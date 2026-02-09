import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// Mock the a2a-client module BEFORE importing the handler
// ---------------------------------------------------------------------------

const { mockSendMessage, mockGetTask } = vi.hoisted(() => ({
  mockSendMessage: vi.fn(),
  mockGetTask: vi.fn(),
}));

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

// Mock block-builder — passthrough that wraps text in a blocks array
vi.mock("../src/ui/block-builder.js", () => ({
  agentResponseBlocks: (agent: string, text: string) => ({
    blocks: [{ type: "section", text: { type: "mrkdwn", text } }],
    text,
  }),
  errorBlocks: (msg: string) => ({
    blocks: [{ type: "section", text: { type: "mrkdwn", text: `:x: ${msg}` } }],
    text: `:x: ${msg}`,
  }),
  warningBlocks: (msg: string) => ({
    blocks: [{ type: "section", text: { type: "mrkdwn", text: `:warning: ${msg}` } }],
    text: `:warning: ${msg}`,
  }),
  loadingBlocks: (msg = "Processing your request...") => ({
    blocks: [{ type: "section", text: { type: "mrkdwn", text: msg } }],
    text: msg,
  }),
  noResponseBlocks: () => ({
    blocks: [{ type: "section", text: { type: "mrkdwn", text: "_No response from agent._" } }],
    text: "_No response from agent._",
  }),
}));

import { registerMentionHandler, threadMap } from "../src/handlers/mention.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockApp() {
  let mentionCallback: (args: Record<string, unknown>) => Promise<void>;

  const app = {
    event: vi.fn((eventName: string, cb: (args: Record<string, unknown>) => Promise<void>) => {
      if (eventName === "app_mention") {
        mentionCallback = cb;
      }
    }),
  };

  registerMentionHandler(app as any);

  return {
    app,
    fireMention: (args: Record<string, unknown>) => mentionCallback(args),
  };
}

function makeSay() {
  return vi.fn().mockResolvedValue(undefined);
}

/** Mock Slack WebClient that satisfies resolveMentions() */
function makeClient() {
  return {
    auth: {
      test: vi.fn().mockResolvedValue({ user_id: "U12345" }),
    },
    users: {
      list: vi.fn().mockResolvedValue({ members: [], response_metadata: {} }),
    },
  };
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
        client: makeClient(),
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
        client: makeClient(),
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
        client: makeClient(),
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
        client: makeClient(),
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
        client: makeClient(),
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

  describe("resolveMentions", () => {
    it("removes bot mention from message text", async () => {
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
        event: makeEvent({ text: "<@U12345> please help me" }),
        say,
        client: makeClient(),
      });

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
        client: makeClient(),
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
        client: makeClient(),
      });

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
      threadMap.set(threadTs, { contextId: "existing-ctx", agentKey: "product-owner" });

      await mock.fireMention({
        event: makeEvent({
          text: "<@U12345> follow up question",
          thread_ts: threadTs,
          ts: "1700000002.000099",
        }),
        say,
        client: makeClient(),
      });

      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10001",
        "follow up question",
        "existing-ctx",
      );
      expect(threadMap.get(threadTs)?.contextId).toBe("existing-ctx");
    });
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  describe("error handling", () => {
    it("posts agent error response with blocks when response.error is set", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        error: { code: -32000, message: "Something went wrong" },
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> do something" }),
        say,
        client: makeClient(),
      });

      expect(say).toHaveBeenCalledWith(
        expect.objectContaining({
          text: expect.stringContaining(":x:"),
          blocks: expect.any(Array),
          thread_ts: expect.any(String),
        }),
      );
    });

    it("posts warning message with blocks when HTTP error occurs", async () => {
      const say = makeSay();
      mockSendMessage.mockRejectedValue(new Error("ECONNREFUSED"));

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> do something" }),
        say,
        client: makeClient(),
      });

      expect(say).toHaveBeenCalledWith(
        expect.objectContaining({
          text: expect.stringContaining(":warning:"),
          blocks: expect.any(Array),
          thread_ts: expect.any(String),
        }),
      );
    });
  });

  // -------------------------------------------------------------------------
  // Successful response
  // -------------------------------------------------------------------------

  describe("successful response", () => {
    it("posts extracted text from agent task result with blocks", async () => {
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
        client: makeClient(),
      });

      expect(say).toHaveBeenCalledWith(
        expect.objectContaining({
          text: "Here is the board summary.",
          blocks: expect.any(Array),
          thread_ts: expect.any(String),
        }),
      );
    });

    it("posts no-response blocks when result is undefined", async () => {
      const say = makeSay();
      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: undefined,
      });

      await mock.fireMention({
        event: makeEvent({ text: "<@U12345> do something" }),
        say,
        client: makeClient(),
      });

      expect(say).toHaveBeenCalledWith(
        expect.objectContaining({
          text: "_No response from agent._",
          blocks: expect.any(Array),
          thread_ts: expect.any(String),
        }),
      );
    });
  });
});
