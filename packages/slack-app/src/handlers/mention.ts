import type { App, AllMiddlewareArgs, SlackEventMiddlewareArgs } from "@slack/bolt";
import type { WebClient } from "@slack/web-api";
import { v4 as uuidv4 } from "uuid";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
  type A2AResponse,
} from "../services/a2a-client.js";
import {
  agentResponseBlocks,
  errorBlocks,
  warningBlocks,
  loadingBlocks,
  noResponseBlocks,
} from "../ui/block-builder.js";

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

/** Cached bot user ID – resolved once on first mention. */
let botUserId: string | null = null;

/** Cached mapping of Slack user ID → display name (populated lazily). */
const userNameCache = new Map<string, string>();

/**
 * Populate the user name cache from the full Slack user list.
 * This uses the `users.list` endpoint which only requires the `users:read`
 * scope — but if that scope is missing too, we fall back gracefully.
 */
async function ensureUserCache(client: WebClient): Promise<void> {
  if (userNameCache.size > 0) return;
  try {
    let cursor: string | undefined;
    do {
      const res = await client.users.list({ cursor, limit: 200 });
      for (const member of res.members ?? []) {
        if (member.id && !member.deleted) {
          const name =
            member.real_name ||
            member.profile?.display_name ||
            member.name ||
            member.id;
          userNameCache.set(member.id, name);
        }
      }
      cursor = res.response_metadata?.next_cursor || undefined;
    } while (cursor);
    console.log(`[mention] Cached ${userNameCache.size} Slack users`);
  } catch (err: any) {
    console.warn(
      `[mention] Could not load user list (${err?.data?.error || err?.message}). ` +
      "Add the 'users:read' scope to the Slack app to enable @mention resolution.",
    );
  }
}

/**
 * Replace the bot's own @mention with nothing, and resolve any other
 * <@USERID> mentions to the user's real name so the agent sees
 * "create a task for Or Bruchim" instead of "create a task for".
 */
async function resolveMentions(
  client: WebClient,
  text: string,
): Promise<string> {
  if (!botUserId) {
    const auth = await client.auth.test();
    botUserId = auth.user_id as string;
  }

  // Pre-load the full user list (cached after first call)
  await ensureUserCache(client);

  const mentionRegex = /<@([A-Z0-9]+)>/g;
  let result = text;
  let match: RegExpExecArray | null;

  // Collect all matches first (regex is stateful)
  const matches: Array<{ full: string; userId: string }> = [];
  while ((match = mentionRegex.exec(text)) !== null) {
    matches.push({ full: match[0], userId: match[1] });
  }

  for (const { full, userId } of matches) {
    if (userId === botUserId) {
      result = result.replace(full, "");
      continue;
    }
    const cached = userNameCache.get(userId);
    if (cached) {
      console.log(`[mention] Resolved <@${userId}> to "${cached}"`);
      result = result.replace(full, cached);
    } else {
      console.warn(`[mention] Unknown user <@${userId}>, keeping raw ID`);
      result = result.replace(full, `@${userId}`);
    }
  }

  return result.trim();
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
      client,
    }: AllMiddlewareArgs & SlackEventMiddlewareArgs<"app_mention">) => {
      const rawText = event.text ?? "";
      const messageText = await resolveMentions(client, rawText);

      if (!messageText) {
        await say({ text: "Hey! How can I help?", thread_ts: event.ts });
        return;
      }

      const agentKey = pickAgent(messageText);
      const agentUrl = AGENT_URLS[agentKey];
      if (!agentUrl) {
        const { blocks, text } = errorBlocks(`Unknown agent: ${agentKey}`);
        await say({ blocks, text, thread_ts: event.ts });
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

      // Post an immediate acknowledgment so the user knows we're working
      const { blocks: loadBlocks, text: loadText } = loadingBlocks(
        `Routing to *${agentKey}*... This may take a few minutes.`,
      );
      await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

      let response: A2AResponse;
      try {
        response = await a2a.sendMessage(agentUrl, messageText, mapping.contextId);
      } catch (err) {
        console.error("[mention] Failed to contact agent:", err);
        const { blocks, text } = warningBlocks(
          `Could not reach the *${agentKey}* agent. Please try again later.`,
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
        const { blocks, text } = agentResponseBlocks(agentKey, replyText);
        await say({ blocks, text, thread_ts: threadTs });
      } else {
        const { blocks, text } = noResponseBlocks();
        await say({ blocks, text, thread_ts: threadTs });
      }
    },
  );
}
