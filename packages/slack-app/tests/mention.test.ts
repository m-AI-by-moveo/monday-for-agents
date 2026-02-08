import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// Mock the a2a-client module BEFORE importing the handler
// ---------------------------------------------------------------------------

const mockSendMessage = vi.fn();
const mockGetTask = vi.fn();

vi.mock("../src/services/a2a-client.js", () => ({
  createA2AClient: () => ({
    sendMessage: mockSendMessage,
    getTask: mockGetTask,
  }),
  extractTextFromTask: vi.fn((task: { status: { state: string; message?: { parts: { type: string; text: string }[] } }; id: string }) => {
    const msg = task.status?.message;
    if (msg) {
      const textPart = msg.parts.find((p: { type: string }) => p.type === "text");
      if (textPart) return textPart.text;
    }
    return `[Agent task ${task.id} is ${task.status.state}]`;
  }),
  AGENT_URLS: {
    "product-owner": "http://localhost:10001",
    "developer": "http://localhost:10002",
    "reviewer": "http://localhost:10003",
    "scrum-master": "http://localhost:10004",
  },
}));

// Mock uuid so we get predictable context IDs
vi.mock("uuid", () => ({
  v4: vi.fn(() => "mock-uuid-1234"),
}));

import { registerMentionHandler, threadMap } from "../src/handlers/mention.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Creates a mock Slack Bolt App that captures the callback registered
 * via `app.event("app_mention", callback)`.
 */
function createMockApp() {
  let mentionCallback: (args: Record<string, unknown>) => Promise<void>;

  const app = {
    event: vi.fn((eventName: string, cb: (args: Record<string, unknown>) => Promise<void>) => {
      if (eventName === "app_mention") {
        mentionCallback = cb;
      }
    }),
  };

  // Register the handler which captures the callback
  registerMentionHandler(app as any);

  return {
    app,
    /** Invoke the captured app_mention callback */
    fireMention: (args: Record<string, unknown>) => mentionCallback(args),
  };
}

function makeSay() {
  return vi.fn().mockResolvedValue(undefined);
}

function makeEvent(overrides: Record<string, unknown> = {}) {
  return {
    text: "<@U12345> hello world",
    ts: "1700000000.000001",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("mention handler", () => {
  let mock: ReturnType<typeof createMockApp>;

  beforeEach(() => {
    mockSendMessage.mockReset();
    mockGetTask.mockReset();
    threadMap.clear();
    mock = createMockApp();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // Routing
  // -------------------------------------------------------------------------

  describe("routing", () => {
    it("routes 'status' keyword to scrum-master", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "ok" }] } },
        },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> what is the status?" }),
        say,
      });

      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10004",
        "what is the status?",
        "mock-uuid-1234",
      );
    });

    it("routes 'standup' keyword to scrum-master", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "ok" }] } },
        },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> run standup" }),
        say,
      });

      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10004",
        expect.stringContaining("standup"),
        expect.any(String),
      );
    });

    it("routes 'blocked' keyword to scrum-master", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "ok" }] } },
        },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> what is blocked?" }),
        say,
      });

      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10004",
        "what is blocked?",
        "mock-uuid-1234",
      );
    });

    it("routes 'summary' keyword to scrum-master", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "ok" }] } },
        },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> give me a summary" }),
        say,
      });

      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10004",
        "give me a summary",
        "mock-uuid-1234",
      );
    });

    it("routes general messages to product-owner", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "ok" }] } },
        },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> create a new feature" }),
        say,
      });

      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10001",
        "create a new feature",
        "mock-uuid-1234",
      );
    });
  });

  // -------------------------------------------------------------------------
  // stripMention
  // -------------------------------------------------------------------------

  describe("stripMention", () => {
    it("removes <@U12345> patterns from message text", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "done" }] } },
        },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@UABC123> please help me" }),
        say,
      });

      // The message sent to the agent should not contain the mention
      expect(mockSendMessage).toHaveBeenCalledWith(
        expect.any(String),
        "please help me",
        expect.any(String),
      );
    });

    it("returns help response when message is empty after stripping mention", async () => {
      const say = makeSay();

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345>" }),
        say,
      });

      expect(say).toHaveBeenCalledWith({
        text: "Hey! How can I help?",
        thread_ts: expect.any(String),
      });
      expect(mockSendMessage).not.toHaveBeenCalled();
    });
  });

  // -------------------------------------------------------------------------
  // Thread mapping / context ID management
  // -------------------------------------------------------------------------

  describe("context management", () => {
    it("creates a new context ID and stores thread mapping for new mentions", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "ok" }] } },
        },
      });

      const ts = "1700000001.000001";
      await mock.fireMention({
        event: makeEvent({ ts, text: "<@U12345> hello" }),
        say,
      });

      // threadMap should now have an entry keyed by the event ts
      expect(threadMap.has(ts)).toBe(true);
      const mapping = threadMap.get(ts);
      expect(mapping?.contextId).toBe("mock-uuid-1234");
      expect(mapping?.agentKey).toBe("product-owner");
    });

    it("reuses existing thread mapping for follow-up mentions in same thread", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "ok" }] } },
        },
      });

      const threadTs = "1700000002.000001";

      // Pre-populate a mapping
      threadMap.set(threadTs, { contextId: "existing-ctx", agentKey: "product-owner" });

      await mock.fireMention({
        event: makeEvent({
          text: "<@U12345> follow up question",
          thread_ts: threadTs,
          ts: "1700000002.000099",
        }),
        say,
      });

      // Should reuse existing context
      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10001",
        "follow up question",
        "existing-ctx",
      );
      // mapping should remain unchanged
      expect(threadMap.get(threadTs)?.contextId).toBe("existing-ctx");
    });
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  describe("error handling", () => {
    it("posts agent error response to thread when response.error is set", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        error: { code: -32000, message: "Something went wrong" },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> do something" }),
        say,
      });

      expect(say).toHaveBeenCalledWith({
        text: ":x: Agent error: Something went wrong",
        thread_ts: expect.any(String),
      });
    });

    it("posts warning message when HTTP error occurs contacting agent", async () => {
      const say = makeSay();
      mockSendMessage.mockRejectedValue(new Error("ECONNREFUSED"));

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> do something" }),
        say,
      });

      expect(say).toHaveBeenCalledWith({
        text: expect.stringContaining(":warning:"),
        thread_ts: expect.any(String),
      });
      expect(say).toHaveBeenCalledWith({
        text: expect.stringContaining("product-owner"),
        thread_ts: expect.any(String),
      });
    });
  });

  // -------------------------------------------------------------------------
  // Successful response
  // -------------------------------------------------------------------------

  describe("successful response", () => {
    it("posts extracted text from agent task result", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "task-abc",
          contextId: "ctx-abc",
          status: {
            state: "completed",
            message: {
              role: "agent",
              parts: [{ type: "text", text: "Here is the board summary." }],
            },
          },
        },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> give me info" }),
        say,
      });

      expect(say).toHaveBeenCalledWith({
        text: "Here is the board summary.",
        thread_ts: expect.any(String),
      });
    });

    it("posts fallback text when result has no content", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: undefined,
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> do something" }),
        say,
      });

      expect(say).toHaveBeenCalledWith({
        text: "_No response from agent._",
        thread_ts: expect.any(String),
      });
    });
  });
});
