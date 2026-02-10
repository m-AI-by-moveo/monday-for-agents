import { describe, it, expect } from "vitest";
import { taskPreviewBlocks } from "../src/ui/task-preview-blocks.js";
import type { ExtractedTask } from "../src/services/task-extractor-agent.js";

describe("taskPreviewBlocks", () => {
  const mockTask: ExtractedTask = {
    taskName: "Fix login page CSS",
    description: "The login button is misaligned on mobile devices",
    assignee: "Alice",
    priority: "High",
    status: "To Do",
  };

  const metadata = {
    extractedTask: mockTask,
    channelId: "C123",
    threadTs: "1234.5678",
    userId: "U123",
    boardsJson: JSON.stringify([{ id: "1", name: "Sprint Board" }]),
    usersJson: JSON.stringify([{ id: "u1", name: "Alice" }]),
  };

  it("returns correct block structure", () => {
    const result = taskPreviewBlocks(mockTask, metadata);

    expect(result.blocks).toHaveLength(3);
    expect(result.blocks[0]).toMatchObject({
      type: "header",
      text: { type: "plain_text", text: "Task Preview" },
    });
    expect(result.blocks[1]).toMatchObject({ type: "section" });
    expect(result.blocks[2]).toMatchObject({ type: "actions" });
  });

  it("includes all task fields in section text", () => {
    const result = taskPreviewBlocks(mockTask, metadata);
    const section = result.blocks[1] as any;
    const text = section.text.text;

    expect(text).toContain("*Task:* Fix login page CSS");
    expect(text).toContain("*Description:* The login button is misaligned");
    expect(text).toContain("*Assignee:* Alice");
    expect(text).toContain("*Priority:* High");
    expect(text).toContain("*Status:* To Do");
  });

  it("includes three action buttons", () => {
    const result = taskPreviewBlocks(mockTask, metadata);
    const actions = result.blocks[2] as any;

    expect(actions.elements).toHaveLength(3);
    expect(actions.elements[0]).toMatchObject({
      type: "button",
      action_id: "mention_create_task",
      style: "primary",
    });
    expect(actions.elements[1]).toMatchObject({
      type: "button",
      action_id: "mention_edit_task",
    });
    expect(actions.elements[2]).toMatchObject({
      type: "button",
      action_id: "mention_cancel_task",
      style: "danger",
    });
  });

  it("includes metadata with serialized task data", () => {
    const result = taskPreviewBlocks(mockTask, metadata);

    expect(result.metadata.event_type).toBe("mention_task_preview");
    expect(result.metadata.event_payload.channel_id).toBe("C123");
    expect(result.metadata.event_payload.thread_ts).toBe("1234.5678");
    expect(result.metadata.event_payload.user_id).toBe("U123");

    const parsedTask = JSON.parse(result.metadata.event_payload.extracted_task);
    expect(parsedTask.taskName).toBe("Fix login page CSS");
  });

  it("returns fallback text with task name", () => {
    const result = taskPreviewBlocks(mockTask, metadata);
    expect(result.text).toContain("Fix login page CSS");
  });

  it("handles empty task fields gracefully", () => {
    const emptyTask: ExtractedTask = {
      taskName: "",
      description: "",
      assignee: "",
      priority: "Medium",
      status: "To Do",
    };
    const result = taskPreviewBlocks(emptyTask, {
      ...metadata,
      extractedTask: emptyTask,
    });

    expect(result.blocks).toHaveLength(3);
    const section = result.blocks[1] as any;
    expect(section.text.text).toContain("*Priority:* Medium");
    expect(section.text.text).toContain("*Status:* To Do");
  });
});
