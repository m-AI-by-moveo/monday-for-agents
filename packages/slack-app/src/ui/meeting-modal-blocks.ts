import type { MeetingAnalysis } from "../services/meeting-notes-agent.js";
import type { MondayBoard } from "../services/monday-client.js";

export interface MeetingModalMetadata {
  eventId: string;
  channelId: string;
  messageTs: string;
}

const MAX_ACTION_ITEM_SLOTS = 5;

export function buildMeetingEditModal(
  analysis: MeetingAnalysis,
  boards: MondayBoard[],
  suggestedBoardId: string | undefined,
  metadata: MeetingModalMetadata,
) {
  const defaultBoardId = suggestedBoardId ?? process.env.MONDAY_BOARD_ID ?? "";

  const boardOptions = boards.map((b) => ({
    text: { type: "plain_text" as const, text: b.name.substring(0, 75) },
    value: b.id,
  }));

  const blocks: any[] = [];

  // Board selector
  if (boardOptions.length > 0) {
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
      label: { type: "plain_text", text: "Monday.com Board" },
      element: boardElement,
    });
  }

  // Summary
  blocks.push({
    type: "input",
    block_id: "summary_block",
    label: { type: "plain_text", text: "Summary" },
    element: {
      type: "plain_text_input",
      action_id: "summary_input",
      multiline: true,
      initial_value: analysis.summary,
    },
  });

  // Key Decisions
  blocks.push({
    type: "input",
    block_id: "decisions_block",
    label: { type: "plain_text", text: "Key Decisions (one per line)" },
    element: {
      type: "plain_text_input",
      action_id: "decisions_input",
      multiline: true,
      initial_value: analysis.decisions.join("\n"),
    },
    optional: true,
  });

  // Divider before action items
  blocks.push({ type: "divider" });

  blocks.push({
    type: "header",
    text: { type: "plain_text", text: "Action Items", emoji: true },
  });

  // Action item slots
  const itemCount = Math.max(analysis.actionItems.length, 1);
  const slotsToRender = Math.min(Math.max(itemCount, MAX_ACTION_ITEM_SLOTS), MAX_ACTION_ITEM_SLOTS);

  for (let i = 0; i < slotsToRender; i++) {
    const item = analysis.actionItems[i];
    const idx = i + 1;

    blocks.push({
      type: "input",
      block_id: `action_title_${i}`,
      label: { type: "plain_text", text: `Task ${idx} — Title` },
      element: {
        type: "plain_text_input",
        action_id: `action_title_input_${i}`,
        initial_value: item?.title ?? "",
        placeholder: { type: "plain_text", text: "Task title (leave empty to skip)" },
      },
      optional: true,
    });

    blocks.push({
      type: "input",
      block_id: `action_desc_${i}`,
      label: { type: "plain_text", text: `Task ${idx} — Description` },
      element: {
        type: "plain_text_input",
        action_id: `action_desc_input_${i}`,
        multiline: true,
        initial_value: item?.description ?? "",
      },
      optional: true,
    });

    blocks.push({
      type: "input",
      block_id: `action_assignee_${i}`,
      label: { type: "plain_text", text: `Task ${idx} — Assignee` },
      element: {
        type: "plain_text_input",
        action_id: `action_assignee_input_${i}`,
        initial_value: item?.assignee ?? "",
      },
      optional: true,
    });
  }

  return {
    type: "modal" as const,
    callback_id: "meeting_edit_submit",
    title: { type: "plain_text" as const, text: "Edit Meeting Tasks" },
    submit: { type: "plain_text" as const, text: "Create Tasks" },
    close: { type: "plain_text" as const, text: "Cancel" },
    private_metadata: JSON.stringify(metadata),
    blocks,
  };
}
