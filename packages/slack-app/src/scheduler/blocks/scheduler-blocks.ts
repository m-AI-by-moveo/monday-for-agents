/**
 * Block Kit builders for scheduled Slack posts.
 */

import type { KnownBlock, Block } from "@slack/types";

// ---------------------------------------------------------------------------
// Daily standup
// ---------------------------------------------------------------------------

export function standupBlocks(
  text: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":sunrise: Daily Standup", emoji: true },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: ":robot_face: Automated report from *Scrum Master*",
        },
      ],
    },
  ];
  return { blocks, text };
}

// ---------------------------------------------------------------------------
// Stale task alert
// ---------------------------------------------------------------------------

export function staleTaskBlocks(
  text: string,
  boardId?: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const boardUrl = boardId
    ? `https://moveogroup.monday.com/boards/${boardId}`
    : "";

  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":warning: Stale Tasks Detected", emoji: true },
    },
    ...(boardUrl
      ? [{
          type: "section" as const,
          text: { type: "mrkdwn" as const, text: `<${boardUrl}|View Board>` },
        }]
      : []),
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: ":robot_face: Automated alert from *Scrum Master*",
        },
      ],
    },
  ];
  return { blocks, text };
}

// ---------------------------------------------------------------------------
// Weekly summary
// ---------------------------------------------------------------------------

export function weeklySummaryBlocks(
  text: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":calendar: Weekly Summary", emoji: true },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text },
    },
    {
      type: "context",
      elements: [
        {
          type: "mrkdwn",
          text: ":robot_face: Automated report from *Scrum Master*",
        },
      ],
    },
  ];
  return { blocks, text };
}
