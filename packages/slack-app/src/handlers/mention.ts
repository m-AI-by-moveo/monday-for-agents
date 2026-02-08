import type { App, AllMiddlewareArgs, SlackEventMiddlewareArgs } from "@slack/bolt";
import { v4 as uuidv4 } from "uuid";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
  type A2AResponse,
} from "../services/a2a-client.js";

// ---------------------------------------------------------------------------
// State — in-memory mapping between Slack threads and A2A context IDs
// ---------------------------------------------------------------------------

export interface ThreadMapping {
  contextId: string;
  agentKey: string;
}

/** Map from Slack thread_ts to A2A context metadata */
export const threadMap = new Map<string, ThreadMapping>();

// ---------------------------------------------------------------------------
// Routing logic
// ---------------------------------------------------------------------------

const SCRUM_MASTER_KEYWORDS = [
  "status",
  "standup",
  "blocked",
  "summary",
  "report",
];

function pickAgent(text: string): string {
  const lower = text.toLowerCase();
  for (const kw of SCRUM_MASTER_KEYWORDS) {
    if (lower.includes(kw)) {
      return "scrum-master";
    }
  }
  return "product-owner";
}

function stripMention(text: string): string {
  // Slack mentions look like <@U12345> – strip them out
  return text.replace(/<@[A-Z0-9]+>/g, "").trim();
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

const a2a = createA2AClient();

export function registerMentionHandler(app: App): void {
  app.event(
    "app_mention",
    async ({
      event,
      say,
    }: AllMiddlewareArgs & SlackEventMiddlewareArgs<"app_mention">) => {
      const rawText = event.text ?? "";
      const messageText = stripMention(rawText);

      if (!messageText) {
        await say({ text: "Hey! How can I help?", thread_ts: event.ts });
        return;
      }

      const agentKey = pickAgent(messageText);
      const agentUrl = AGENT_URLS[agentKey];
      if (!agentUrl) {
        await say({
          text: `Unknown agent: ${agentKey}`,
          thread_ts: event.ts,
        });
        return;
      }

      // Use the existing thread_ts if this mention is already inside a thread,
      // otherwise use the event ts as the thread root.
      const threadTs = event.thread_ts ?? event.ts;

      // Create (or reuse) a context ID for this thread
      let mapping = threadMap.get(threadTs);
      if (!mapping) {
        mapping = { contextId: uuidv4(), agentKey };
        threadMap.set(threadTs, mapping);
      }

      console.log(
        `[mention] Routing to ${agentKey} | thread=${threadTs} context=${mapping.contextId}`,
      );

      let response: A2AResponse;
      try {
        response = await a2a.sendMessage(agentUrl, messageText, mapping.contextId);
      } catch (err) {
        console.error("[mention] Failed to contact agent:", err);
        await say({
          text: `:warning: Could not reach the *${agentKey}* agent. Please try again later.`,
          thread_ts: threadTs,
        });
        return;
      }

      if (response.error) {
        await say({
          text: `:x: Agent error: ${response.error.message}`,
          thread_ts: threadTs,
        });
        return;
      }

      const replyText = response.result
        ? extractTextFromTask(response.result)
        : "_No response from agent._";

      await say({ text: replyText, thread_ts: threadTs });
    },
  );
}
