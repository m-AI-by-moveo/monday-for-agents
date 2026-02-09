import { createA2AClient, extractTextFromTask } from "../../services/a2a-client.js";
import { staleTaskBlocks } from "../blocks/scheduler-blocks.js";
import type { ScheduledJobContext, ScheduledJobDefinition, ScheduledJobResult } from "../types.js";

// ---------------------------------------------------------------------------
// Stale task checker job
// ---------------------------------------------------------------------------

const STALE_CHECK_PROMPT =
  "Check for stuck or stale tasks on the board. If there are tasks that have been in the same status too long based on the thresholds, list them with details. If there are NO stale tasks, respond with exactly: NO_STALE_TASKS";

/** Sentinel value the scrum-master returns when nothing is stale */
const NO_STALE_SENTINEL = "NO_STALE_TASKS";

async function execute(ctx: ScheduledJobContext): Promise<ScheduledJobResult> {
  const a2a = createA2AClient();

  const response = await a2a.sendMessage(ctx.scrumMasterUrl, STALE_CHECK_PROMPT);

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

  // Suppress posting when no stale tasks are found
  if (text.includes(NO_STALE_SENTINEL)) {
    return { success: true, posted: false };
  }

  const { blocks, text: fallback } = staleTaskBlocks(text);

  await ctx.slackClient.chat.postMessage({
    channel: ctx.channelId,
    text: fallback,
    blocks,
  });

  return { success: true, posted: true };
}

export function createStaleTaskCheckerJob(
  enabled: boolean,
  cronExpression: string,
): ScheduledJobDefinition {
  return {
    id: "stale-task-checker",
    name: "Stale Task Checker",
    cron: cronExpression,
    enabled,
    execute,
  };
}
