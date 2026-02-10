import type { WebClient } from "@slack/web-api";
import { v4 as uuidv4 } from "uuid";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
} from "../services/a2a-client.js";
import {
  agentResponseBlocks,
  errorBlocks,
  warningBlocks,
  loadingBlocks,
  noResponseBlocks,
} from "../ui/block-builder.js";
import { googleConnectBlocks } from "../ui/google-blocks.js";
import { taskPreviewBlocks } from "../ui/task-preview-blocks.js";
import { TaskExtractorAgent } from "../services/task-extractor-agent.js";
import { GoogleCalendarAgent } from "../services/google-calendar-agent.js";
import { GoogleDriveAgent } from "../services/google-drive-agent.js";
import { MeetingSyncService } from "../services/meeting-sync.js";
import { MeetingNotesAgent } from "../services/meeting-notes-agent.js";
import { fetchBoardStatus } from "./commands.js";
import { fetchBoards, fetchUsers } from "../services/monday-client.js";
import type { GoogleServices } from "./commands.js";
import type { MeetingStore } from "../services/meeting-store.js";
import type { ThreadMapping } from "./mention.js";
import { threadMap } from "./mention.js";

// ---------------------------------------------------------------------------
// Context passed to every intent handler
// ---------------------------------------------------------------------------

export interface IntentContext {
  say: (msg: { blocks?: any[]; text: string; thread_ts: string; metadata?: any }) => Promise<any>;
  client: WebClient;
  event: { ts: string; thread_ts?: string; user?: string; channel?: string; text?: string };
  threadTs: string;
  messageText: string;
  googleServices?: GoogleServices | null;
  meetingStore?: MeetingStore | null;
}

// ---------------------------------------------------------------------------
// Lazy-init singletons
// ---------------------------------------------------------------------------

let taskExtractor: TaskExtractorAgent | null = null;
let calendarAgent: GoogleCalendarAgent | null = null;
let driveAgent: GoogleDriveAgent | null = null;

const a2a = createA2AClient();

// ---------------------------------------------------------------------------
// create-task: Read history, extract task, post preview with buttons
// ---------------------------------------------------------------------------

export async function handleCreateTask(ctx: IntentContext): Promise<void> {
  const { say, client, event, threadTs, messageText } = ctx;
  const channelId = event.channel ?? "";

  const { blocks: loadBlocks, text: loadText } = loadingBlocks(
    "Reading conversation and extracting task details...",
  );
  await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

  try {
    // Fetch conversation history
    let formattedMessages: { user: string; text: string }[] = [];
    try {
      const history = await client.conversations.history({
        channel: channelId,
        limit: 20,
      });

      const userMessages = (history.messages ?? [])
        .filter((m: any) => !m.bot_id && m.text)
        .reverse();

      const userIdSet = new Set(userMessages.map((m: any) => m.user).filter(Boolean));
      const userNames = new Map<string, string>();
      await Promise.all(
        [...userIdSet].map(async (uid) => {
          try {
            const info = await client.users.info({ user: uid! });
            userNames.set(uid!, (info.user as any)?.real_name || (info.user as any)?.name || uid!);
          } catch {
            userNames.set(uid!, uid!);
          }
        }),
      );

      formattedMessages = userMessages.map((m: any) => ({
        user: userNames.get(m.user!) ?? m.user ?? "Unknown",
        text: m.text!,
      }));
    } catch (err: any) {
      console.warn("[intent-handlers] Could not fetch history:", err.message);
    }

    // Also add the triggering message itself if it has useful context
    if (messageText && !messageText.toLowerCase().startsWith("create")) {
      formattedMessages.push({ user: "User", text: messageText });
    }

    // Extract task + fetch boards/users in parallel
    if (!taskExtractor) taskExtractor = new TaskExtractorAgent();
    const [extractedTask, boards, users] = await Promise.all([
      taskExtractor.extractTaskFromMessages(formattedMessages),
      fetchBoards().catch(() => []),
      fetchUsers().catch(() => []),
    ]);

    const { blocks, text, metadata } = taskPreviewBlocks(extractedTask, {
      extractedTask,
      channelId,
      threadTs,
      userId: event.user ?? "",
      boardsJson: JSON.stringify(boards),
      usersJson: JSON.stringify(users),
    });

    await say({ blocks, text, thread_ts: threadTs, metadata });
  } catch (err: any) {
    console.error("[intent-handlers] handleCreateTask error:", err);
    const { blocks, text } = errorBlocks(`Failed to extract task: ${err.message ?? "Unknown error"}`);
    await say({ blocks, text, thread_ts: threadTs });
  }
}

// ---------------------------------------------------------------------------
// board-status: Query scrum-master agent
// ---------------------------------------------------------------------------

export async function handleBoardStatus(ctx: IntentContext): Promise<void> {
  const { say, threadTs } = ctx;

  const { blocks: loadBlocks, text: loadText } = loadingBlocks(
    "Fetching board status from Scrum Master...",
  );
  await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

  const result = await fetchBoardStatus();
  await say({ blocks: result.blocks, text: result.text, thread_ts: threadTs });
}

// ---------------------------------------------------------------------------
// meeting-sync: Check recent meeting transcripts
// ---------------------------------------------------------------------------

export async function handleMeetingSync(ctx: IntentContext): Promise<void> {
  const { say, client, event, threadTs, googleServices, meetingStore } = ctx;
  const userId = event.user ?? "";
  const channelId = event.channel ?? "";

  if (!googleServices) {
    const { blocks, text } = warningBlocks("Google integration is not configured.");
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  if (!meetingStore) {
    const { blocks, text } = warningBlocks("Meeting sync is not enabled.");
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  if (!googleServices.auth.isConnected(userId)) {
    const authUrl = googleServices.auth.getAuthUrl(userId);
    const { blocks, text } = googleConnectBlocks(authUrl);
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  const { blocks: loadBlocks, text: loadText } = loadingBlocks(
    "Checking recent meetings for transcripts...",
  );
  await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

  try {
    const meetingNotesAgent = new MeetingNotesAgent();
    const syncService = new MeetingSyncService(
      googleServices.auth,
      meetingStore,
      meetingNotesAgent,
      client,
      channelId,
    );

    const result = await syncService.checkRecentMeetings(userId);

    let summary = `:memo: *Meeting Sync Results*\n`;
    summary += `Meetings found: ${result.meetingsFound}\n`;
    summary += `Transcripts found: ${result.transcriptsFound}\n`;
    summary += `Previews posted: ${result.previewsPosted}\n`;
    summary += `Skipped: ${result.skipped}`;
    if (result.errors.length > 0) {
      summary += `\nErrors: ${result.errors.join(", ")}`;
    }

    await say({ text: summary, thread_ts: threadTs });
  } catch (err: any) {
    console.error("[intent-handlers] handleMeetingSync error:", err);
    const { blocks, text } = errorBlocks(err.message ?? "Meeting sync failed.");
    await say({ blocks, text, thread_ts: threadTs });
  }
}

// ---------------------------------------------------------------------------
// calendar: Delegate to GoogleCalendarAgent
// ---------------------------------------------------------------------------

export async function handleCalendar(ctx: IntentContext): Promise<void> {
  const { say, threadTs, messageText, googleServices, event } = ctx;
  const userId = event.user ?? "";

  if (!googleServices) {
    const { blocks, text } = warningBlocks("Google integration is not configured.");
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  if (!googleServices.auth.isConnected(userId)) {
    const authUrl = googleServices.auth.getAuthUrl(userId);
    const { blocks, text } = googleConnectBlocks(authUrl);
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  const { blocks: loadBlocks, text: loadText } = loadingBlocks("Checking your calendar...");
  await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

  try {
    if (!calendarAgent) calendarAgent = new GoogleCalendarAgent();
    const result = await calendarAgent.handleRequest(messageText, googleServices.calendar, userId);
    await say({ text: result, thread_ts: threadTs });
  } catch (err: any) {
    console.error("[intent-handlers] handleCalendar error:", err);
    const { blocks, text } = errorBlocks(err.message ?? "Calendar operation failed.");
    await say({ blocks, text, thread_ts: threadTs });
  }
}

// ---------------------------------------------------------------------------
// drive: Delegate to GoogleDriveAgent
// ---------------------------------------------------------------------------

export async function handleDrive(ctx: IntentContext): Promise<void> {
  const { say, threadTs, messageText, googleServices, event } = ctx;
  const userId = event.user ?? "";

  if (!googleServices) {
    const { blocks, text } = warningBlocks("Google integration is not configured.");
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  if (!googleServices.auth.isConnected(userId)) {
    const authUrl = googleServices.auth.getAuthUrl(userId);
    const { blocks, text } = googleConnectBlocks(authUrl);
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  const { blocks: loadBlocks, text: loadText } = loadingBlocks("Searching your Drive...");
  await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

  try {
    if (!driveAgent) driveAgent = new GoogleDriveAgent();
    const result = await driveAgent.handleRequest(messageText, googleServices.drive, userId);
    await say({ text: result, thread_ts: threadTs });
  } catch (err: any) {
    console.error("[intent-handlers] handleDrive error:", err);
    const { blocks, text } = errorBlocks(err.message ?? "Drive operation failed.");
    await say({ blocks, text, thread_ts: threadTs });
  }
}

// ---------------------------------------------------------------------------
// agent-chat: Forward to A2A agent (existing behavior)
// ---------------------------------------------------------------------------

export async function handleAgentChat(
  ctx: IntentContext,
  agentKey: string,
): Promise<void> {
  const { say, client, event, threadTs, messageText } = ctx;
  const channelId = event.channel ?? "";

  const agentUrl = AGENT_URLS[agentKey];
  if (!agentUrl) {
    const { blocks, text } = errorBlocks(`Unknown agent: ${agentKey}`);
    await say({ blocks, text, thread_ts: threadTs });
    return;
  }

  // Create (or reuse) a context ID for this thread
  let mapping = threadMap.get(threadTs);
  if (!mapping) {
    mapping = { contextId: uuidv4(), agentKey, intent: "agent-chat" };
    threadMap.set(threadTs, mapping);
  }

  console.log(
    `[intent-handlers] Routing to ${agentKey} | thread=${threadTs} context=${mapping.contextId}`,
  );

  const { blocks: loadBlocks, text: loadText } = loadingBlocks(
    `Routing to *${agentKey}*... This may take a few minutes.`,
  );
  await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

  // Fetch recent channel history so the agent has context
  let channelContext = "";
  if (channelId) {
    try {
      const history = await client.conversations.history({
        channel: channelId,
        limit: 15,
      });
      const msgs = (history.messages ?? [])
        .filter((m: any) => m.text && !m.bot_id)
        .reverse()
        .slice(-15);
      if (msgs.length > 0) {
        channelContext =
          "Recent Slack channel messages for context:\n" +
          msgs.map((m: any) => `- ${m.text}`).join("\n") +
          "\n\n";
      }
    } catch (err: any) {
      console.warn("[intent-handlers] Could not fetch channel history:", err.message);
    }
  }

  const fullMessage = channelContext
    ? channelContext + "User request: " + messageText
    : messageText;

  try {
    const response = await a2a.sendMessage(agentUrl, fullMessage, mapping.contextId);

    if (response.error) {
      const { blocks, text } = errorBlocks(`Agent error: ${response.error.message}`);
      await say({ blocks, text, thread_ts: threadTs });
      return;
    }

    if (response.result) {
      const replyText = extractTextFromTask(response.result);
      const { blocks, text } = agentResponseBlocks(agentKey, replyText);
      await say({ blocks, text, thread_ts: threadTs });
    } else {
      const { blocks, text } = noResponseBlocks();
      await say({ blocks, text, thread_ts: threadTs });
    }
  } catch (err) {
    console.error("[intent-handlers] Failed to contact agent:", err);
    const { blocks, text } = warningBlocks(
      `Could not reach the *${agentKey}* agent. Please try again later.`,
    );
    await say({ blocks, text, thread_ts: threadTs });
  }
}
