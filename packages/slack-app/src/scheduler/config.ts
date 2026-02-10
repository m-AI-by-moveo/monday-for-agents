import cron from "node-cron";

// ---------------------------------------------------------------------------
// Scheduler configuration (env var parsing)
// ---------------------------------------------------------------------------

export interface SchedulerConfig {
  enabled: boolean;
  timezone: string;
  channelId: string;
  standup: { enabled: boolean; cron: string };
  staleCheck: { enabled: boolean; cron: string };
  weekly: { enabled: boolean; cron: string };
  meetingSync: { enabled: boolean; cron: string; slackUserId: string };
}

function envBool(key: string, fallback: boolean): boolean {
  const val = process.env[key];
  if (val === undefined || val === "") return fallback;
  return val.toLowerCase() === "true" || val === "1";
}

function envString(key: string, fallback: string): string {
  return process.env[key] || fallback;
}

function validateCron(expression: string, label: string): void {
  if (!cron.validate(expression)) {
    throw new Error(
      `[scheduler] Invalid cron expression for ${label}: "${expression}"`,
    );
  }
}

export function loadSchedulerConfig(): SchedulerConfig {
  const channelId = envString("SLACK_CHANNEL_ID", "");
  const masterEnabled = envBool("SCHEDULER_ENABLED", true);

  // Disable scheduler if no channel is configured
  const enabled = masterEnabled && channelId !== "";

  const timezone = envString("SCHEDULER_TIMEZONE", "Asia/Jerusalem");

  const standupCron = envString("SCHEDULER_STANDUP_CRON", "0 9 * * 1-5");
  const staleCheckCron = envString("SCHEDULER_STALE_CHECK_CRON", "*/30 * * * *");
  const weeklyCron = envString("SCHEDULER_WEEKLY_CRON", "0 9 * * 1");

  const meetingSyncCron = envString("SCHEDULER_MEETING_SYNC_CRON", "*/15 * * * *");

  // Validate all cron expressions at startup
  if (enabled) {
    validateCron(standupCron, "SCHEDULER_STANDUP_CRON");
    validateCron(staleCheckCron, "SCHEDULER_STALE_CHECK_CRON");
    validateCron(weeklyCron, "SCHEDULER_WEEKLY_CRON");
    validateCron(meetingSyncCron, "SCHEDULER_MEETING_SYNC_CRON");
  }

  return {
    enabled,
    timezone,
    channelId,
    standup: {
      enabled: envBool("SCHEDULER_STANDUP_ENABLED", true),
      cron: standupCron,
    },
    staleCheck: {
      enabled: envBool("SCHEDULER_STALE_CHECK_ENABLED", true),
      cron: staleCheckCron,
    },
    weekly: {
      enabled: envBool("SCHEDULER_WEEKLY_ENABLED", true),
      cron: weeklyCron,
    },
    meetingSync: {
      enabled: envBool("SCHEDULER_MEETING_SYNC_ENABLED", false),
      cron: meetingSyncCron,
      slackUserId: envString("MEETING_SYNC_SLACK_USER_ID", ""),
    },
  };
}
