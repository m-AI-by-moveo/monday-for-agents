import type { App, AllMiddlewareArgs, SlackEventMiddlewareArgs } from "@slack/bolt";
import type { WebClient } from "@slack/web-api";
import { v4 as uuidv4 } from "uuid";
import { IntentRouter, type IntentType } from "../services/intent-router.js";
import {
  handleCreateTask,
  handleBoardStatus,
  handleMeetingSync,
  handleCalendar,
  handleDrive,
  handleAgentChat,
  type IntentContext,
} from "./intent-handlers.js";
import { loadingBlocks } from "../ui/block-builder.js";
import type { GoogleServices } from "./commands.js";
import type { MeetingStore } from "../services/meeting-store.js";

// ---------------------------------------------------------------------------
// State — in-memory mapping between Slack threads and A2A context IDs
// ---------------------------------------------------------------------------

export interface ThreadMapping {
  contextId: string;
  agentKey: string;
  intent?: IntentType;
}

/** Map from Slack thread_ts to A2A context metadata */
export const threadMap = new Map<string, ThreadMapping>();

// ---------------------------------------------------------------------------
// Bot user ID + mention resolution (unchanged)
// ---------------------------------------------------------------------------

/** Cached bot user ID – resolved once on first mention. */
let botUserId: string | null = null;

/** Cached mapping of Slack user ID → display name. */
const userNameCache = new Map<string, string>();

let staticMapLoaded = false;

function loadStaticUserMap(): void {
  if (staticMapLoaded) return;
  staticMapLoaded = true;
  const raw = process.env.SLACK_USER_MAP;
  if (!raw) return;
  try {
    const map = JSON.parse(raw) as Record<string, string>;
    for (const [id, name] of Object.entries(map)) {
      userNameCache.set(id, name);
    }
    console.log(`[mention] Loaded ${Object.keys(map).length} static user mapping(s) from SLACK_USER_MAP`);
  } catch {
    console.warn("[mention] Failed to parse SLACK_USER_MAP env var");
  }
}

async function ensureUserCache(client: WebClient): Promise<void> {
  loadStaticUserMap();
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
    console.log(`[mention] Cached ${userNameCache.size} Slack users from API`);
  } catch (err: any) {
    const errMsg = err?.data?.error || err?.message;
    if (errMsg === "missing_scope") {
      console.warn(
        "[mention] users:read scope missing. Using static SLACK_USER_MAP. " +
        "Add users:read scope and reinstall the app for automatic resolution.",
      );
    } else {
      console.warn(`[mention] Could not load user list: ${errMsg}`);
    }
  }
}

export async function resolveMentions(
  client: WebClient,
  text: string,
): Promise<string> {
  if (!botUserId) {
    const auth = await client.auth.test();
    botUserId = auth.user_id as string;
  }

  await ensureUserCache(client);

  const mentionRegex = /<@([A-Z0-9]+)>/g;
  let result = text;
  let match: RegExpExecArray | null;

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
// Dependencies interface
// ---------------------------------------------------------------------------

export interface MentionHandlerDeps {
  googleServices?: GoogleServices | null;
  meetingStore?: MeetingStore | null;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

const intentRouter = new IntentRouter();

export function registerMentionHandler(app: App, deps: MentionHandlerDeps = {}): void {
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

      const threadTs = event.thread_ts ?? event.ts;

      // Classify intent
      const { blocks: loadBlocks, text: loadText } = loadingBlocks("Thinking...");
      await say({ blocks: loadBlocks, text: loadText, thread_ts: threadTs });

      const { intent, agentKey } = await intentRouter.classify(messageText);
      console.log(`[mention] Intent: ${intent} | Agent: ${agentKey} | thread=${threadTs}`);

      // Store intent in thread mapping for continuations
      let mapping = threadMap.get(threadTs);
      if (!mapping) {
        mapping = { contextId: uuidv4(), agentKey, intent };
        threadMap.set(threadTs, mapping);
      } else {
        mapping.intent = intent;
        mapping.agentKey = agentKey;
      }

      const ctx: IntentContext = {
        say,
        client,
        event: {
          ts: event.ts,
          thread_ts: event.thread_ts,
          user: event.user,
          channel: event.channel,
          text: event.text,
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
    },
  );
}
