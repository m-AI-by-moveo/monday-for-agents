import { config } from "dotenv";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";

// Load .env from repo root (two levels up from packages/slack-app/)
const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, "../../../.env") });
import bolt from "@slack/bolt";
const { App, ExpressReceiver } = bolt;
import type { Request, Response } from "express";
import { registerMentionHandler } from "./handlers/mention.js";
import { registerThreadHandler } from "./handlers/thread.js";
import { registerCommands } from "./handlers/commands.js";
import type { GoogleServices } from "./handlers/commands.js";
import { loadSchedulerConfig } from "./scheduler/config.js";
import { createSchedulerService } from "./services/scheduler.js";
import { AGENT_URLS } from "./services/a2a-client.js";
import { createDailyStandupJob } from "./scheduler/jobs/daily-standup.js";
import { createStaleTaskCheckerJob } from "./scheduler/jobs/stale-task-checker.js";
import { createWeeklySummaryJob } from "./scheduler/jobs/weekly-summary.js";
import { GoogleTokenStore } from "./services/google-token-store.js";
import { GoogleAuthService } from "./services/google-auth.js";
import { GoogleCalendarService } from "./services/google-calendar.js";
import { GoogleDriveService } from "./services/google-drive.js";
import { MeetingStore } from "./services/meeting-store.js";
import { MeetingNotesAgent } from "./services/meeting-notes-agent.js";
import { MeetingSyncService } from "./services/meeting-sync.js";
import { MeetingSyncScheduler } from "./services/meeting-sync-scheduler.js";
import { registerActions, registerCreateTaskActions } from "./handlers/actions.js";

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
registerCreateTaskActions(app);

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
// Google OAuth2 integration (optional — enabled when GOOGLE_CLIENT_ID is set)
// ---------------------------------------------------------------------------

let googleServices: GoogleServices | null = null;

if (process.env.GOOGLE_CLIENT_ID) {
  const tokenStore = new GoogleTokenStore();
  const googleAuth = new GoogleAuthService(tokenStore);
  const googleCalendar = new GoogleCalendarService(googleAuth);
  const googleDrive = new GoogleDriveService(googleAuth);
  googleServices = { auth: googleAuth, calendar: googleCalendar, drive: googleDrive };

  receiver.router.get("/api/google/callback", async (req: Request, res: Response) => {
    try {
      const code = req.query.code as string;
      const state = req.query.state as string;

      if (!code || !state) {
        res.status(400).send("Missing code or state parameter.");
        return;
      }

      const slackUserId = await googleAuth.handleCallback(code, state);
      res.send(
        `<html><body><h2>Google account connected!</h2><p>You can close this tab and return to Slack. (User: ${slackUserId})</p></body></html>`,
      );
    } catch (err) {
      console.error("[google-callback] Error:", err);
      res.status(400).send("OAuth callback failed. Please try /google connect again.");
    }
  });

  console.log("[slack-app] Google integration enabled");
} else {
  console.log("[slack-app] Google integration disabled (GOOGLE_CLIENT_ID not set)");
}

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------

(async () => {
  if (useSocketMode) {
    await app.start();
    // In Socket Mode, Bolt uses WebSockets — start Express separately for HTTP routes
    // (OAuth callback, agent-notify webhook, etc.)
    receiver.app.listen(PORT, () => {
      console.log(`[slack-app] HTTP routes on http://localhost:${PORT}`);
    });
    console.log(`[slack-app] Running in Socket Mode`);
  } else {
    await app.start(PORT);
    console.log(`[slack-app] Running on http://localhost:${PORT}`);
  }
  console.log("[slack-app] Handlers registered: mention, thread, commands, agent-notify");

  // -------------------------------------------------------------------------
  // Scheduled automations & /scheduler command
  // -------------------------------------------------------------------------

  const schedulerConfig = loadSchedulerConfig();

  // Meeting store + smart scheduler (available even without cron scheduler)
  let meetingStore: MeetingStore | null = null;
  let meetingSyncScheduler: MeetingSyncScheduler | null = null;

  if (
    schedulerConfig.meetingSync.enabled &&
    schedulerConfig.meetingSync.slackUserId &&
    googleServices
  ) {
    meetingStore = new MeetingStore();
    registerActions(app, meetingStore);

    const meetingNotesAgent = new MeetingNotesAgent();
    const syncService = new MeetingSyncService(
      googleServices.auth,
      meetingStore,
      meetingNotesAgent,
      app.client,
      schedulerConfig.channelId,
    );

    meetingSyncScheduler = new MeetingSyncScheduler(
      googleServices.auth,
      schedulerConfig.meetingSync.slackUserId,
      meetingStore,
      syncService,
    );

    await meetingSyncScheduler.start();
    console.log("[slack-app] Meeting sync actions registered");
    console.log(
      `[slack-app] Calendar-aware meeting sync enabled for user ${schedulerConfig.meetingSync.slackUserId}`,
    );
  }

  if (schedulerConfig.enabled) {
    const scheduler = createSchedulerService({
      slackClient: app.client,
      channelId: schedulerConfig.channelId,
      scrumMasterUrl: AGENT_URLS["scrum-master"],
    });

    scheduler.register(
      createDailyStandupJob(
        schedulerConfig.standup.enabled,
        schedulerConfig.standup.cron,
      ),
    );
    scheduler.register(
      createStaleTaskCheckerJob(
        schedulerConfig.staleCheck.enabled,
        schedulerConfig.staleCheck.cron,
      ),
    );
    scheduler.register(
      createWeeklySummaryJob(
        schedulerConfig.weekly.enabled,
        schedulerConfig.weekly.cron,
      ),
    );

    scheduler.startAll(schedulerConfig.timezone);

    registerCommands(app, scheduler, googleServices, meetingStore);

    const gracefulShutdown = () => {
      console.log("[slack-app] Shutting down...");
      scheduler.stopAll();
      if (meetingSyncScheduler) meetingSyncScheduler.stop();
      if (meetingStore) meetingStore.close();
      process.exit(0);
    };

    process.on("SIGTERM", gracefulShutdown);
    process.on("SIGINT", gracefulShutdown);
  } else {
    registerCommands(app, null, googleServices, meetingStore);
    console.log("[slack-app] Scheduler disabled (SCHEDULER_ENABLED=false or SLACK_CHANNEL_ID empty)");
  }
})();
