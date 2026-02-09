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

// Mock block-builder
vi.mock("../src/ui/block-builder.js", () => ({
  agentListBlocks: (agents: Record<string, string>) => {
    const lines = Object.entries(agents).map(([name, url]) => `*${name}* → \`${url}\``);
    const text = `Registered Agents: ${Object.keys(agents).join(", ")}`;
    return { blocks: [{ type: "header" }, { type: "section", text: { text: lines.join("\n") } }], text };
  },
  statusDashboardBlocks: (statusText: string) => ({
    blocks: [{ type: "header" }, { type: "section", text: { text: statusText } }],
    text: statusText,
  }),
  loadingBlocks: (msg: string) => ({
    blocks: [{ type: "section", text: { text: `:hourglass_flowing_sand: ${msg}` } }],
    text: `:hourglass_flowing_sand: ${msg}`,
  }),
  errorBlocks: (msg: string) => ({
    blocks: [{ type: "section", text: { text: `:x: ${msg}` } }],
    text: `:x: ${msg}`,
  }),
  warningBlocks: (msg: string) => ({
    blocks: [{ type: "section", text: { text: `:warning: ${msg}` } }],
    text: `:warning: ${msg}`,
  }),
  schedulerStatusBlocks: (jobs: any[]) => ({
    blocks: [{ type: "header" }, ...jobs.map((j: any) => ({ type: "section", job: j.name }))],
    text: `Scheduler Status: ${jobs.map((j: any) => j.name).join(", ")}`,
  }),
}));

import { registerCommands } from "../src/handlers/commands.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockApp(scheduler?: any) {
  const commandCallbacks = new Map<string, (args: Record<string, unknown>) => Promise<void>>();

  const app = {
    command: vi.fn((name: string, cb: (args: Record<string, unknown>) => Promise<void>) => {
      commandCallbacks.set(name, cb);
    }),
  };

  registerCommands(app as any, scheduler);

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

    it("returns a list of all agent names and URLs with blocks", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      await mock.fireCommand("/agents", { ack, respond });

      expect(respond).toHaveBeenCalledTimes(1);
      const call = respond.mock.calls[0][0] as { response_type: string; text: string; blocks: any[] };
      expect(call.response_type).toBe("ephemeral");
      expect(call.blocks).toBeDefined();
      expect(Array.isArray(call.blocks)).toBe(true);

      // Verify all four agents appear in the response text
      expect(call.text).toContain("product-owner");
      expect(call.text).toContain("developer");
      expect(call.text).toContain("reviewer");
      expect(call.text).toContain("scrum-master");
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
      expect(ack.mock.invocationCallOrder[0]).toBeLessThan(
        respond.mock.invocationCallOrder[0],
      );
    });

    it("sends query to scrum-master agent and returns blocks", async () => {
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

      expect(mockSendMessage).toHaveBeenCalledWith(
        "http://localhost:10004",
        "Give me the current board status summary.",
      );

      // respond is called twice: once with loading, once with result
      expect(respond).toHaveBeenCalledTimes(2);

      // First call: ephemeral loading with blocks
      const firstCall = respond.mock.calls[0][0] as { response_type: string; blocks: any[]; text: string };
      expect(firstCall.response_type).toBe("ephemeral");
      expect(firstCall.blocks).toBeDefined();
      expect(firstCall.text).toContain("Fetching");

      // Second call: in_channel with status blocks
      const secondCall = respond.mock.calls[1][0] as { response_type: string; blocks: any[]; text: string };
      expect(secondCall.response_type).toBe("in_channel");
      expect(secondCall.blocks).toBeDefined();
      expect(secondCall.text).toBe("Sprint is on track.");
    });

    it("handles agent error gracefully with error blocks", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      mockSendMessage.mockResolvedValue({
        jsonrpc: "2.0",
        id: "1",
        error: { code: -32000, message: "Agent is broken" },
      });

      await mock.fireCommand("/status", { ack, respond });

      expect(respond).toHaveBeenCalledTimes(2);

      const secondCall = respond.mock.calls[1][0] as { text: string; blocks: any[] };
      expect(secondCall.text).toContain(":x:");
      expect(secondCall.text).toContain("Agent is broken");
      expect(secondCall.blocks).toBeDefined();
    });

    it("handles agent unreachable (sendMessage throws) with warning blocks", async () => {
      const ack = makeAck();
      const respond = makeRespond();

      mockSendMessage.mockRejectedValue(new Error("ECONNREFUSED"));

      await mock.fireCommand("/status", { ack, respond });

      expect(respond).toHaveBeenCalledTimes(2);

      const secondCall = respond.mock.calls[1][0] as { text: string; blocks: any[] };
      expect(secondCall.text).toContain(":warning:");
      expect(secondCall.text).toContain("Could not reach");
      expect(secondCall.blocks).toBeDefined();
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
  // /scheduler
  // -------------------------------------------------------------------------

  describe("/scheduler", () => {
    it("acks immediately", async () => {
      const mockScheduler = {
        getStatus: vi.fn().mockReturnValue([]),
      };
      const m = createMockApp(mockScheduler);
      const ack = makeAck();
      const respond = makeRespond();

      await m.fireCommand("/scheduler", { ack, respond });

      expect(ack).toHaveBeenCalledTimes(1);
    });

    it("returns scheduler status blocks when scheduler is available", async () => {
      const sampleJobs = [
        {
          id: "daily-standup",
          name: "Daily Standup",
          enabled: true,
          cron: "0 9 * * 1-5",
          running: false,
          lastRun: new Date(),
          lastResult: { success: true, posted: true },
          consecutiveFailures: 0,
        },
        {
          id: "stale-tasks",
          name: "Stale Task Checker",
          enabled: false,
          cron: "0 14 * * 1-5",
          running: false,
          lastRun: null,
          lastResult: null,
          consecutiveFailures: 0,
        },
      ];
      const mockScheduler = {
        getStatus: vi.fn().mockReturnValue(sampleJobs),
      };
      const m = createMockApp(mockScheduler);
      const ack = makeAck();
      const respond = makeRespond();

      await m.fireCommand("/scheduler", { ack, respond });

      expect(mockScheduler.getStatus).toHaveBeenCalledTimes(1);
      expect(respond).toHaveBeenCalledTimes(1);

      const call = respond.mock.calls[0][0] as { response_type: string; text: string; blocks: any[] };
      expect(call.response_type).toBe("ephemeral");
      expect(call.blocks).toBeDefined();
      expect(call.text).toContain("Daily Standup");
      expect(call.text).toContain("Stale Task Checker");
    });

    it("returns disabled message when scheduler is null", async () => {
      const m = createMockApp(null);
      const ack = makeAck();
      const respond = makeRespond();

      await m.fireCommand("/scheduler", { ack, respond });

      expect(respond).toHaveBeenCalledTimes(1);

      const call = respond.mock.calls[0][0] as { response_type: string; text: string };
      expect(call.response_type).toBe("ephemeral");
      expect(call.text).toContain("Scheduler is disabled");
    });
  });

  // -------------------------------------------------------------------------
  // Registration
  // -------------------------------------------------------------------------

  describe("registration", () => {
    it("registers /agents, /status, and /scheduler commands", () => {
      expect(mock.app.command).toHaveBeenCalledWith("/agents", expect.any(Function));
      expect(mock.app.command).toHaveBeenCalledWith("/status", expect.any(Function));
      expect(mock.app.command).toHaveBeenCalledWith("/scheduler", expect.any(Function));
    });
  });
});
