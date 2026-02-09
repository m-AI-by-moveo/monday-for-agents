/**
 * Shared Block Kit builder functions for rich Slack messages.
 *
 * Every function returns a tuple of [blocks, fallbackText] so callers
 * can pass `{ blocks, text }` to `say()` / `respond()`.
 */

import type { KnownBlock, Block } from "@slack/types";
import type { JobStatus } from "../scheduler/types.js";

// ---------------------------------------------------------------------------
// Markdown → Slack mrkdwn conversion
// ---------------------------------------------------------------------------

/**
 * Convert GitHub-flavored Markdown (from LLM output) to Slack mrkdwn.
 *
 * Key differences:
 * - Bold: **text** → *text*
 * - Headings: ## text → *text*
 * - Strikethrough is the same (~text~)
 * - Links are the same ([text](url))
 */
function markdownToMrkdwn(md: string): string {
  return (
    md
      // Headings → bold (must come before bold conversion)
      .replace(/^#{1,6}\s+(.+)$/gm, "*$1*")
      // Bold: **text** → *text*  (avoid converting already-single *)
      .replace(/\*\*(.+?)\*\*/g, "*$1*")
  );
}

// ---------------------------------------------------------------------------
// Agent response
// ---------------------------------------------------------------------------

export function agentResponseBlocks(
  agentName: string,
  responseText: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const converted = markdownToMrkdwn(responseText);
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text: converted },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: `:robot_face: Response from *${agentName}*`,
        },
      ],
    },
  ];
  return { blocks, text: responseText };
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

export function errorBlocks(
  message: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const text = `:x: ${message}`;
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
  ];
  return { blocks, text };
}

// ---------------------------------------------------------------------------
// Warning (unreachable agent, etc.)
// ---------------------------------------------------------------------------

export function warningBlocks(
  message: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const text = `:warning: ${message}`;
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
  ];
  return { blocks, text };
}

// ---------------------------------------------------------------------------
// Agent list (/agents command)
// ---------------------------------------------------------------------------

export function agentListBlocks(
  agents: Record<string, string>,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const lines = Object.entries(agents).map(
    ([name, url]) => `*${name}*  \u2192  \`${url}\``,
  );
  const listText = lines.join("\n");
  const fallback = `Registered Agents: ${Object.keys(agents).join(", ")}`;

  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":robot_face: Registered Agents", emoji: true },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: listText },
    },
  ];
  return { blocks, text: fallback };
}

// ---------------------------------------------------------------------------
// Status dashboard (/status command)
// ---------------------------------------------------------------------------

export function statusDashboardBlocks(
  statusText: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":bar_chart: Board Status", emoji: true },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: statusText },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: "Source: *Scrum Master* agent",
        },
      ],
    },
  ];
  return { blocks, text: statusText };
}

// ---------------------------------------------------------------------------
// Loading indicator
// ---------------------------------------------------------------------------

export function loadingBlocks(
  message = "Processing your request...",
): { blocks: (KnownBlock | Block)[]; text: string } {
  const text = `:hourglass_flowing_sand: ${message}`;
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
  ];
  return { blocks, text };
}

// ---------------------------------------------------------------------------
// No response fallback
// ---------------------------------------------------------------------------

export function noResponseBlocks(): { blocks: (KnownBlock | Block)[]; text: string } {
  const text = "_No response from agent._";
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
  ];
  return { blocks, text };
}

// ---------------------------------------------------------------------------
// Scheduler status (/scheduler command)
// ---------------------------------------------------------------------------

function relativeTime(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

export function schedulerStatusBlocks(
  jobs: JobStatus[],
): { blocks: (KnownBlock | Block)[]; text: string } {
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":gear: Scheduler Status", emoji: true },
    },
  ];

  for (const job of jobs) {
    const status = job.enabled ? ":white_check_mark: Enabled" : ":no_entry_sign: Disabled";
    const running = job.running ? " :runner: Running now" : "";
    const lastRun = job.lastRun ? relativeTime(job.lastRun) : "Never";

    let resultLine = "";
    if (job.lastResult) {
      resultLine = job.lastResult.success
        ? "\nLast result: :white_check_mark: Success"
        : `\nLast result: :x: Failed — ${job.lastResult.error ?? "unknown error"}`;
    }

    const failureLine =
      job.consecutiveFailures > 0
        ? `\n:warning: Consecutive failures: ${job.consecutiveFailures}`
        : "";

    const text = `*${job.name}*\n${status}${running}\nCron: \`${job.cron}\`\nLast run: ${lastRun}${resultLine}${failureLine}`;

    blocks.push({
      type: "section",
      text: { type: "mrkdwn", text },
    });
  }

  const fallback = `Scheduler Status: ${jobs.map((j) => `${j.name} (${j.enabled ? "enabled" : "disabled"})`).join(", ")}`;
  return { blocks, text: fallback };
}
