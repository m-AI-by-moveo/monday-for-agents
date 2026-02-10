import type { App } from "@slack/bolt";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
} from "../services/a2a-client.js";
import type { MeetingStore } from "../services/meeting-store.js";
import type { MeetingAnalysis } from "../services/meeting-notes-agent.js";
import { fetchBoards } from "../services/monday-client.js";
import { buildMeetingEditModal, type MeetingModalMetadata } from "../ui/meeting-modal-blocks.js";
import type { CreateTaskModalMetadata } from "../ui/create-task-modal-blocks.js";

export function registerActions(
  app: App,
  meetingStore: MeetingStore,
): void {
  // -------------------------------------------------------------------------
  // meeting_approve — Open editable modal instead of creating tasks directly
  // -------------------------------------------------------------------------

  app.action("meeting_approve", async ({ ack, body, client }) => {
    await ack();

    const action = (body as any).actions?.[0];
    const eventId = action?.value;
    if (!eventId) return;

    const message = (body as any).message;
    const channel = (body as any).channel?.id;
    const messageTs = message?.ts;
    const triggerId = (body as any).trigger_id;

    if (!triggerId) {
      console.error("[actions] No trigger_id available for modal");
      return;
    }

    // Retrieve stored analysis from message metadata
    let analysis: MeetingAnalysis | null = null;
    let suggestedBoardId: string | undefined;
    try {
      const metadata = message?.metadata;
      if (metadata?.event_payload?.analysis) {
        analysis = JSON.parse(metadata.event_payload.analysis as string);
      }
      if (metadata?.event_payload?.suggested_board_id) {
        suggestedBoardId = metadata.event_payload.suggested_board_id as string;
      }
    } catch {
      // Fall through — will report error
    }

    if (!analysis) {
      if (channel && messageTs) {
        await client.chat.update({
          channel,
          ts: messageTs,
          text: ":warning: Could not retrieve meeting analysis. Please try /meeting-sync again.",
          blocks: [],
        });
      }
      return;
    }

    // Use suggestedBoardId from analysis if not in metadata
    if (!suggestedBoardId && analysis.suggestedBoardId) {
      suggestedBoardId = analysis.suggestedBoardId;
    }

    // Fetch boards for the dropdown (cached, fast)
    let boards: { id: string; name: string }[] = [];
    try {
      boards = await fetchBoards();
    } catch (err: any) {
      console.warn("[actions] Could not fetch boards:", err.message);
    }

    const modalMetadata: MeetingModalMetadata = {
      eventId,
      channelId: channel ?? "",
      messageTs: messageTs ?? "",
    };

    const view = buildMeetingEditModal(analysis, boards, suggestedBoardId, modalMetadata);

    try {
      await client.views.open({
        trigger_id: triggerId,
        view: view as any,
      });
    } catch (err: any) {
      console.error("[actions] Failed to open modal:", err.message);
      if (channel && messageTs) {
        await client.chat.update({
          channel,
          ts: messageTs,
          text: `:x: Failed to open edit modal: ${err.message ?? "Unknown error"}`,
          blocks: [],
        });
      }
    }
  });

  // -------------------------------------------------------------------------
  // meeting_edit_submit — Handle modal submission
  // -------------------------------------------------------------------------

  app.view("meeting_edit_submit", async ({ ack, view, body, client }) => {
    await ack();

    const metadata: MeetingModalMetadata = JSON.parse(view.private_metadata);
    const { eventId, channelId, messageTs } = metadata;
    const values = view.state.values;

    // Extract board selection
    const boardId = values.board_block?.board_select?.selected_option?.value
      ?? process.env.MONDAY_BOARD_ID
      ?? "";

    // Extract summary & decisions
    const summary = values.summary_block?.summary_input?.value ?? "";
    const decisionsRaw = values.decisions_block?.decisions_input?.value ?? "";
    const decisions = decisionsRaw
      .split("\n")
      .map((d: string) => d.trim())
      .filter(Boolean);

    // Extract action items (skip empty slots)
    const actionItems: { title: string; description: string; assignee: string }[] = [];
    for (let i = 0; i < 5; i++) {
      const title = values[`action_title_${i}`]?.[`action_title_input_${i}`]?.value ?? "";
      const description = values[`action_desc_${i}`]?.[`action_desc_input_${i}`]?.value ?? "";
      const assignee = values[`action_assignee_${i}`]?.[`action_assignee_input_${i}`]?.value ?? "";
      if (title.trim()) {
        actionItems.push({ title: title.trim(), description: description.trim(), assignee: assignee.trim() });
      }
    }

    // Build prompt for the product-owner agent
    let prompt: string;
    if (actionItems.length > 0) {
      const taskLines = actionItems.map((item, i) => {
        let line = `${i + 1}. ${item.title}: ${item.description}`;
        if (item.assignee) line += ` (assign to: ${item.assignee})`;
        return line;
      });

      prompt =
        `Create the following tasks from meeting action items.\n` +
        (boardId ? `Use board_id=${boardId} for all task creation.\n\n` : "\n") +
        taskLines.join("\n");
    } else {
      const parts = [`Meeting summary: ${summary}`];
      if (decisions.length > 0) {
        parts.push(`Key decisions:\n${decisions.map((d: string) => `- ${d}`).join("\n")}`);
      }
      prompt =
        `The following meeting had no explicit action items, but the user wants to create tasks based on the context. ` +
        `Review the meeting notes and create appropriate follow-up tasks.\n` +
        (boardId ? `Use board_id=${boardId} for all task creation.\n\n` : "\n") +
        parts.join("\n\n");
    }

    const a2a = createA2AClient();
    const poUrl = AGENT_URLS["product-owner"];

    try {
      const response = await a2a.sendMessage(poUrl, prompt);

      const taskIds: string[] = [];
      if (response.result) {
        const resultText = extractTextFromTask(response.result);
        const idMatches = resultText.match(/\d{10,}/g);
        if (idMatches) taskIds.push(...idMatches);
      }

      meetingStore.markApproved(eventId, taskIds);

      if (channelId && messageTs) {
        const resultText = response.result
          ? extractTextFromTask(response.result)
          : "Tasks created.";

        await client.chat.update({
          channel: channelId,
          ts: messageTs,
          text: "Tasks created from meeting notes.",
          blocks: [
            {
              type: "section",
              text: {
                type: "mrkdwn",
                text: `:white_check_mark: *Tasks created!*\n${resultText}`,
              },
            },
            {
              type: "context",
              elements: [
                {
                  type: "mrkdwn",
                  text: `:robot_face: Approved by <@${(body as any).user?.id}>` +
                    (boardId ? ` | Board: \`${boardId}\`` : ""),
                },
              ],
            },
          ],
        });
      }
    } catch (err: any) {
      console.error("[actions] meeting_edit_submit error:", err);
      if (channelId && messageTs) {
        await client.chat.update({
          channel: channelId,
          ts: messageTs,
          text: `:x: Failed to create tasks: ${err.message ?? "Unknown error"}`,
          blocks: [],
        });
      }
    }
  });

  // -------------------------------------------------------------------------
  // meeting_dismiss — Dismiss meeting action items
  // -------------------------------------------------------------------------

  app.action("meeting_dismiss", async ({ ack, body, client }) => {
    await ack();

    const action = (body as any).actions?.[0];
    const eventId = action?.value;
    if (!eventId) return;

    meetingStore.markDismissed(eventId);

    const message = (body as any).message;
    const channel = (body as any).channel?.id;
    const messageTs = message?.ts;

    if (channel && messageTs) {
      // Replace buttons with dismissal notice
      const blocks = message?.blocks?.slice(0, -2) ?? [];
      blocks.push({
        type: "section",
        text: {
          type: "mrkdwn",
          text: `:no_entry_sign: *Dismissed* by <@${(body as any).user?.id}>`,
        },
      });

      await client.chat.update({
        channel,
        ts: messageTs,
        text: "Meeting notes dismissed.",
        blocks,
      });
    }
  });
}

// ---------------------------------------------------------------------------
// /create-task view submission handler
// ---------------------------------------------------------------------------

export function registerCreateTaskActions(app: App): void {
  app.view("create_task_submit", async ({ ack, view, body, client }) => {
    await ack();

    const metadata: CreateTaskModalMetadata = JSON.parse(view.private_metadata);
    const { channelId, userId } = metadata;
    const values = view.state.values;

    // Extract form values
    const taskName = values.task_name_block?.task_name_input?.value ?? "";
    const description = values.description_block?.description_input?.value ?? "";
    const boardId = values.board_block?.board_select?.selected_option?.value
      ?? process.env.MONDAY_BOARD_ID
      ?? "";
    const assignee = values.assignee_block?.assignee_input?.value ?? "";
    const status = values.status_block?.status_select?.selected_option?.value ?? "To Do";
    const priority = values.priority_block?.priority_select?.selected_option?.value ?? "Medium";

    if (!taskName.trim()) {
      // Shouldn't happen (required field), but guard anyway
      return;
    }

    // Build prompt for PO agent
    let prompt = `Create a task on Monday.com with the following details:\n`;
    prompt += `- Task name: ${taskName}\n`;
    if (description) prompt += `- Description: ${description}\n`;
    if (boardId) prompt += `- Board ID: ${boardId}\n`;
    if (assignee) prompt += `- Assign to: ${assignee}\n`;
    prompt += `- Status: ${status}\n`;
    prompt += `- Priority: ${priority}\n`;

    const a2a = createA2AClient();
    const poUrl = AGENT_URLS["product-owner"];

    try {
      const response = await a2a.sendMessage(poUrl, prompt);

      const resultText = response.result
        ? extractTextFromTask(response.result)
        : "Task created.";

      // Post confirmation in the channel
      await client.chat.postMessage({
        channel: channelId,
        text: `Task created from /create-task`,
        blocks: [
          {
            type: "section",
            text: {
              type: "mrkdwn",
              text: `:white_check_mark: *Task created:* ${taskName}\n${resultText}`,
            },
          },
          {
            type: "context",
            elements: [
              {
                type: "mrkdwn",
                text: `:robot_face: Created by <@${userId}>`
                  + (boardId ? ` | Board: \`${boardId}\`` : "")
                  + ` | Priority: ${priority} | Status: ${status}`,
              },
            ],
          },
        ],
      });
    } catch (err: any) {
      console.error("[actions] create_task_submit error:", err);
      try {
        await client.chat.postEphemeral({
          channel: channelId,
          user: userId,
          text: `:x: Failed to create task: ${err.message ?? "Unknown error"}`,
        });
      } catch (ephErr: any) {
        console.error("[actions] Failed to post ephemeral error:", ephErr.message);
      }
    }
  });
}
