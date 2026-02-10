import type { App } from "@slack/bolt";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
} from "../services/a2a-client.js";
import {
  agentListBlocks,
  statusDashboardBlocks,
  schedulerStatusBlocks,
  loadingBlocks,
  errorBlocks,
  warningBlocks,
} from "../ui/block-builder.js";
import {
  googleConnectBlocks,
  googleStatusBlocks,
} from "../ui/google-blocks.js";
import type { SchedulerService } from "../services/scheduler.js";
import type { GoogleAuthService } from "../services/google-auth.js";
import type { GoogleCalendarService } from "../services/google-calendar.js";
import type { GoogleDriveService } from "../services/google-drive.js";
import { GoogleCalendarAgent } from "../services/google-calendar-agent.js";
import { GoogleDriveAgent } from "../services/google-drive-agent.js";
import { MeetingSyncService } from "../services/meeting-sync.js";
import { MeetingNotesAgent } from "../services/meeting-notes-agent.js";
import type { MeetingStore } from "../services/meeting-store.js";
import { TaskExtractorAgent } from "../services/task-extractor-agent.js";
import { fetchBoards, fetchUsers } from "../services/monday-client.js";
import {
  buildCreateTaskLoadingModal,
  buildCreateTaskModal,
  type CreateTaskModalMetadata,
} from "../ui/create-task-modal-blocks.js";

const a2a = createA2AClient();

// ---------------------------------------------------------------------------
// /status — query Scrum Master for board status
// ---------------------------------------------------------------------------

async function fetchBoardStatus(): Promise<{ blocks: any[]; text: string }> {
  const agentUrl = AGENT_URLS["scrum-master"];
  if (!agentUrl) {
    return errorBlocks("Scrum Master agent is not configured.");
  }

  try {
    const response = await a2a.sendMessage(
      agentUrl,
      "Give me the current board status summary.",
    );

    if (response.error) {
      return errorBlocks(`Agent error: ${response.error.message}`);
    }

    if (response.result) {
      const statusText = extractTextFromTask(response.result);
      return statusDashboardBlocks(statusText);
    }
    return { blocks: [], text: "_No status available from agent._" };
  } catch (err) {
    console.error("[commands] /status failed:", err);
    return warningBlocks("Could not reach the Scrum Master agent.");
  }
}

// ---------------------------------------------------------------------------
// Google services interface
// ---------------------------------------------------------------------------

export interface GoogleServices {
  auth: GoogleAuthService;
  calendar: GoogleCalendarService;
  drive: GoogleDriveService;
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

export function registerCommands(
  app: App,
  scheduler?: SchedulerService | null,
  googleServices?: GoogleServices | null,
  meetingStore?: MeetingStore | null,
): void {
  // Lazy-init LLM agents (only when first needed)
  let calendarAgent: GoogleCalendarAgent | null = null;
  let driveAgent: GoogleDriveAgent | null = null;

  app.command("/agents", async ({ ack, respond }) => {
    await ack();
    console.log("[commands] /agents invoked");
    const { blocks, text } = agentListBlocks(AGENT_URLS);
    await respond({ response_type: "ephemeral", blocks, text });
  });

  app.command("/status", async ({ ack, respond }) => {
    await ack();
    console.log("[commands] /status invoked");

    const loading = loadingBlocks("Fetching board status from Scrum Master...");
    await respond({
      response_type: "ephemeral",
      blocks: loading.blocks,
      text: loading.text,
    });

    const result = await fetchBoardStatus();
    await respond({
      response_type: "in_channel",
      blocks: result.blocks,
      text: result.text,
    });
  });

  app.command("/scheduler", async ({ ack, respond }) => {
    await ack();
    console.log("[commands] /scheduler invoked");

    if (!scheduler) {
      await respond({
        response_type: "ephemeral",
        text: "Scheduler is disabled.",
      });
      return;
    }

    const jobs = scheduler.getStatus();
    const { blocks, text } = schedulerStatusBlocks(jobs);
    await respond({ response_type: "ephemeral", blocks, text });
  });

  // -------------------------------------------------------------------------
  // /google — OAuth2 connect / disconnect / status
  // -------------------------------------------------------------------------

  app.command("/google", async ({ ack, respond, command }) => {
    await ack();
    console.log("[commands] /google invoked");

    if (!googleServices) {
      await respond({
        response_type: "ephemeral",
        text: "Google integration is not configured.",
      });
      return;
    }

    const subcommand = (command.text ?? "").trim().toLowerCase();
    const userId = command.user_id;

    switch (subcommand) {
      case "connect": {
        const authUrl = googleServices.auth.getAuthUrl(userId);
        const { blocks, text } = googleConnectBlocks(authUrl);
        await respond({ response_type: "ephemeral", blocks, text });
        break;
      }
      case "disconnect": {
        await googleServices.auth.disconnect(userId);
        await respond({
          response_type: "ephemeral",
          text: ":white_check_mark: Google account disconnected.",
        });
        break;
      }
      case "status":
      default: {
        const connected = googleServices.auth.isConnected(userId);
        const { blocks, text } = googleStatusBlocks(connected);
        await respond({ response_type: "ephemeral", blocks, text });
        break;
      }
    }
  });

  // -------------------------------------------------------------------------
  // /gcal — Natural language Google Calendar (LLM-powered)
  // -------------------------------------------------------------------------

  app.command("/gcal", async ({ ack, respond, command }) => {
    await ack();
    console.log("[commands] /gcal invoked");

    if (!googleServices) {
      await respond({ response_type: "ephemeral", text: "Google integration is not configured." });
      return;
    }

    const userId = command.user_id;
    if (!googleServices.auth.isConnected(userId)) {
      const authUrl = googleServices.auth.getAuthUrl(userId);
      const { blocks, text } = googleConnectBlocks(authUrl);
      await respond({ response_type: "ephemeral", blocks, text });
      return;
    }

    const userText = (command.text ?? "").trim();
    if (!userText) {
      await respond({
        response_type: "ephemeral",
        text: "Tell me what you need! Examples:\n" +
          "• `/gcal what do I have today?`\n" +
          "• `/gcal book a meeting tomorrow 2-3pm`\n" +
          "• `/gcal what's my next free slot this week?`\n" +
          "• `/gcal cancel my 3pm meeting`",
      });
      return;
    }

    // Show loading indicator
    const loading = loadingBlocks("Checking your calendar...");
    await respond({ response_type: "ephemeral", blocks: loading.blocks, text: loading.text });

    try {
      if (!calendarAgent) calendarAgent = new GoogleCalendarAgent();
      const result = await calendarAgent.handleRequest(userText, googleServices.calendar, userId);
      await respond({ response_type: "ephemeral", text: result });
    } catch (err: any) {
      console.error("[commands] /gcal error:", err);
      const { blocks, text } = errorBlocks(err.message ?? "Calendar operation failed.");
      await respond({ response_type: "ephemeral", blocks, text });
    }
  });

  // -------------------------------------------------------------------------
  // /gdrive — Natural language Google Drive (LLM-powered)
  // -------------------------------------------------------------------------

  app.command("/gdrive", async ({ ack, respond, command }) => {
    await ack();
    console.log("[commands] /gdrive invoked");

    if (!googleServices) {
      await respond({ response_type: "ephemeral", text: "Google integration is not configured." });
      return;
    }

    const userId = command.user_id;
    if (!googleServices.auth.isConnected(userId)) {
      const authUrl = googleServices.auth.getAuthUrl(userId);
      const { blocks, text } = googleConnectBlocks(authUrl);
      await respond({ response_type: "ephemeral", blocks, text });
      return;
    }

    const userText = (command.text ?? "").trim();
    if (!userText) {
      await respond({
        response_type: "ephemeral",
        text: "Tell me what you need! Examples:\n" +
          "• `/gdrive show my recent files`\n" +
          "• `/gdrive find the Q4 report`\n" +
          "• `/gdrive create a new doc called Meeting Notes`\n" +
          "• `/gdrive what's in file <fileId>?`",
      });
      return;
    }

    const loading = loadingBlocks("Searching your Drive...");
    await respond({ response_type: "ephemeral", blocks: loading.blocks, text: loading.text });

    try {
      if (!driveAgent) driveAgent = new GoogleDriveAgent();
      const result = await driveAgent.handleRequest(userText, googleServices.drive, userId);
      await respond({ response_type: "ephemeral", text: result });
    } catch (err: any) {
      console.error("[commands] /gdrive error:", err);
      const { blocks, text } = errorBlocks(err.message ?? "Drive operation failed.");
      await respond({ response_type: "ephemeral", blocks, text });
    }
  });

  // -------------------------------------------------------------------------
  // /create-task — Create a Monday.com task from conversation context
  // -------------------------------------------------------------------------

  let taskExtractor: TaskExtractorAgent | null = null;

  app.command("/create-task", async ({ ack, command, client }) => {
    await ack();
    console.log("[commands] /create-task invoked");

    const channelId = command.channel_id;
    const userId = command.user_id;
    const triggerId = command.trigger_id;

    const metadata: CreateTaskModalMetadata = { channelId, userId };

    // Open loading modal immediately (trigger_id expires in 3s)
    let viewId: string;
    try {
      const loadingView = buildCreateTaskLoadingModal(metadata);
      const result = await client.views.open({
        trigger_id: triggerId,
        view: loadingView as any,
      });
      viewId = (result.view as any)?.id;
      if (!viewId) {
        console.error("[commands] /create-task: no view ID returned");
        return;
      }
    } catch (err: any) {
      console.error("[commands] /create-task: failed to open loading modal:", err.message);
      return;
    }

    try {
      // Fetch conversation history
      let formattedMessages: { user: string; text: string }[] = [];
      try {
        const history = await client.conversations.history({
          channel: channelId,
          limit: 20,
        });

        const userMessages = (history.messages ?? [])
          .filter((m) => !m.bot_id && m.text)
          .reverse();

        // Resolve user IDs to display names
        const userIdSet = new Set(userMessages.map((m) => m.user).filter(Boolean));
        const userNames = new Map<string, string>();
        await Promise.all(
          [...userIdSet].map(async (uid) => {
            try {
              const info = await client.users.info({ user: uid! });
              userNames.set(uid!, info.user?.real_name || info.user?.name || uid!);
            } catch {
              userNames.set(uid!, uid!);
            }
          }),
        );

        formattedMessages = userMessages.map((m) => ({
          user: userNames.get(m.user!) ?? m.user ?? "Unknown",
          text: m.text!,
        }));
      } catch (err: any) {
        console.warn("[commands] /create-task: could not fetch history:", err.message);
        // Continue with empty messages — modal will show empty form
      }

      // Extract task details + fetch boards in parallel
      if (!taskExtractor) taskExtractor = new TaskExtractorAgent();
      const [extractedTask, boards, users] = await Promise.all([
        taskExtractor.extractTaskFromMessages(formattedMessages),
        fetchBoards().catch((err) => {
          console.warn("[commands] /create-task: could not fetch boards:", err.message);
          return [];
        }),
        fetchUsers().catch((err) => {
          console.warn("[commands] /create-task: could not fetch users:", err.message);
          return [];
        }),
      ]);

      // Update modal with full form
      const fullView = buildCreateTaskModal(extractedTask, boards, metadata, users);
      await client.views.update({
        view_id: viewId,
        view: fullView as any,
      });
    } catch (err: any) {
      console.error("[commands] /create-task error:", err);
      // Update modal with error message
      try {
        await client.views.update({
          view_id: viewId,
          view: {
            type: "modal",
            callback_id: "create_task_submit",
            title: { type: "plain_text", text: "Create Task" },
            close: { type: "plain_text", text: "Close" },
            blocks: [
              {
                type: "section",
                text: {
                  type: "mrkdwn",
                  text: `:x: Failed to extract task details: ${err.message ?? "Unknown error"}`,
                },
              },
            ],
          } as any,
        });
      } catch (updateErr: any) {
        console.error("[commands] /create-task: failed to update modal with error:", updateErr.message);
      }
    }
  });

  // -------------------------------------------------------------------------
  // /meeting-sync — Manually trigger meeting notes extraction
  // -------------------------------------------------------------------------

  app.command("/meeting-sync", async ({ ack, respond, command }) => {
    await ack();
    console.log("[commands] /meeting-sync invoked");

    if (!googleServices) {
      await respond({ response_type: "ephemeral", text: "Google integration is not configured." });
      return;
    }

    if (!meetingStore) {
      await respond({ response_type: "ephemeral", text: "Meeting sync is not enabled." });
      return;
    }

    const userId = command.user_id;
    if (!googleServices.auth.isConnected(userId)) {
      const authUrl = googleServices.auth.getAuthUrl(userId);
      const { blocks, text } = googleConnectBlocks(authUrl);
      await respond({ response_type: "ephemeral", blocks, text });
      return;
    }

    const loading = loadingBlocks("Checking recent meetings for transcripts...");
    await respond({ response_type: "ephemeral", blocks: loading.blocks, text: loading.text });

    try {
      const meetingNotesAgent = new MeetingNotesAgent();
      const channelId = command.channel_id;
      const syncService = new MeetingSyncService(
        googleServices.auth,
        meetingStore,
        meetingNotesAgent,
        app.client,
        channelId,
      );

      const result = await syncService.checkRecentMeetings(userId);

      let summary = `:memo: *Meeting Sync Results*\n`;
      summary += `• Meetings found: ${result.meetingsFound}\n`;
      summary += `• Transcripts found: ${result.transcriptsFound}\n`;
      summary += `• Previews posted: ${result.previewsPosted}\n`;
      summary += `• Skipped: ${result.skipped}`;
      if (result.errors.length > 0) {
        summary += `\n• Errors: ${result.errors.join(", ")}`;
      }

      await respond({ response_type: "ephemeral", text: summary });
    } catch (err: any) {
      console.error("[commands] /meeting-sync error:", err);
      const { blocks, text } = errorBlocks(err.message ?? "Meeting sync failed.");
      await respond({ response_type: "ephemeral", blocks, text });
    }
  });
}
