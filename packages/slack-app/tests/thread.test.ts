import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// Mock a2a-client BEFORE importing the handler
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

// We import threadMap from the mention module so we can pre-populate it.
// The mention module also needs to be mocked consistently since thread.ts
// imports threadMap from mention.js.
// Because vi.mock hoists, and thread.ts does:
//   import { threadMap } from "./mention.js";
// We need to mock the mention module to export the real threadMap.
// Actually, since we already mock a2a-client.js above, and mention.ts
// uses a2a-client at module scope (const a2a = createA2AClient()),
// the mock will apply and mention.ts will load fine.

import { registerThreadHandler } from "../src/handlers/thread.js";
import { threadMap } from "../src/handlers/mention.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockApp() {
  let messageCallback: (args: Record<string, unknown>) => Promise<void>;

  const app = {
    event: vi.fn((eventName: string, cb: (args: Record<string, unknown>) => Promise<void>) => {
      if (eventName === "message") {
        messageCallback = cb;
      }
    }),
  };

  registerThreadHandler(app as any);

  return {
    app,
    fireMessage: (args: Record<string, unknown>) => messageCallback(args),
  };
}

function makeSay() {
  return vi.fn().mockResolvedValue(undefined);
}

function makeThreadEvent(overrides: Record<string, unknown> = {}) {
  return {
    text: "follow up question",
    ts: "1700000000.000099",
    thread_ts: "1700000000.000001",
    user: "U_HUMAN",
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("thread handler", () => {
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
  // Routing based on threadMap
  // -------------------------------------------------------------------------

  it("forwards thread reply to agent when active mapping exists", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-abc", agentKey: "product-owner" });

    mockSendMessage.mockResolvedValue({
      jsonrpc: "2.0",
      id: "1",
      result: {
        id: "t1",
        contextId: "ctx-abc",
        status: {
          state: "completed",
          message: { role: "agent", parts: [{ type: "text", text: "Agent reply" }] },
        },
      },
    });

    await mock.fireMessage({
      event: makeThreadEvent({ text: "follow up", thread_ts: threadTs }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(mockSendMessage).toHaveBeenCalledWith(
      "http://localhost:10001",
      "follow up",
      "ctx-abc",
    );
    expect(say).toHaveBeenCalledWith({
      text: "Agent reply",
      thread_ts: threadTs,
    });
  });

  it("ignores thread reply when no mapping exists", async () => {
    const say = makeSay();

    await mock.fireMessage({
      event: makeThreadEvent(),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(say).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Bot / subtype filtering
  // -------------------------------------------------------------------------

  it("ignores bot messages to prevent loops", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "developer" });

    await mock.fireMessage({
      event: makeThreadEvent({
        thread_ts: threadTs,
        bot_id: "B_OTHER_BOT",
      }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(say).not.toHaveBeenCalled();
  });

  it("ignores messages from our own bot user", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "developer" });

    await mock.fireMessage({
      event: makeThreadEvent({
        thread_ts: threadTs,
        user: "U_BOT",
      }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(say).not.toHaveBeenCalled();
  });

  it("ignores messages with a subtype", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "developer" });

    await mock.fireMessage({
      event: makeThreadEvent({
        thread_ts: threadTs,
        subtype: "message_changed",
      }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(say).not.toHaveBeenCalled();
  });

  it("ignores non-threaded messages (no thread_ts)", async () => {
    const say = makeSay();
    // Even with a mapping in the threadMap for some ts, a top-level message
    // without thread_ts should be ignored.
    threadMap.set("1700000000.000001", { contextId: "ctx-1", agentKey: "developer" });

    await mock.fireMessage({
      event: {
        text: "top-level message",
        ts: "1700000000.000099",
        user: "U_HUMAN",
        // No thread_ts
      },
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(say).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // Response posting
  // -------------------------------------------------------------------------

  it("posts agent response in the same thread", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "scrum-master" });

    mockSendMessage.mockResolvedValue({
      jsonrpc: "2.0",
      id: "1",
      result: {
        id: "t2",
        contextId: "ctx-1",
        status: {
          state: "completed",
          message: { role: "agent", parts: [{ type: "text", text: "Thread response" }] },
        },
      },
    });

    await mock.fireMessage({
      event: makeThreadEvent({ thread_ts: threadTs }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(say).toHaveBeenCalledWith({
      text: "Thread response",
      thread_ts: threadTs,
    });
  });

  it("posts fallback when agent result is undefined", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "scrum-master" });

    mockSendMessage.mockResolvedValue({
      jsonrpc: "2.0",
      id: "1",
      result: undefined,
    });

    await mock.fireMessage({
      event: makeThreadEvent({ thread_ts: threadTs }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(say).toHaveBeenCalledWith({
      text: "_No response from agent._",
      thread_ts: threadTs,
    });
  });

  // -------------------------------------------------------------------------
  // Error handling
  // -------------------------------------------------------------------------

  it("posts error response when agent returns JSON-RPC error", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "reviewer" });

    mockSendMessage.mockResolvedValue({
      jsonrpc: "2.0",
      id: "1",
      error: { code: -32000, message: "Internal error" },
    });

    await mock.fireMessage({
      event: makeThreadEvent({ thread_ts: threadTs }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(say).toHaveBeenCalledWith({
      text: ":x: Agent error: Internal error",
      thread_ts: threadTs,
    });
  });

  it("posts warning message when agent is unreachable", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "developer" });

    mockSendMessage.mockRejectedValue(new Error("ECONNREFUSED"));

    await mock.fireMessage({
      event: makeThreadEvent({ thread_ts: threadTs }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(say).toHaveBeenCalledWith({
      text: expect.stringContaining(":warning:"),
      thread_ts: threadTs,
    });
    expect(say).toHaveBeenCalledWith({
      text: expect.stringContaining("developer"),
      thread_ts: threadTs,
    });
  });

  // -------------------------------------------------------------------------
  // Edge cases
  // -------------------------------------------------------------------------

  it("ignores empty text messages in tracked threads", async () => {
    const say = makeSay();
    const threadTs = "1700000000.000001";
    threadMap.set(threadTs, { contextId: "ctx-1", agentKey: "developer" });

    await mock.fireMessage({
      event: makeThreadEvent({ thread_ts: threadTs, text: "   " }),
      say,
      context: { botUserId: "U_BOT" },
    });

    expect(mockSendMessage).not.toHaveBeenCalled();
    expect(say).not.toHaveBeenCalled();
  });
});
