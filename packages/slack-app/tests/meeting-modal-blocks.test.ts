import { describe, it, expect } from "vitest";
import { buildMeetingEditModal } from "../src/ui/meeting-modal-blocks.js";
import type { MeetingAnalysis } from "../src/services/meeting-notes-agent.js";
import type { MondayBoard } from "../src/services/monday-client.js";

const sampleAnalysis: MeetingAnalysis = {
  summary: "Team discussed API migration plan.",
  actionItems: [
    { title: "Write migration script", description: "Script to migrate v1 to v2", assignee: "Alice" },
    { title: "Update docs", description: "Update API documentation for v2" },
  ],
  decisions: ["Use GraphQL for v2", "Deprecate REST endpoints"],
};

const sampleBoards: MondayBoard[] = [
  { id: "100", name: "API Project" },
  { id: "200", name: "Frontend Redesign" },
  { id: "300", name: "DevOps" },
];

const sampleMetadata = {
  eventId: "evt-123",
  channelId: "C456",
  messageTs: "1234567890.123456",
};

describe("buildMeetingEditModal", () => {
  it("returns a valid modal view structure", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);

    expect(view.type).toBe("modal");
    expect(view.callback_id).toBe("meeting_edit_submit");
    expect(view.title.text).toBe("Edit Meeting Tasks");
    expect(view.submit.text).toBe("Create Tasks");
    expect(view.close.text).toBe("Cancel");
  });

  it("includes private_metadata with event context", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);

    const parsed = JSON.parse(view.private_metadata);
    expect(parsed.eventId).toBe("evt-123");
    expect(parsed.channelId).toBe("C456");
    expect(parsed.messageTs).toBe("1234567890.123456");
  });

  it("pre-selects the suggested board", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);

    const boardBlock = view.blocks.find((b: any) => b.block_id === "board_block");
    expect(boardBlock).toBeDefined();
    expect(boardBlock.element.initial_option.value).toBe("100");
    expect(boardBlock.element.initial_option.text.text).toBe("API Project");
  });

  it("pre-fills summary from analysis", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);

    const summaryBlock = view.blocks.find((b: any) => b.block_id === "summary_block");
    expect(summaryBlock).toBeDefined();
    expect(summaryBlock.element.initial_value).toBe("Team discussed API migration plan.");
  });

  it("pre-fills decisions as newline-separated text", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);

    const decisionsBlock = view.blocks.find((b: any) => b.block_id === "decisions_block");
    expect(decisionsBlock).toBeDefined();
    expect(decisionsBlock.element.initial_value).toBe("Use GraphQL for v2\nDeprecate REST endpoints");
  });

  it("renders 5 action item slots", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);

    const titleBlocks = view.blocks.filter((b: any) =>
      b.block_id?.startsWith("action_title_"),
    );
    expect(titleBlocks).toHaveLength(5);
  });

  it("pre-fills existing action items in slots", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);

    const title0 = view.blocks.find((b: any) => b.block_id === "action_title_0");
    expect(title0.element.initial_value).toBe("Write migration script");

    const desc0 = view.blocks.find((b: any) => b.block_id === "action_desc_0");
    expect(desc0.element.initial_value).toBe("Script to migrate v1 to v2");

    const assignee0 = view.blocks.find((b: any) => b.block_id === "action_assignee_0");
    expect(assignee0.element.initial_value).toBe("Alice");

    // Second slot
    const title1 = view.blocks.find((b: any) => b.block_id === "action_title_1");
    expect(title1.element.initial_value).toBe("Update docs");

    // Third slot should be empty
    const title2 = view.blocks.find((b: any) => b.block_id === "action_title_2");
    expect(title2.element.initial_value).toBe("");
  });

  it("stays under 50 blocks", () => {
    const view = buildMeetingEditModal(sampleAnalysis, sampleBoards, "100", sampleMetadata);
    expect(view.blocks.length).toBeLessThanOrEqual(50);
  });

  it("handles empty boards list (no board selector)", () => {
    const view = buildMeetingEditModal(sampleAnalysis, [], undefined, sampleMetadata);

    const boardBlock = view.blocks.find((b: any) => b.block_id === "board_block");
    expect(boardBlock).toBeUndefined();
  });

  it("handles no action items in analysis", () => {
    const emptyAnalysis: MeetingAnalysis = {
      summary: "Quick sync.",
      actionItems: [],
      decisions: [],
    };

    const view = buildMeetingEditModal(emptyAnalysis, sampleBoards, undefined, sampleMetadata);

    // Should still render 5 empty slots
    const titleBlocks = view.blocks.filter((b: any) =>
      b.block_id?.startsWith("action_title_"),
    );
    expect(titleBlocks).toHaveLength(5);
    expect(titleBlocks[0].element.initial_value).toBe("");
  });
});
