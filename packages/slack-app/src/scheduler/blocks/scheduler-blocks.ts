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
    { type: "divider" },
    {
      type: "section",
      text: {
        type: "mrkdwn",
        text: `*Summary*\n${analysis.summary}`,
      },
    },
  ];

  if (analysis.decisions.length > 0) {
    blocks.push({ type: "divider" });
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text:
          `:bulb: *Key Decisions*\n` +
          analysis.decisions.map((d) => `> ${d}`).join("\n"),
      },
    });
  }

  if (analysis.actionItems.length > 0) {
    blocks.push({ type: "divider" });
    const lines = analysis.actionItems.map((item, i) => {
      let line = `${i + 1}. *${item.title}*`;
      if (item.assignee) line += ` — _${item.assignee}_`;
      if (item.priority) line += `  \`${item.priority}\``;
      if (item.deadline) line += `  :calendar: ${item.deadline}`;
      line += `\n     ${item.description}`;
      return line;
    });

    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: `:clipboard: *Action Items* (${analysis.actionItems.length})\n` + lines.join("\n"),
      },
    });
  } else {
    blocks.push({ type: "divider" });
    blocks.push({
      type: "section",
      text: {
        type: "mrkdwn",
        text: `:clipboard: *Action Items*\n_No action items detected — click *Create Tasks* if you see something worth tracking._`,
      },
    });
  }

  blocks.push({ type: "divider" });

  blocks.push({
    type: "actions",
    elements: [
      {
        type: "button",
        text: { type: "plain_text", text: ":white_check_mark: Create Tasks", emoji: true },
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

  const actionCount = analysis.actionItems.length;
  const text = actionCount > 0
    ? `Meeting Notes — ${meetingTitle}: ${actionCount} action item(s)`
    : `Meeting Notes — ${meetingTitle}`;
  return { blocks, text };
}
