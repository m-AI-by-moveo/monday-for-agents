import { createA2AClient, extractTextFromTask } from "../../services/a2a-client.js";
import { staleTaskBlocks } from "../blocks/scheduler-blocks.js";
import type { ScheduledJobContext, ScheduledJobDefinition, ScheduledJobResult } from "../types.js";

// ---------------------------------------------------------------------------
// Stale task checker job
// ---------------------------------------------------------------------------

function getStaleCheckPrompt(): string {
  const boardId = process.env.MONDAY_BOARD_ID || "";
  if (!boardId) {
    console.warn("[stale-task-checker] MONDAY_BOARD_ID not set — agent may not know which board to check");
  }
  return `Check for stuck or stale tasks on Monday.com board ${boardId}. Call get_board_summary(board_id=${boardId}) first, then check for tasks that have been in the same status too long based on the thresholds. If there are NO stale tasks, respond with exactly: NO_STALE_TASKS`;
}

/** Sentinel value the scrum-master returns when nothing is stale */
const NO_STALE_SENTINEL = "NO_STALE_TASKS";

/** Patterns that indicate the agent failed to access the board */
const SUPPRESSED_PATTERNS = [
  "provide the board id",
  "provide the correct",
  "need a valid board",
  "need the board id",
  "could you please provide",
  "i need a",
  "i don't have access",
  "unable to locate",
];

async function execute(ctx: ScheduledJobContext): Promise<ScheduledJobResult> {
  const a2a = createA2AClient();

  const response = await a2a.sendMessage(ctx.scrumMasterUrl, getStaleCheckPrompt());

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

  // Suppress posting when the agent failed to access the board
  const lower = text.toLowerCase();
  if (SUPPRESSED_PATTERNS.some((p) => lower.includes(p))) {
    console.warn("[stale-task-checker] Suppressed confused agent response:", text.slice(0, 200));
    return {
      success: false,
      posted: false,
      error: "Agent could not access the board — check MONDAY_BOARD_ID and agent config",
    };
  }

  const boardId = process.env.MONDAY_BOARD_ID || "";
  const { blocks, text: fallback } = staleTaskBlocks(text, boardId);

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
