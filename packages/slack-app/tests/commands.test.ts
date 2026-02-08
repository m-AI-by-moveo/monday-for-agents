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

import { registerCommands } from "../src/handlers/commands.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockApp() {
  const commandCallbacks = new Map<string, (args: Record<string, unknown>) => Promise<void>>();

  const app = {
    command: vi.fn((name: string, cb: (args: Record<string, unknown>) => Promise<void>) => {
      commandCallbacks.set(name, cb);
    }),
  };

  registerCommands(app as any);

  return {
    app,
    fireCommand: (name: string, args: Record<string, unknown>) => {
      const cb = commandCallbacks.get(name);
      if (!cb) throw new Error(`No command handler registered for ${name}`);
      return cb(args);
    },
  };
}

function makeAck() {
  return vi.fn().mockResolvedValue(undefined);
}

function makeRespond() {
  return vi.fn().mockResolvedValue(undefined);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("commands handler", () => {
  let mock: ReturnType<typeof createMockApp>;

  beforeEach(() => {
    mockSendMessage.mockReset();
    mockGetTask.mockReset();
    mock = createMockApp();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  // -------------------------------------------------------------------------
  // /agents
  // -------------------------------------------------------------------------

  describe("/agents", () => {
    it("acks immediately", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      await mock.fireCommand("/agents", { ack, respond });

      expect(ack).toHaveBeenCalledTimes(1);
    });

    it("returns a list of all agent names and URLs", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      await mock.fireCommand("/agents", { ack, respond });

      expect(respond).toHaveBeenCalledTimes(1);
      const call = respond.mock.calls[0][0] as { response_type: string; text: string };
      expect(call.response_type).toBe("ephemeral");

      // Verify all four agents appear in the response text
      expect(call.text).toContain("product-owner");
      expect(call.text).toContain("developer");
      expect(call.text).toContain("reviewer");
      expect(call.text).toContain("scrum-master");

      expect(call.text).toContain("http://localhost:10001");
      expect(call.text).toContain("http://localhost:10002");
      expect(call.text).toContain("http://localhost:10003");
      expect(call.text).toContain("http://localhost:10004");
    });
  });

  // -------------------------------------------------------------------------
  // /status
  // -------------------------------------------------------------------------

  describe("/status", () => {
    it("acks immediately", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: {
            state: "completed",
            message: { role: "agent", parts: [{ type: "text", text: "status ok" }] },
          },
        },
      });

      await mock.fireCommand("/status", { ack, respond });

      expect(ack).toHaveBeenCalledTimes(1);
      // ack should be called before respond
      expect(ack.mock.invocationCallOrder[0]).toBeLessThan(
        respond.mock.invocationCallOrder[0],
      );
    });

    it("sends query to scrum-master agent", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: {
          id: "t1",
          contextId: "c1",
          status: {
            state: "completed",
            message: {
              role: "agent",
              parts: [{ type: "text", text: "Sprint is on track." }],
            },
          },
        },
      });

      await mock.fireCommand("/status", { ack, respond });

      // Should call sendMessage with the scrum-master URL
      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10004",
        "Give me the current board status summary.",
      );

      // respond is called twice: once with "fetching" message, once with result
      expect(respond).toHaveBeenCalledTimes(2);

      // First call: ephemeral "fetching" message
      const firstCall = respond.mock.calls[0][0] as { response_type: string; text: string };
      expect(firstCall.response_type).toBe("ephemeral");
      expect(firstCall.text).toContain("Fetching");

      // Second call: in_channel with actual status
      const secondCall = respond.mock.calls[1][0] as { response_type: string; text: string };
      expect(secondCall.response_type).toBe("in_channel");
      expect(secondCall.text).toBe("Sprint is on track.");
    });

    it("handles agent error gracefully", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        error: { code: -32000, message: "Agent is broken" },
      });

      await mock.fireCommand("/status", { ack, respond });

      expect(respond).toHaveBeenCalledTimes(2);

      const secondCall = respond.mock.calls[1][0] as { text: string };
      expect(secondCall.text).toContain(":x:");
      expect(secondCall.text).toContain("Agent is broken");
    });

    it("handles agent unreachable (sendMessage throws)", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      mockSendMessage.mockRejectedValue(new Error("ECONNREFUSED"));

      await mock.fireCommand("/status", { ack, respond });

      expect(respond).toHaveBeenCalledTimes(2);

      const secondCall = respond.mock.calls[1][0] as { text: string };
      expect(secondCall.text).toContain(":warning:");
      expect(secondCall.text).toContain("Could not reach");
    });

    it("returns no-status fallback when result is null", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        result: undefined,
      });

      await mock.fireCommand("/status", { ack, respond });

      const secondCall = respond.mock.calls[1][0] as { text: string };
      expect(secondCall.text).toContain("No status available");
    });
  });

  // -------------------------------------------------------------------------
  // Registration
  // -------------------------------------------------------------------------

  describe("registration", () => {
    it("registers both /agents and /status commands", () => {
      expect(mock.app.command).toHaveBeenCalledWith("/agents", expect.any(Function));
      expect(mock.app.command).toHaveBeenCalledWith("/status", expect.any(Function));
    });
  });
});
