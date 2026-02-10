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

// ---------------------------------------------------------------------------
// Meeting preview (action items extracted from transcript)
// ---------------------------------------------------------------------------

import type { MeetingAnalysis } from "../../services/meeting-notes-agent.js";

export function meetingPreviewBlocks(
  meetingTitle: string,
  analysis: MeetingAnalysis,
  eventId: string,
): { blocks: (KnownBlock | Block)[]; text: string } {
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: {
        type: "plain_text",
        text: `:memo: Meeting Notes — ${meetingTitle}`,
        emoji: true,
      },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: analysis.summary },
    },
  ];

  if (analysis.decisions.length > 0) {
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text:
          "*Key Decisions*\n" +
          analysis.decisions.map((d) => `• ${d}`).join("\n"),
      },
    });
  }

  if (analysis.actionItems.length > 0) {
    const lines = analysis.actionItems.map((item, i) => {
      let line = `${i + 1}. *${item.title}*`;
      if (item.assignee) line += ` — _${item.assignee}_`;
      if (item.priority) line += ` [${item.priority}]`;
      if (item.deadline) line += ` (due: ${item.deadline})`;
      line += `\n    ${item.description}`;
      return line;
    });

    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: "*Action Items*\n" + lines.join("\n"),
      },
    });
  }

  blocks.push({
    type: "actions",
    elements: [
      {
        type: "button",
        text: { type: "plain_text", text: "Create Tasks", emoji: true },
        style: "primary",
        action_id: "meeting_approve",
        value: eventId,
      },
      {
        type: "button",
        text: { type: "plain_text", text: "Dismiss", emoji: true },
        action_id: "meeting_dismiss",
        value: eventId,
      },
    ],
  } as any);

  blocks.push({
    type: "context",
    elements: [
      {
        type: "mrkdwn",
        text: ":robot_face: Extracted from meeting transcript",
      },
    ],
  });

  const text = `Meeting Notes — ${meetingTitle}: ${analysis.actionItems.length} action item(s)`;
  return { blocks, text };
}
