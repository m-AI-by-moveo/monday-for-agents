import type { App, AllMiddlewareArgs, SlackEventMiddlewareArgs } from "@slack/bolt";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
  type A2AResponse,
} from "../services/a2a-client.js";
import { threadMap } from "./mention.js";
import {
  agentResponseBlocks,
  errorBlocks,
  warningBlocks,
  noResponseBlocks,
} from "../ui/block-builder.js";

const a2a = createA2AClient();

export function registerThreadHandler(app: App): void {
  app.event(
    "message",
    async ({
      event,
      say,
      context,
    }: AllMiddlewareArgs & SlackEventMiddlewareArgs<"message">) => {
      // Only handle plain messages (not bot messages, not edits, etc.)
      if (event.subtype) return;

      // Must be a threaded reply
      if (!("thread_ts" in event) || !event.thread_ts) return;

      const threadTs = event.thread_ts;

      // Ignore messages from our own bot so we don't loop
      if ("bot_id" in event && event.bot_id) return;
      if ("user" in event && event.user === context.botUserId) return;

      // Check if we have an active agent conversation for this thread
      const mapping = threadMap.get(threadTs);
      if (!mapping) return; // not a tracked thread – ignore

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
