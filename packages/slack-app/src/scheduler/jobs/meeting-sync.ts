import { MeetingSyncService } from "../../services/meeting-sync.js";
import { MeetingNotesAgent } from "../../services/meeting-notes-agent.js";
import type { ScheduledJobContext, ScheduledJobDefinition, ScheduledJobResult } from "../types.js";

// ---------------------------------------------------------------------------
// Meeting sync job
// ---------------------------------------------------------------------------

async function execute(ctx: ScheduledJobContext): Promise<ScheduledJobResult> {
  if (!ctx.googleAuth || !ctx.meetingSyncUserId || !ctx.meetingStore) {
    return {
      success: false,
      posted: false,
      error: "Google auth, meeting sync user, or meeting store not configured",
    };
  }

  const meetingNotesAgent = new MeetingNotesAgent();
  const syncService = new MeetingSyncService(
    ctx.googleAuth,
    ctx.meetingStore,
    meetingNotesAgent,
    ctx.slackClient,
    ctx.channelId,
  );

  const result = await syncService.checkRecentMeetings(ctx.meetingSyncUserId);

  if (result.errors.length > 0) {
    console.error("[meeting-sync] Errors:", result.errors);
  }

  return {
    success: result.errors.length === 0,
    posted: result.previewsPosted > 0,
    error:
      result.errors.length > 0
        ? result.errors.join("; ")
        : undefined,
  };
}

export function createMeetingSyncJob(
  enabled: boolean,
  cronExpression: string,
): ScheduledJobDefinition {
  return {
    id: "meeting-sync",
    name: "Meeting Notes Sync",
    cron: cronExpression,
    enabled,
    execute,
  };
}
