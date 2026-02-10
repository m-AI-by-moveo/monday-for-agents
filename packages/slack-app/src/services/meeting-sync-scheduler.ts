import { google } from "googleapis";
import type { GoogleAuthService } from "./google-auth.js";
import type { MeetingStore } from "./meeting-store.js";
import type { MeetingSyncService } from "./meeting-sync.js";

const FIRST_ATTEMPT_DELAY_MS = 2 * 60 * 1000;   // 2 min after meeting ends
const RETRY_DELAY_MS = 15 * 60 * 1000;           // 15 min after meeting ends (fallback)
const REFRESH_INTERVAL_MS = 60 * 60 * 1000;      // Refresh calendar every hour

interface ScheduledMeeting {
  eventId: string;
  title: string;
  endTime: Date;
  firstTimer: ReturnType<typeof setTimeout> | null;
  retryTimer: ReturnType<typeof setTimeout> | null;
}

export class MeetingSyncScheduler {
  private scheduled = new Map<string, ScheduledMeeting>();
  private refreshTimer: ReturnType<typeof setInterval> | null = null;
  private stopped = false;

  constructor(
    private auth: GoogleAuthService,
    private userId: string,
    private meetingStore: MeetingStore,
    private syncService: MeetingSyncService,
  ) {}

  async start(): Promise<void> {
    console.log("[meeting-scheduler] Starting calendar-aware scheduler");
    await this.refreshSchedule();

    this.refreshTimer = setInterval(async () => {
      if (this.stopped) return;
      try {
        await this.refreshSchedule();
      } catch (err: any) {
        console.error("[meeting-scheduler] Refresh error:", err.message);
      }
    }, REFRESH_INTERVAL_MS);

    console.log("[meeting-scheduler] Will refresh calendar every hour");
  }

  stop(): void {
    this.stopped = true;
    if (this.refreshTimer) {
      clearInterval(this.refreshTimer);
      this.refreshTimer = null;
    }
    for (const meeting of this.scheduled.values()) {
      if (meeting.firstTimer) clearTimeout(meeting.firstTimer);
      if (meeting.retryTimer) clearTimeout(meeting.retryTimer);
    }
    this.scheduled.clear();
    console.log("[meeting-scheduler] Stopped");
  }

  async refreshSchedule(): Promise<void> {
    try {
      const authClient = await this.auth.getClient(this.userId);
      const calendar = google.calendar({ version: "v3", auth: authClient });

      const now = new Date();
      const endOfDay = new Date(now);
      endOfDay.setHours(23, 59, 59, 999);

      const res = await calendar.events.list({
        calendarId: "primary",
        timeMin: now.toISOString(),
        timeMax: endOfDay.toISOString(),
        singleEvents: true,
        orderBy: "startTime",
        maxResults: 50,
      });

      const events = res.data.items ?? [];
      const meetEvents = events.filter(
        (e) => e.conferenceData || e.hangoutLink,
      );

      let newCount = 0;
      for (const event of meetEvents) {
        const eventId = event.id ?? "";
        if (!eventId) continue;
        if (this.scheduled.has(eventId)) continue;
        if (this.meetingStore.isProcessed(eventId)) continue;

        const endStr = event.end?.dateTime ?? event.end?.date;
        if (!endStr) continue;

        const endTime = new Date(endStr);
        const title = event.summary ?? "(untitled meeting)";

        this.scheduleMeeting(eventId, title, endTime);
        newCount++;
      }

      if (newCount > 0) {
        console.log(`[meeting-scheduler] Scheduled ${newCount} new meeting(s)`);
      }

      const totalPending = Array.from(this.scheduled.values()).filter(
        (m) => m.firstTimer || m.retryTimer,
      ).length;
      console.log(
        `[meeting-scheduler] Refreshed — ${meetEvents.length} upcoming Meet event(s), ${totalPending} pending sync(s)`,
      );
    } catch (err: any) {
      console.error("[meeting-scheduler] Failed to fetch calendar:", err.message);
    }
  }

  private scheduleMeeting(eventId: string, title: string, endTime: Date): void {
    const now = Date.now();
    const firstAttemptAt = endTime.getTime() + FIRST_ATTEMPT_DELAY_MS;
    const retryAt = endTime.getTime() + RETRY_DELAY_MS;

    const meeting: ScheduledMeeting = {
      eventId,
      title,
      endTime,
      firstTimer: null,
      retryTimer: null,
    };

    const firstDelay = firstAttemptAt - now;
    if (firstDelay > 0) {
      meeting.firstTimer = setTimeout(() => {
        this.attemptSync(eventId, title, false);
      }, firstDelay);

      const mins = Math.round(firstDelay / 60000);
      console.log(
        `[meeting-scheduler] "${title}" ends at ${endTime.toLocaleTimeString()} — sync in ${mins} min`,
      );
    }

    // Always schedule the retry as a fallback
    const retryDelay = retryAt - now;
    if (retryDelay > 0) {
      meeting.retryTimer = setTimeout(() => {
        this.attemptSync(eventId, title, true);
      }, retryDelay);
    }

    this.scheduled.set(eventId, meeting);
  }

  private async attemptSync(
    eventId: string,
    title: string,
    isRetry: boolean,
  ): Promise<void> {
    if (this.stopped) return;
    if (this.meetingStore.isProcessed(eventId)) {
      // Already handled (first attempt succeeded, or manually processed)
      this.clearTimers(eventId);
      return;
    }

    const label = isRetry ? "retry" : "first attempt";
    console.log(`[meeting-scheduler] Syncing "${title}" (${label})`);

    try {
      const result = await this.syncService.checkRecentMeetings(this.userId);

      if (result.previewsPosted > 0) {
        console.log(
          `[meeting-scheduler] "${title}" — posted ${result.previewsPosted} preview(s)`,
        );
        this.clearTimers(eventId);
      } else if (!isRetry) {
        console.log(
          `[meeting-scheduler] "${title}" — no transcript yet, will retry in ~${Math.round(RETRY_DELAY_MS / 60000 - FIRST_ATTEMPT_DELAY_MS / 60000)} min`,
        );
        // Keep retry timer running
      } else {
        console.log(
          `[meeting-scheduler] "${title}" — no transcript found after retry, giving up`,
        );
        this.clearTimers(eventId);
      }

      if (result.errors.length > 0) {
        console.error(`[meeting-scheduler] Errors:`, result.errors);
      }
    } catch (err: any) {
      console.error(
        `[meeting-scheduler] "${title}" sync failed (${label}):`,
        err.message,
      );
    }
  }

  private clearTimers(eventId: string): void {
    const meeting = this.scheduled.get(eventId);
    if (!meeting) return;
    if (meeting.firstTimer) clearTimeout(meeting.firstTimer);
    if (meeting.retryTimer) clearTimeout(meeting.retryTimer);
    meeting.firstTimer = null;
    meeting.retryTimer = null;
  }
}
