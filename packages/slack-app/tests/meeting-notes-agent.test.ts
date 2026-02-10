import { describe, it, expect, beforeEach, afterEach } from "vitest";
import nock from "nock";
import { MeetingNotesAgent } from "../src/services/meeting-notes-agent.js";

// Anthropic SDK validates API key before making HTTP requests
process.env.ANTHROPIC_API_KEY = "sk-ant-test-key-for-unit-tests";

describe("MeetingNotesAgent", () => {
  let agent: MeetingNotesAgent;

  beforeEach(() => {
    agent = new MeetingNotesAgent();
    nock.disableNetConnect();
  });

  afterEach(() => {
    nock.cleanAll();
    nock.enableNetConnect();
  });

  it("extracts action items from transcript", async () => {
    const mockAnalysis = {
      summary: "Team discussed sprint priorities and upcoming deadlines.",
      actionItems: [
        {
          title: "Update API docs",
          description: "Add new endpoints to the API documentation",
          assignee: "Alice",
          priority: "high",
        },
        {
          title: "Fix login bug",
          description: "Investigate and fix the SSO login issue",
          assignee: "Bob",
          priority: "medium",
        },
      ],
      decisions: ["Use React for the new frontend"],
    };

    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_123",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: JSON.stringify(mockAnalysis) },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 100, output_tokens: 200 },
      });

    const result = await agent.analyzeMeetingTranscript(
      "Alice: We need to update the API docs. Bob: I'll fix the login bug. Everyone agreed to use React.",
      "Sprint Planning",
    );

    expect(result.summary).toContain("sprint priorities");
    expect(result.actionItems).toHaveLength(2);
    expect(result.actionItems[0].title).toBe("Update API docs");
    expect(result.actionItems[0].assignee).toBe("Alice");
    expect(result.actionItems[1].title).toBe("Fix login bug");
    expect(result.decisions).toHaveLength(1);
  });

  it("handles empty transcript", async () => {
    const result = await agent.analyzeMeetingTranscript("", "Empty Meeting");

    expect(result.summary).toContain("Empty");
    expect(result.actionItems).toHaveLength(0);
    expect(result.decisions).toHaveLength(0);
  });

  it("handles too-short transcript", async () => {
    const result = await agent.analyzeMeetingTranscript("Hi", "Quick Call");

    expect(result.actionItems).toHaveLength(0);
  });

  it("handles transcript with no action items", async () => {
    const mockAnalysis = {
      summary: "Casual team check-in with no specific action items.",
      actionItems: [],
      decisions: [],
    };

    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_456",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: JSON.stringify(mockAnalysis) },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 50, output_tokens: 50 },
      });

    const result = await agent.analyzeMeetingTranscript(
      "Hey everyone, just wanted to say hi and see how things are going. All good? Great, see you next week.",
      "Casual Check-in",
    );

    expect(result.actionItems).toHaveLength(0);
    expect(result.decisions).toHaveLength(0);
  });

  it("handles malformed LLM response", async () => {
    nock("https://api.anthropic.com")
      .post("/v1/messages")
      .reply(200, {
        id: "msg_789",
        type: "message",
        role: "assistant",
        content: [
          { type: "text", text: "This is not valid JSON at all" },
        ],
        model: "claude-sonnet-4-5-20250929",
        stop_reason: "end_turn",
        usage: { input_tokens: 50, output_tokens: 20 },
      });

    const result = await agent.analyzeMeetingTranscript(
      "Some meeting transcript that produces bad output from the LLM",
      "Bad Output Meeting",
    );

    expect(result.actionItems).toHaveLength(0);
    // Falls back to raw text as summary when JSON parsing fails
    expect(result.summary).toContain("not valid JSON");
  });
});
