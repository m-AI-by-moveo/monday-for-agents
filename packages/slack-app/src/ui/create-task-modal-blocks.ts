import type { ExtractedTask } from "../services/task-extractor-agent.js";
import type { MondayBoard, MondayUser } from "../services/monday-client.js";

export interface CreateTaskModalMetadata {
  channelId: string;
  userId: string;
}

export function buildCreateTaskLoadingModal(metadata: CreateTaskModalMetadata) {
  return {
    type: "modal" as const,
    callback_id: "create_task_submit",
    title: { type: "plain_text" as const, text: "Create Task" },
    close: { type: "plain_text" as const, text: "Cancel" },
    private_metadata: JSON.stringify(metadata),
    blocks: [
      {
        type: "section",
        text: {
          type: "mrkdwn",
          text: ":hourglass_flowing_sand: Reading conversation and extracting task details...",
        },
      },
    ],
  };
}

export function buildCreateTaskModal(
  extractedTask: ExtractedTask,
  boards: MondayBoard[],
  metadata: CreateTaskModalMetadata,
  users: MondayUser[] = [],
) {
  const defaultBoardId = process.env.MONDAY_BOARD_ID ?? "";

  const blocks: any[] = [];

  // Task Name (required)
  blocks.push({
    type: "input",
    block_id: "task_name_block",
    label: { type: "plain_text", text: "Task Name" },
    element: {
      type: "plain_text_input",
      action_id: "task_name_input",
      initial_value: extractedTask.taskName,
      placeholder: { type: "plain_text", text: "Enter task name" },
    },
  });

  // Description (optional)
  blocks.push({
    type: "input",
    block_id: "description_block",
    label: { type: "plain_text", text: "Description" },
    element: {
      type: "plain_text_input",
      action_id: "description_input",
      multiline: true,
      initial_value: extractedTask.description,
      placeholder: { type: "plain_text", text: "Enter task description" },
    },
    optional: true,
  });

  // Board selector
  if (boards.length > 0) {
    const boardOptions = boards.map((b) => ({
      text: { type: "plain_text" as const, text: b.name.substring(0, 75) },
      value: b.id,
    }));

    const boardElement: any = {
      type: "static_select",
      action_id: "board_select",
      placeholder: { type: "plain_text", text: "Select a board" },
      options: boardOptions,
    };

    const initialOption = boardOptions.find((o) => o.value === defaultBoardId);
    if (initialOption) {
      boardElement.initial_option = initialOption;
    }

    blocks.push({
      type: "input",
      block_id: "board_block",
      label: { type: "plain_text", text: "Board" },
      element: boardElement,
    });
  }

  // Assignee (optional)
  if (users.length > 0) {
    const userOptions = users.map((u) => ({
      text: { type: "plain_text" as const, text: u.name.substring(0, 75) },
      value: u.id,
    }));

    const assigneeElement: any = {
      type: "static_select",
      action_id: "assignee_select",
      placeholder: { type: "plain_text", text: "Select assignee" },
      options: userOptions,
    };

    // Try to pre-select based on LLM-extracted name (case-insensitive partial match)
    if (extractedTask.assignee) {
      const lowerAssignee = extractedTask.assignee.toLowerCase();
      const match = userOptions.find((o) =>
        o.text.text.toLowerCase().includes(lowerAssignee) ||
        lowerAssignee.includes(o.text.text.toLowerCase()),
      );
      if (match) {
        assigneeElement.initial_option = match;
      }
    }

    blocks.push({
      type: "input",
      block_id: "assignee_block",
      label: { type: "plain_text", text: "Assignee" },
      element: assigneeElement,
      optional: true,
    });
  } else {
    blocks.push({
      type: "input",
      block_id: "assignee_block",
      label: { type: "plain_text", text: "Assignee" },
      element: {
        type: "plain_text_input",
        action_id: "assignee_input",
        initial_value: extractedTask.assignee,
        placeholder: { type: "plain_text", text: "Person responsible" },
      },
      optional: true,
    });
  }

  // Status selector
  const statusOptions = ["To Do", "Working on it", "In Progress", "Done"].map((s) => ({
    text: { type: "plain_text" as const, text: s },
    value: s,
  }));

  blocks.push({
    type: "input",
    block_id: "status_block",
    label: { type: "plain_text", text: "Status" },
    element: {
      type: "static_select",
      action_id: "status_select",
      options: statusOptions,
      initial_option: statusOptions.find((o) => o.value === extractedTask.status) ?? statusOptions[0],
    },
  });

  // Priority selector
  const priorityOptions = ["Low", "Medium", "High", "Critical"].map((p) => ({
    text: { type: "plain_text" as const, text: p },
    value: p,
  }));

  blocks.push({
    type: "input",
    block_id: "priority_block",
    label: { type: "plain_text", text: "Priority" },
    element: {
      type: "static_select",
      action_id: "priority_select",
      options: priorityOptions,
      initial_option: priorityOptions.find((o) => o.value === extractedTask.priority) ?? priorityOptions[1],
    },
  });

  return {
    type: "modal" as const,
    callback_id: "create_task_submit",
    title: { type: "plain_text" as const, text: "Create Task" },
    submit: { type: "plain_text" as const, text: "Create Task" },
    close: { type: "plain_text" as const, text: "Cancel" },
    private_metadata: JSON.stringify(metadata),
    blocks,
  };
}
