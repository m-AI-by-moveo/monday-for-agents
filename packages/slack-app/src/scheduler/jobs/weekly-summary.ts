import { createA2AClient, extractTextFromTask } from "../../services/a2a-client.js";
import { weeklySummaryBlocks } from "../blocks/scheduler-blocks.js";
import type { ScheduledJobContext, ScheduledJobDefinition, ScheduledJobResult } from "../types.js";

// ---------------------------------------------------------------------------
// Weekly summary job
// ---------------------------------------------------------------------------

const WEEKLY_PROMPT =
  "Generate a weekly summary report. Include overall progress, completed tasks this week, tasks still in progress, any blockers, and a brief outlook for next week.";

async function execute(ctx: ScheduledJobContext): Promise<ScheduledJobResult> {
  const a2a = createA2AClient();

  const response = await a2a.sendMessage(ctx.scrumMasterUrl, WEEKLY_PROMPT);

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
  const { blocks, text: fallback } = weeklySummaryBlocks(text);

  await ctx.slackClient.chat.postMessage({
    channel: ctx.channelId,
    text: fallback,
    blocks,
  });

  return { success: true, posted: true };
}

export function createWeeklySummaryJob(
  enabled: boolean,
  cronExpression: string,
): ScheduledJobDefinition {
  return {
    id: "weekly-summary",
    name: "Weekly Summary",
    cron: cronExpression,
    enabled,
    execute,
  };
}
