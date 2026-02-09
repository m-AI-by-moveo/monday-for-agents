import { createA2AClient, extractTextFromTask } from "../../services/a2a-client.js";
import { standupBlocks } from "../blocks/scheduler-blocks.js";
import type { ScheduledJobContext, ScheduledJobDefinition, ScheduledJobResult } from "../types.js";

// ---------------------------------------------------------------------------
// Daily standup job
// ---------------------------------------------------------------------------

const STANDUP_PROMPT =
  "Generate the daily standup report. Show what's in progress, what's blocked, recently completed tasks, and any action items.";

async function execute(ctx: ScheduledJobContext): Promise<ScheduledJobResult> {
  const a2a = createA2AClient();

  const response = await a2a.sendMessage(ctx.scrumMasterUrl, STANDUP_PROMPT);

  if (response.error) {
    return {
      success: false,
      posted: false,
      error: `A2A error: ${response.error.message}`,
    };
  }

  if (!response.result) {
    return {
      success: false,
      posted: false,
      error: "No result from scrum-master agent",
    };
  }

  const text = extractTextFromTask(response.result);
  const { blocks, text: fallback } = standupBlocks(text);

  await ctx.slackClient.chat.postMessage({
    channel: ctx.channelId,
    text: fallback,
    blocks,
  });

  return { success: true, posted: true };
}

export function createDailyStandupJob(
  enabled: boolean,
  cronExpression: string,
): ScheduledJobDefinition {
  return {
    id: "daily-standup",
    name: "Daily Standup",
    cron: cronExpression,
    enabled,
    execute,
  };
}
