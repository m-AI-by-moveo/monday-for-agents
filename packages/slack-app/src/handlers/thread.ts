import type { App, AllMiddlewareArgs, SlackEventMiddlewareArgs } from "@slack/bolt";
import { v4 as uuidv4 } from "uuid";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
  type A2AResponse,
} from "../services/a2a-client.js";
import { threadMap } from "./mention.js";
import type { MentionHandlerDeps } from "./mention.js";
import { IntentRouter } from "../services/intent-router.js";
import {
  handleCreateTask,
  handleBoardStatus,
  handleMeetingSync,
  handleCalendar,
  handleDrive,
  handleAgentChat,
  type IntentContext,
} from "./intent-handlers.js";
import {
  agentResponseBlocks,
  errorBlocks,
  warningBlocks,
  noResponseBlocks,
  loadingBlocks,
} from "../ui/block-builder.js";

const a2a = createA2AClient();
const intentRouter = new IntentRouter();

export function registerThreadHandler(app: App, deps: MentionHandlerDeps = {}): void {
  app.event(
    "message",
    async ({
      event,
      say,
      client,
      context,
    }: AllMiddlewareArgs & SlackEventMiddlewareArgs<"message">) => {
      // Only handle plain messages (not bot messages, not edits, etc.)
      if (event.subtype) return;

      // Ignore messages from our own bot so we don't loop
      if ("bot_id" in event && event.bot_id) return;
      if ("user" in event && event.user === context.botUserId) return;

      const isDM = "channel_type" in event && event.channel_type === "im";
      const hasThread = "thread_ts" in event && !!event.thread_ts;

      // -----------------------------------------------------------------------
      // New DM (no thread) — classify intent and dispatch like mention handler
      // -----------------------------------------------------------------------
      if (isDM && !hasThread) {
        const messageText =
          "text" in event && typeof event.text === "string" ? event.text : "";
        if (!messageText.trim()) return;

        const threadTs = event.ts;

        const { blocks: loadBlocks, text: loadText } = loadingBlocks("Thinking...");
        await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

        const { intent, agentKey } = await intentRouter.classify(messageText);
        console.log(`[dm] Intent: ${intent} | Agent: ${agentKey} | thread=${threadTs}`);

        const mapping = { contextId: uuidv4(), agentKey, intent };
        threadMap.set(threadTs, mapping);

        const ctx: IntentContext = {
          say,
          client,
          event: {
            ts: event.ts,
            thread_ts: undefined,
            user: "user" in event ? event.user : undefined,
            channel: "channel" in event ? event.channel : undefined,
            text: "text" in event ? event.text : undefined,
          },
          threadTs,
          messageText,
          googleServices: deps.googleServices,
          meetingStore: deps.meetingStore,
        };

        switch (intent) {
          case "create-task":
            await handleCreateTask(ctx);
            break;
          case "board-status":
            await handleBoardStatus(ctx);
            break;
          case "meeting-sync":
            await handleMeetingSync(ctx);
            break;
          case "calendar":
            await handleCalendar(ctx);
            break;
          case "drive":
            await handleDrive(ctx);
            break;
          case "agent-chat":
          default:
            await handleAgentChat(ctx, agentKey);
            break;
        }
        return;
      }

      // -----------------------------------------------------------------------
      // Threaded reply (channel or DM) — continue existing conversation
      // -----------------------------------------------------------------------
      if (!hasThread) return;

      const threadTs = (event as any).thread_ts as string;

      // Check if we have an active agent conversation for this thread
      const mapping = threadMap.get(threadTs);
      if (!mapping) return; // not a tracked thread – ignore

      // In channels, only continue agent-chat threads (other intents are one-shot).
      // In DMs, allow all thread continuations so users can follow up naturally.
      if (!isDM && mapping.intent && mapping.intent !== "agent-chat") return;

      const messageText =
        "text" in event && typeof event.text === "string" ? event.text : "";
      if (!messageText.trim()) return;

      const agentUrl = AGENT_URLS[mapping.agentKey];
      if (!agentUrl) {
        console.error(`[thread] No URL for agent key: ${mapping.agentKey}`);
        return;
      }

      console.log(
        `[thread] Continuing conversation with ${mapping.agentKey} | thread=${threadTs} context=${mapping.contextId}`,
      );

      let response: A2AResponse;
      try {
        response = await a2a.sendMessage(
          agentUrl,
          messageText,
          mapping.contextId,
        );
      } catch (err) {
        console.error("[thread] Failed to contact agent:", err);
        const { blocks, text } = warningBlocks(
          `Could not reach the *${mapping.agentKey}* agent. Please try again later.`,
        );
        await say({ blocks, text, thread_ts: threadTs });
        return;
      }

      if (response.error) {
        const { blocks, text } = errorBlocks(
          `Agent error: ${response.error.message}`,
        );
        await say({ blocks, text, thread_ts: threadTs });
        return;
      }

      if (response.result) {
        const replyText = extractTextFromTask(response.result);
        const { blocks, text } = agentResponseBlocks(mapping.agentKey, replyText);
        await say({ blocks, text, thread_ts: threadTs });
      } else {
        const { blocks, text } = noResponseBlocks();
        await say({ blocks, text, thread_ts: threadTs });
      }
    },
  );
}
