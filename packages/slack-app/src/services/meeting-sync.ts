import { google } from "googleapis";
import type { GoogleAuthService } from "./google-auth.js";
import type { MeetingStore } from "./meeting-store.js";
import type { MeetingNotesAgent, MeetingAnalysis } from "./meeting-notes-agent.js";
import { meetingPreviewBlocks } from "../scheduler/blocks/scheduler-blocks.js";

export interface MeetingSyncResult {
  meetingsFound: number;
  transcriptsFound: number;
  previewsPosted: number;
  skipped: number;
  errors: string[];
}

interface SlackClient {
  chat: {
    postMessage: (args: {
      channel: string;
      text: string;
      blocks?: any[];
      metadata?: {
        event_type: string;
        event_payload: Record<string, unknown>;
      };
    }) => Promise<unknown>;
  };
}

export class MeetingSyncService {
  constructor(
    private auth: GoogleAuthService,
    private meetingStore: MeetingStore,
    private meetingNotesAgent: MeetingNotesAgent,
    private slackClient: SlackClient,
    private channelId: string,
  ) {}

  async checkRecentMeetings(userId: string): Promise<MeetingSyncResult> {
    const result: MeetingSyncResult = {
      meetingsFound: 0,
      transcriptsFound: 0,
      previewsPosted: 0,
      skipped: 0,
      errors: [],
    };

    try {
      const authClient = await this.auth.getClient(userId);
      const calendar = google.calendar({ version: "v3", auth: authClient });

      const now = new Date();
      const twentyMinAgo = new Date(now.getTime() - 20 * 60 * 1000);

      const res = await calendar.events.list({
        calendarId: "primary",
        timeMin: twentyMinAgo.toISOString(),
        timeMax: now.toISOString(),
        singleEvents: true,
        orderBy: "startTime",
        maxResults: 25,
      });

      const events = res.data.items ?? [];

      // Filter to events with Google Meet / conference data
      const meetEvents = events.filter(
        (e) => e.conferenceData || e.hangoutLink,
      );

      result.meetingsFound = meetEvents.length;

      for (const event of meetEvents) {
        const eventId = event.id ?? "";
        if (!eventId) continue;

        if (this.meetingStore.isProcessed(eventId)) {
          result.skipped++;
          continue;
        }

        const meetingTitle = event.summary ?? "(untitled meeting)";

        try {
          const transcript = await this.findTranscript(userId, meetingTitle);
          if (!transcript) {
            result.skipped++;
            continue;
          }

          result.transcriptsFound++;

          const analysis = await this.meetingNotesAgent.analyzeMeetingTranscript(
            transcript,
            meetingTitle,
          );

          if (analysis.actionItems.length === 0) {
            this.meetingStore.markDismissed(eventId, meetingTitle);
            result.skipped++;
            continue;
          }

          this.meetingStore.markPending(eventId, meetingTitle);

          const { blocks, text } = meetingPreviewBlocks(
            meetingTitle,
            analysis,
            eventId,
          );

          await this.slackClient.chat.postMessage({
            channel: this.channelId,
            text,
            blocks,
            metadata: {
              event_type: "meeting_analysis",
              event_payload: {
                event_id: eventId,
                analysis: JSON.stringify(analysis),
              },
            },
          });

          result.previewsPosted++;
        } catch (err: any) {
          result.errors.push(
            `Error processing "${meetingTitle}": ${err.message ?? String(err)}`,
          );
        }
      }
    } catch (err: any) {
      result.errors.push(`Calendar API error: ${err.message ?? String(err)}`);
    }

    return result;
  }

  private async findTranscript(
    userId: string,
    meetingTitle: string,
  ): Promise<string | null> {
    try {
      const authClient = await this.auth.getClient(userId);
      const drive = google.drive({ version: "v3", auth: authClient });

      const escapedTitle = meetingTitle.replace(/'/g, "\\'");

      // Google Meet transcripts are named: "<title> - <date> - Transcript"
      // Search by title in name + "Transcript" suffix
      const query =
        `name contains '${escapedTitle}' and ` +
        `name contains 'Transcript' and ` +
        `mimeType = 'application/vnd.google-apps.document' and ` +
        `trashed = false`;

      const res = await drive.files.list({
        q: query,
        pageSize: 5,
        fields: "files(id, name, mimeType, modifiedTime)",
        orderBy: "modifiedTime desc",
      });

      const files = res.data.files ?? [];
      if (files.length === 0) return null;

      const fileId = files[0].id;
      if (!fileId) return null;

      const exportRes = await drive.files.export(
        { fileId, mimeType: "text/plain" },
        { responseType: "text" },
      );

      return String(exportRes.data);
    } catch {
      return null;
    }
  }
}
