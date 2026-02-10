import type { KnownBlock, Block } from "@slack/types";
import type { GoogleAuthService } from "../services/google-auth.js";
import type { MeetingStore } from "../services/meeting-store.js";

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
        metadata?: {
          event_type: string;
          event_payload: Record<string, unknown>;
        };
      }) => Promise<unknown>;
    };
  };
  /** Channel ID to post scheduled messages to */
  channelId: string;
  /** Base URL for the scrum-master A2A agent */
  scrumMasterUrl: string;
  /** Google auth service (optional — for meeting sync) */
  googleAuth?: GoogleAuthService;
  /** Slack user ID whose Google tokens to use for meeting sync */
  meetingSyncUserId?: string;
  /** Meeting store for deduplication (optional — for meeting sync) */
  meetingStore?: MeetingStore;
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
