import { describe, it, expect, beforeEach, afterEach } from "vitest";
import nock from "nock";
import { IntentRouter, classifyFallback } from "../src/services/intent-router.js";

// Anthropic SDK validates API key before making HTTP requests
process.env.ANTHROPIC_API_KEY = "sk-ant-test-key-for-unit-tests";

function mockClassification(intent: string, agentKey: string) {
  return nock("https://api.anthropic.com")
    .post("/v1/messages")
    .reply(200, {
      id: "msg_intent",
      type: "message",
      role: "assistant",
      content: [
        { type: "text", text: JSON.stringify({ intent, agentKey }) },
      ],
      model: "claude-haiku-4-5-20251001",
      stop_reason: "end_turn",
      usage: { input_tokens: 50, output_tokens: 20 },
    });
}

describe("IntentRouter", () => {
  let router: IntentRouter;

  beforeEach(() => {
    router = new IntentRouter();
    nock.disableNetConnect();
  });

  afterEach(() => {
    nock.cleanAll();
    nock.enableNetConnect();
  });

  // -------------------------------------------------------------------------
  // Keyword pre-filter (LLM not called)
  // -------------------------------------------------------------------------

  describe("keyword pre-filter", () => {
    it("routes 'create a task from this conversation' to create-task without LLM", async () => {
      // No nock — if LLM were called it would fail due to disableNetConnect
      const result = await router.classify("create a task from this conversation");
      expect(result.intent).toBe("create-task");
      expect(result.agentKey).toBe("product-owner");
    });

    it("routes 'board status' to board-status without LLM", async () => {
      const result = await router.classify("what's the board status?");
      expect(result.intent).toBe("board-status");
      expect(result.agentKey).toBe("scrum-master");
    });

    it("routes 'sync meetings' to meeting-sync without LLM", async () => {
      const result = await router.classify("sync meetings from today");
      expect(result.intent).toBe("meeting-sync");
      expect(result.agentKey).toBe("product-owner");
    });

    it("routes 'calendar' to calendar without LLM", async () => {
      const result = await router.classify("check my calendar for tomorrow");
      expect(result.intent).toBe("calendar");
      expect(result.agentKey).toBe("product-owner");
    });

    it("routes 'google drive' to drive without LLM", async () => {
      const result = await router.classify("search google drive for the report");
      expect(result.intent).toBe("drive");
      expect(result.agentKey).toBe("product-owner");
    });

    it("routes 'standup' to board-status without LLM", async () => {
      const result = await router.classify("give me the standup summary");
      expect(result.intent).toBe("board-status");
      expect(result.agentKey).toBe("scrum-master");
    });
  });

  // -------------------------------------------------------------------------
  // LLM classification
  // -------------------------------------------------------------------------

  describe("LLM classification", () => {
    it("routes general chat to agent-chat via LLM", async () => {
      mockClassification("agent-chat", "product-owner");
      const result = await router.classify("plan a feature for user onboarding");
      expect(result.intent).toBe("agent-chat");
      expect(result.agentKey).toBe("product-owner");
    });

    it("routes scrum-master chat via LLM", async () => {
      mockClassification("agent-chat", "scrum-master");
      const result = await router.classify("help me optimize our sprint process");
      expect(result.intent).toBe("agent-chat");
      expect(result.agentKey).toBe("scrum-master");
    });

    it("routes create-task via LLM when keywords don't match", async () => {
      mockClassification("create-task", "product-owner");
      const result = await router.classify("could you track this as a work item?");
      expect(result.intent).toBe("create-task");
    });

    it("routes calendar via LLM", async () => {
      mockClassification("calendar", "product-owner");
      const result = await router.classify("what's on my schedule for next Tuesday?");
      // "schedule" triggers keyword pre-filter first
      expect(result.intent).toBe("calendar");
    });

    it("routes drive via LLM", async () => {
      mockClassification("drive", "product-owner");
      const result = await router.classify("find the Q4 report in my files");
      // "find the" doesn't match keyword rules, so LLM handles it
      expect(result.intent).toBe("drive");
    });
  });

  // -------------------------------------------------------------------------
  // Fallback on LLM failure
  // -------------------------------------------------------------------------

  describe("fallback on LLM failure", () => {
    it("falls back to keyword matching when LLM returns error", async () => {
      nock("https://api.anthropic.com")
        .post("/v1/messages")
        .reply(500, { error: "Internal server error" });

      const result = await router.classify("what is the status of our sprint");
      expect(result.intent).toBe("board-status");
      expect(result.agentKey).toBe("scrum-master");
    });

    it("falls back to agent-chat when LLM fails and no keywords match", async () => {
      nock("https://api.anthropic.com")
        .post("/v1/messages")
        .reply(500, { error: "Internal server error" });

      const result = await router.classify("hey, help me think through this problem");
      expect(result.intent).toBe("agent-chat");
      expect(result.agentKey).toBe("product-owner");
    });

    it("falls back when LLM returns invalid JSON", async () => {
      nock("https://api.anthropic.com")
        .post("/v1/messages")
        .reply(200, {
          id: "msg_bad",
          type: "message",
          role: "assistant",
          content: [
            { type: "text", text: "I'm not sure what you want" },
          ],
          model: "claude-haiku-4-5-20251001",
          stop_reason: "end_turn",
          usage: { input_tokens: 50, output_tokens: 20 },
        });

      const result = await router.classify("what are the blocked items");
      expect(result.intent).toBe("board-status"); // "blocked" matches fallback keyword
    });
  });

  // -------------------------------------------------------------------------
  // classifyFallback (standalone)
  // -------------------------------------------------------------------------

  describe("classifyFallback", () => {
    it("routes task-related messages to create-task", () => {
      const result = classifyFallback("create a new task for the login bug");
      expect(result.intent).toBe("create-task");
    });

    it("routes status/board messages to board-status", () => {
      const result = classifyFallback("show me the sprint status");
      expect(result.intent).toBe("board-status");
    });

    it("routes calendar messages to calendar", () => {
      const result = classifyFallback("when is my next meeting");
      expect(result.intent).toBe("calendar");
    });

    it("routes drive messages to drive", () => {
      const result = classifyFallback("find the design document");
      expect(result.intent).toBe("drive");
    });

    it("routes sync messages to meeting-sync", () => {
      const result = classifyFallback("sync the meeting notes");
      expect(result.intent).toBe("meeting-sync");
    });

    it("defaults to agent-chat for unrecognized messages", () => {
      const result = classifyFallback("help me brainstorm a new feature");
      expect(result.intent).toBe("agent-chat");
      expect(result.agentKey).toBe("product-owner");
    });
  });
});
