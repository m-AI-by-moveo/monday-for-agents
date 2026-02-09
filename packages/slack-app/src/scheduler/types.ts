import type { KnownBlock, Block } from "@slack/bolt";

// ---------------------------------------------------------------------------
// Scheduler types
// ---------------------------------------------------------------------------

export interface ScheduledJobContext {
  /** Slack WebClient for posting messages */
  slackClient: {
    chat: {
      postMessage: (args: {
        channel: string;
        text: string;
        blocks?: (KnownBlock | Block)[];
      }) => Promise<unknown>;
    };
  };
  /** Channel ID to post scheduled messages to */
  channelId: string;
  /** Base URL for the scrum-master A2A agent */
  scrumMasterUrl: string;
}

export interface ScheduledJobResult {
  /** Whether the job executed successfully */
  success: boolean;
  /** Whether a Slack message was posted (some jobs suppress no-op runs) */
  posted: boolean;
  /** Optional error message on failure */
  error?: string;
}

export interface ScheduledJobDefinition {
  /** Unique identifier for this job */
  id: string;
  /** Human-readable name */
  name: string;
  /** Cron expression for scheduling */
  cron: string;
  /** Whether this job is enabled */
  enabled: boolean;
  /** The job's execute function */
  execute: (ctx: ScheduledJobContext) => Promise<ScheduledJobResult>;
}

export interface JobStatus {
  id: string;
  name: string;
  enabled: boolean;
  cron: string;
  running: boolean;
  lastRun: Date | null;
  lastResult: ScheduledJobResult | null;
  consecutiveFailures: number;
}

export interface SlackMessagePayload {
  channel: string;
  text: string;
  blocks?: (KnownBlock | Block)[];
}
