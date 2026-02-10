import { describe, it, expect, beforeEach, afterEach } from "vitest";
import nock from "nock";
import { TaskExtractorAgent } from "../src/services/task-extractor-agent.js";

// Anthropic SDK validates API key before making HTTP requests
process.env.ANTHROPIC_API_KEY = "sk-ant-test-key-for-unit-tests";

describe("TaskExtractorAgent", () => {
  let agent: TaskExtractorAgent;

  beforeEach(() => {
    agent = new TaskExtractorAgent();
    nock.disableNetConnect();
  });

  afterEach(() => {
    nock.cleanAll();
    nock.enableNetConnect();
  });

  it("extracts all fields from a clear conversation", async () => {
    const mockTask = {
      taskName: "Fix login page CSS",
      description: "The login button is misaligned on mobile devices. Need to fix the CSS grid layout.",
      assignee: "Alice",
      priority: "High",
      status: "To Do",
    };

    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_123",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: JSON.stringify(mockTask) },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 100, output_tokens: 200 },
      });

    const result = await agent.extractTaskFromMessages([
      { user: "Alice", text: "The login page is broken on mobile" },
      { user: "Bob", text: "Yeah, the CSS grid is off. Alice, can you fix it?" },
      { user: "Alice", text: "Sure, I'll take care of it today. It's high priority." },
    ]);

    expect(result.taskName).toBe("Fix login page CSS");
    expect(result.description).toContain("login button");
    expect(result.assignee).toBe("Alice");
    expect(result.priority).toBe("High");
    expect(result.status).toBe("To Do");
  });

  it("defaults priority and status when not evident", async () => {
    const mockTask = {
      taskName: "Update README",
      description: "Add setup instructions to the README file",
      assignee: "",
      priority: "Medium",
      status: "To Do",
    };

    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_456",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: JSON.stringify(mockTask) },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 50, output_tokens: 100 },
      });

    const result = await agent.extractTaskFromMessages([
      { user: "Charlie", text: "We should probably update the README at some point" },
    ]);

    expect(result.taskName).toBe("Update README");
    expect(result.priority).toBe("Medium");
    expect(result.status).toBe("To Do");
    expect(result.assignee).toBe("");
  });

  it("handles empty messages (returns defaults)", async () => {
    const result = await agent.extractTaskFromMessages([]);

    expect(result.taskName).toBe("");
    expect(result.description).toBe("");
    expect(result.assignee).toBe("");
    expect(result.priority).toBe("Medium");
    expect(result.status).toBe("To Do");
  });

  it("handles malformed LLM response (falls back gracefully)", async () => {
    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_789",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: "I cannot extract a task from this conversation." },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 50, output_tokens: 20 },
      });

    const result = await agent.extractTaskFromMessages([
      { user: "Dave", text: "Hey, how's it going?" },
    ]);

    expect(result.taskName).toBe("");
    expect(result.priority).toBe("Medium");
    expect(result.status).toBe("To Do");
  });

  it("strips markdown code fences from LLM response", async () => {
    const mockTask = {
      taskName: "Deploy hotfix",
      description: "Deploy the auth hotfix to production",
      assignee: "Bob",
      priority: "Critical",
      status: "In Progress",
    };

    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_abc",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: "```json\n" + JSON.stringify(mockTask) + "\n```" },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 80, output_tokens: 120 },
      });

    const result = await agent.extractTaskFromMessages([
      { user: "Bob", text: "I'm deploying the auth hotfix now, it's critical" },
    ]);

    expect(result.taskName).toBe("Deploy hotfix");
    expect(result.assignee).toBe("Bob");
    expect(result.priority).toBe("Critical");
    expect(result.status).toBe("In Progress");
  });

  it("validates priority enum values", async () => {
    const mockTask = {
      taskName: "Some task",
      description: "desc",
      assignee: "",
      priority: "URGENT",
      status: "Doing",
    };

    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_enum",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: JSON.stringify(mockTask) },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 50, output_tokens: 50 },
      });

    const result = await agent.extractTaskFromMessages([
      { user: "Eve", text: "This is urgent!" },
    ]);

    // Invalid enum values should fall back to defaults
    expect(result.priority).toBe("Medium");
    expect(result.status).toBe("To Do");
  });
});
