import { config } from "dotenv";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// Load .env from repo root (two levels up from packages/slack-app/)
const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, "../../../.env") });
import { App, ExpressReceiver } from "@slack/bolt";
import type { Request, Response } from "express";
import { registerMentionHandler } from "./handlers/mention.js";
import { registerThreadHandler } from "./handlers/thread.js";
import { registerCommands } from "./handlers/commands.js";

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const PORT = Number(process.env.PORT) || 3000;
const SLACK_BOT_TOKEN = process.env.SLACK_BOT_TOKEN;
const SLACK_SIGNING_SECRET = process.env.SLACK_SIGNING_SECRET;
const SLACK_APP_TOKEN = process.env.SLACK_APP_TOKEN;

if (!SLACK_BOT_TOKEN || !SLACK_SIGNING_SECRET) {
  console.error(
    "[slack-app] SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET are required",
  );
  process.exit(1);
}

// ---------------------------------------------------------------------------
// Receiver (Express-based so we can add custom routes)
// ---------------------------------------------------------------------------

const receiver = new ExpressReceiver({
  signingSecret: SLACK_SIGNING_SECRET,
});

// ---------------------------------------------------------------------------
// Agent notification webhook — POST /api/agent-notify
// ---------------------------------------------------------------------------

interface AgentNotifyBody {
  channel: string;
  text: string;
  thread_ts?: string;
  blocks?: Array<Record<string, unknown>>;
}

// We need the Bolt app reference to post messages, so we register the route
// after creating the app. The express router is available immediately though.
receiver.router.use("/api/agent-notify", (req: Request, _res: Response, next) => {
  // Only accept POST
  if (req.method !== "POST") {
    _res.status(405).json({ error: "Method not allowed" });
    return;
  }
  next();
});

// ---------------------------------------------------------------------------
// Bolt App
// ---------------------------------------------------------------------------

const useSocketMode = Boolean(SLACK_APP_TOKEN);

const app = new App({
  token: SLACK_BOT_TOKEN,
  ...(useSocketMode
    ? {
        socketMode: true,
        appToken: SLACK_APP_TOKEN,
      }
    : {
        receiver,
      }),
});

// ---------------------------------------------------------------------------
// Register handlers
// ---------------------------------------------------------------------------

registerMentionHandler(app);
registerThreadHandler(app);
registerCommands(app);

// ---------------------------------------------------------------------------
// Agent notification webhook route (needs `app.client` for posting)
// ---------------------------------------------------------------------------

receiver.router.post("/api/agent-notify", async (req: Request, res: Response) => {
  try {
    const body = req.body as AgentNotifyBody;

    if (!body.channel || !body.text) {
      res.status(400).json({ error: "channel and text are required" });
      return;
    }

    console.log(
      `[agent-notify] Posting to channel=${body.channel} thread=${body.thread_ts ?? "none"}`,
    );

    await app.client.chat.postMessage({
      token: SLACK_BOT_TOKEN,
      channel: body.channel,
      text: body.text,
      ...(body.blocks ? { blocks: body.blocks } : {}),
      ...(body.thread_ts ? { thread_ts: body.thread_ts } : {}),
    });

    res.status(200).json({ ok: true });
  } catch (err) {
    console.error("[agent-notify] Error posting message:", err);
    res.status(500).json({ error: "Failed to post message" });
  }
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

(async () => {
  if (useSocketMode) {
    await app.start();
    console.log(`[slack-app] Running in Socket Mode`);
  } else {
    await app.start(PORT);
    console.log(`[slack-app] Running on http://localhost:${PORT}`);
  }
  console.log("[slack-app] Handlers registered: mention, thread, commands, agent-notify");
})();
