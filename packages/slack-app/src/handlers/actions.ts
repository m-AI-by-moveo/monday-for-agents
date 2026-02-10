import type { App } from "@slack/bolt";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
} from "../services/a2a-client.js";
import type { MeetingStore } from "../services/meeting-store.js";
import type { MeetingAnalysis } from "../services/meeting-notes-agent.js";

export function registerActions(
  app: App,
  meetingStore: MeetingStore,
): void {
  // -------------------------------------------------------------------------
  // meeting_approve — Create tasks from meeting action items
  // -------------------------------------------------------------------------

  app.action("meeting_approve", async ({ ack, body, client }) => {
    await ack();

    const action = (body as any).actions?.[0];
    const eventId = action?.value;
    if (!eventId) return;

    const message = (body as any).message;
    const channel = (body as any).channel?.id;
    const messageTs = message?.ts;

    // Retrieve stored analysis from message metadata
    let analysis: MeetingAnalysis | null = null;
    try {
      const metadata = message?.metadata;
      if (metadata?.event_payload?.analysis) {
        analysis = JSON.parse(metadata.event_payload.analysis as string);
      }
    } catch {
      // Fall through — will report error
    }

    if (!analysis || analysis.actionItems.length === 0) {
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

    // Build a task creation prompt for the product-owner agent
    const taskLines = analysis.actionItems.map((item, i) => {
      let line = `${i + 1}. ${item.title}: ${item.description}`;
      if (item.assignee) line += ` (assign to: ${item.assignee})`;
      if (item.priority) line += ` [priority: ${item.priority}]`;
      if (item.deadline) line += ` [deadline: ${item.deadline}]`;
      return line;
    });

    const prompt =
      `Create the following tasks on the board from meeting action items:\n\n` +
      taskLines.join("\n");

    const a2a = createA2AClient();
    const poUrl = AGENT_URLS["product-owner"];

    try {
      const response = await a2a.sendMessage(poUrl, prompt);

      const taskIds: string[] = [];
      if (response.result) {
        const resultText = extractTextFromTask(response.result);
        // Extract any item IDs mentioned in the response
        const idMatches = resultText.match(/\d{10,}/g);
        if (idMatches) taskIds.push(...idMatches);
      }

      meetingStore.markApproved(eventId, taskIds);

      if (channel && messageTs) {
        const resultText = response.result
          ? extractTextFromTask(response.result)
          : "Tasks created.";

        // Replace buttons with confirmation
        const blocks = message?.blocks?.slice(0, -2) ?? [];
        blocks.push({
          type: "section",
          text: {
            type: "mrkdwn",
            text: `:white_check_mark: *Tasks created!*\n${resultText}`,
          },
        });
        blocks.push({
          type: "context",
          elements: [
            {
              type: "mrkdwn",
              text: `:robot_face: Approved by <@${(body as any).user?.id}>`,
            },
          ],
        });

        await client.chat.update({
          channel,
          ts: messageTs,
          text: "Tasks created from meeting notes.",
          blocks,
        });
      }
    } catch (err: any) {
      console.error("[actions] meeting_approve error:", err);
      if (channel && messageTs) {
        await client.chat.update({
          channel,
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
