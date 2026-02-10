import { describe, it, expect } from "vitest";
import {
  buildCreateTaskLoadingModal,
  buildCreateTaskModal,
} from "../src/ui/create-task-modal-blocks.js";
import type { ExtractedTask } from "../src/services/task-extractor-agent.js";
import type { MondayBoard, MondayUser } from "../src/services/monday-client.js";

const sampleTask: ExtractedTask = {
  taskName: "Fix login bug",
  description: "The SSO login fails on Chrome mobile",
  assignee: "Alice",
  priority: "High",
  status: "To Do",
};

const sampleBoards: MondayBoard[] = [
  { id: "100", name: "API Project" },
  { id: "200", name: "Frontend Redesign" },
  { id: "300", name: "DevOps" },
];

const sampleUsers: MondayUser[] = [
  { id: "1001", name: "Alice Johnson" },
  { id: "1002", name: "Bob Smith" },
  { id: "1003", name: "Charlie Brown" },
];

const sampleMetadata = {
  channelId: "C123",
  userId: "U456",
};

describe("buildCreateTaskLoadingModal", () => {
  it("returns a modal with no submit button", () => {
    const view = buildCreateTaskLoadingModal(sampleMetadata);

    expect(view.type).toBe("modal");
    expect(view.callback_id).toBe("create_task_submit");
    expect(view.title.text).toBe("Create Task");
    expect(view).not.toHaveProperty("submit");
    expect(view.close.text).toBe("Cancel");
  });

  it("shows loading text", () => {
    const view = buildCreateTaskLoadingModal(sampleMetadata);

    expect(view.blocks).toHaveLength(1);
    expect(view.blocks[0].text.text).toContain("hourglass");
    expect(view.blocks[0].text.text).toContain("extracting");
  });

  it("includes correct metadata", () => {
    const view = buildCreateTaskLoadingModal(sampleMetadata);

    const parsed = JSON.parse(view.private_metadata);
    expect(parsed.channelId).toBe("C123");
    expect(parsed.userId).toBe("U456");
  });
});

describe("buildCreateTaskModal", () => {
  it("returns a valid modal view structure", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    expect(view.type).toBe("modal");
    expect(view.callback_id).toBe("create_task_submit");
    expect(view.title.text).toBe("Create Task");
    expect(view.submit.text).toBe("Create Task");
    expect(view.close.text).toBe("Cancel");
  });

  it("pre-fills task name from extracted task", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    const nameBlock = view.blocks.find((b: any) => b.block_id === "task_name_block");
    expect(nameBlock).toBeDefined();
    expect(nameBlock.element.initial_value).toBe("Fix login bug");
  });

  it("pre-fills description from extracted task", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    const descBlock = view.blocks.find((b: any) => b.block_id === "description_block");
    expect(descBlock).toBeDefined();
    expect(descBlock.element.initial_value).toBe("The SSO login fails on Chrome mobile");
  });

  it("shows assignee as text input when no users provided", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    const assigneeBlock = view.blocks.find((b: any) => b.block_id === "assignee_block");
    expect(assigneeBlock).toBeDefined();
    expect(assigneeBlock.element.action_id).toBe("assignee_input");
    expect(assigneeBlock.element.initial_value).toBe("Alice");
  });

  it("shows assignee as dropdown when users provided", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata, sampleUsers);

    const assigneeBlock = view.blocks.find((b: any) => b.block_id === "assignee_block");
    expect(assigneeBlock).toBeDefined();
    expect(assigneeBlock.element.action_id).toBe("assignee_select");
    expect(assigneeBlock.element.options).toHaveLength(3);
    expect(assigneeBlock.element.options[0].text.text).toBe("Alice Johnson");
    expect(assigneeBlock.element.options[0].value).toBe("1001");
  });

  it("pre-selects assignee from LLM match", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata, sampleUsers);

    const assigneeBlock = view.blocks.find((b: any) => b.block_id === "assignee_block");
    expect(assigneeBlock.element.initial_option).toBeDefined();
    expect(assigneeBlock.element.initial_option.value).toBe("1001");
    expect(assigneeBlock.element.initial_option.text.text).toBe("Alice Johnson");
  });

  it("includes board dropdown with options", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    const boardBlock = view.blocks.find((b: any) => b.block_id === "board_block");
    expect(boardBlock).toBeDefined();
    expect(boardBlock.element.options).toHaveLength(3);
    expect(boardBlock.element.options[0].value).toBe("100");
    expect(boardBlock.element.options[0].text.text).toBe("API Project");
  });

  it("pre-selects status from extracted task", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    const statusBlock = view.blocks.find((b: any) => b.block_id === "status_block");
    expect(statusBlock).toBeDefined();
    expect(statusBlock.element.initial_option.value).toBe("To Do");
  });

  it("pre-selects priority from extracted task", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    const priorityBlock = view.blocks.find((b: any) => b.block_id === "priority_block");
    expect(priorityBlock).toBeDefined();
    expect(priorityBlock.element.initial_option.value).toBe("High");
  });

  it("includes metadata in private_metadata", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);

    const parsed = JSON.parse(view.private_metadata);
    expect(parsed.channelId).toBe("C123");
    expect(parsed.userId).toBe("U456");
  });

  it("stays under 50 blocks", () => {
    const view = buildCreateTaskModal(sampleTask, sampleBoards, sampleMetadata);
    expect(view.blocks.length).toBeLessThanOrEqual(50);
  });

  it("handles empty boards (no board block)", () => {
    const view = buildCreateTaskModal(sampleTask, [], sampleMetadata);

    const boardBlock = view.blocks.find((b: any) => b.block_id === "board_block");
    expect(boardBlock).toBeUndefined();
  });

  it("handles empty extracted task (shows empty defaults)", () => {
    const emptyTask: ExtractedTask = {
      taskName: "",
      description: "",
      assignee: "",
      priority: "Medium",
      status: "To Do",
    };

    const view = buildCreateTaskModal(emptyTask, sampleBoards, sampleMetadata);

    const nameBlock = view.blocks.find((b: any) => b.block_id === "task_name_block");
    expect(nameBlock.element.initial_value).toBe("");

    const descBlock = view.blocks.find((b: any) => b.block_id === "description_block");
    expect(descBlock.element.initial_value).toBe("");

    const assigneeBlock = view.blocks.find((b: any) => b.block_id === "assignee_block");
    // No users provided → text input with empty value
    expect(assigneeBlock.element.action_id).toBe("assignee_input");
    expect(assigneeBlock.element.initial_value).toBe("");

    const priorityBlock = view.blocks.find((b: any) => b.block_id === "priority_block");
    expect(priorityBlock.element.initial_option.value).toBe("Medium");

    const statusBlock = view.blocks.find((b: any) => b.block_id === "status_block");
    expect(statusBlock.element.initial_option.value).toBe("To Do");
  });
});
