import type { KnownBlock, Block } from "@slack/types";
import type { ExtractedTask } from "../services/task-extractor-agent.js";

export interface TaskPreviewMetadata {
  extractedTask: ExtractedTask;
  channelId: string;
  threadTs: string;
  userId: string;
  boardsJson?: string;
  usersJson?: string;
}

export function taskPreviewBlocks(
  extractedTask: ExtractedTask,
  metadata: TaskPreviewMetadata,
): {
  blocks: (KnownBlock | Block)[];
  text: string;
  metadata: { event_type: string; event_payload: Record<string, string> };
} {
  const text = `Task preview: ${extractedTask.taskName}`;

  const fields: string[] = [];
  if (extractedTask.taskName) fields.push(`*Task:* ${extractedTask.taskName}`);
  if (extractedTask.description) fields.push(`*Description:* ${extractedTask.description}`);
  if (extractedTask.assignee) fields.push(`*Assignee:* ${extractedTask.assignee}`);
  fields.push(`*Priority:* ${extractedTask.priority}`);
  fields.push(`*Status:* ${extractedTask.status}`);

  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: "Task Preview", emoji: true },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: fields.join("\n") },
    },
    {
      type: "actions",
      elements: [
        {
          type: "button",
          text: { type: "plain_text", text: "Create Task", emoji: true },
          style: "primary",
          action_id: "mention_create_task",
          value: "create",
        },
        {
          type: "button",
          text: { type: "plain_text", text: "Edit", emoji: true },
          action_id: "mention_edit_task",
          value: "edit",
        },
        {
          type: "button",
          text: { type: "plain_text", text: "Cancel", emoji: true },
          style: "danger",
          action_id: "mention_cancel_task",
          value: "cancel",
        },
      ],
    },
  ];

  return {
    blocks,
    text,
    metadata: {
      event_type: "mention_task_preview",
      event_payload: {
        extracted_task: JSON.stringify(extractedTask),
        channel_id: metadata.channelId,
        thread_ts: metadata.threadTs,
        user_id: metadata.userId,
        boards_json: metadata.boardsJson ?? "[]",
        users_json: metadata.usersJson ?? "[]",
      },
    },
  };
}
