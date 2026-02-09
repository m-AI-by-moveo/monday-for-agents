import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const {
  mockSendMessage,
  mockGetTask,
  mockCalendarHandleRequest,
  mockDriveHandleRequest,
  MockCalendarAgent,
  MockDriveAgent,
} = vi.hoisted(() => {
  const mockCalendarHandleRequest = vi.fn().mockResolvedValue("Here are your events for today...");
  const mockDriveHandleRequest = vi.fn().mockResolvedValue("Found 3 files matching your query.");

  class MockCalendarAgent {
    handleRequest = mockCalendarHandleRequest;
  }
  class MockDriveAgent {
    handleRequest = mockDriveHandleRequest;
  }

  return {
    mockSendMessage: vi.fn(),
    mockGetTask: vi.fn(),
    mockCalendarHandleRequest,
    mockDriveHandleRequest,
    MockCalendarAgent,
    MockDriveAgent,
  };
});

vi.mock("../src/services/a2a-client.js", () => ({
  createA2AClient: () => ({
    sendMessage: mockSendMessage,
    getTask: mockGetTask,
  }),
  extractTextFromTask: vi.fn(() => "status text"),
  AGENT_URLS: {
    "product-owner": "http://localhost:10001",
    "scrum-master": "http://localhost:10004",
  },
}));

vi.mock("../src/ui/block-builder.js", () => ({
  agentListBlocks: () => ({ blocks: [], text: "agents" }),
  statusDashboardBlocks: () => ({ blocks: [], text: "status" }),
  schedulerStatusBlocks: () => ({ blocks: [], text: "scheduler" }),
  loadingBlocks: () => ({ blocks: [], text: "loading" }),
  errorBlocks: (msg: string) => ({ blocks: [{ type: "section" }], text: `:x: ${msg}` }),
  warningBlocks: (msg: string) => ({ blocks: [], text: `:warning: ${msg}` }),
}));

vi.mock("../src/ui/google-blocks.js", () => ({
  googleConnectBlocks: (url: string) => ({
    blocks: [{ type: "section", url }],
    text: "Connect your Google account",
  }),
  googleStatusBlocks: (connected: boolean) => ({
    blocks: [{ type: "section" }],
    text: connected ? "Connected" : "Not connected",
  }),
}));

vi.mock("../src/services/google-calendar-agent.js", () => ({
  GoogleCalendarAgent: MockCalendarAgent,
}));

vi.mock("../src/services/google-drive-agent.js", () => ({
  GoogleDriveAgent: MockDriveAgent,
}));

import { registerCommands } from "../src/handlers/commands.js";
import type { GoogleServices } from "../src/handlers/commands.js";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockGoogleServices(): GoogleServices {
  return {
    auth: {
      getAuthUrl: vi.fn().mockReturnValue("https://accounts.google.com/mock"),
      handleCallback: vi.fn(),
      getClient: vi.fn(),
      isConnected: vi.fn().mockReturnValue(false),
      disconnect: vi.fn().mockResolvedValue(undefined),
    } as any,
    calendar: {
      listEvents: vi.fn().mockResolvedValue([]),
      createEvent: vi.fn().mockResolvedValue({ summary: "Test", start: "now", end: "later" }),
      updateEvent: vi.fn().mockResolvedValue({ summary: "Updated" }),
      deleteEvent: vi.fn().mockResolvedValue(undefined),
    } as any,
    drive: {
      listFiles: vi.fn().mockResolvedValue([]),
      searchFiles: vi.fn().mockResolvedValue([]),
      readFile: vi.fn().mockResolvedValue("file content"),
      createFile: vi.fn().mockResolvedValue({ id: "f1", name: "test.doc" }),
      deleteFile: vi.fn().mockResolvedValue(undefined),
    } as any,
  };
}

function createMockApp(googleServices?: GoogleServices | null) {
  const commandCallbacks = new Map<string, (args: Record<string, unknown>) => Promise<void>>();

  const app = {
    command: vi.fn((name: string, cb: (args: Record<string, unknown>) => Promise<void>) => {
      commandCallbacks.set(name, cb);
    }),
  };

  registerCommands(app as any, null, googleServices);

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

describe("/google command", () => {
  let google: GoogleServices;
  let mock: ReturnType<typeof createMockApp>;

  beforeEach(() => {
    google = createMockGoogleServices();
    mock = createMockApp(google);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("registers /google, /gcal, /gdrive commands", () => {
    expect(mock.app.command).toHaveBeenCalledWith("/google", expect.any(Function));
    expect(mock.app.command).toHaveBeenCalledWith("/gcal", expect.any(Function));
    expect(mock.app.command).toHaveBeenCalledWith("/gdrive", expect.any(Function));
  });

  describe("/google connect", () => {
    it("returns auth URL blocks", async () => {
      const ack = makeAck();
      const respond = makeRespond();
      const command = { text: "connect", user_id: "U123" };

      await mock.fireCommand("/google", { ack, respond, command });

      expect(ack).toHaveBeenCalledOnce();
      expect(google.auth.getAuthUrl).toHaveBeenCalledWith("U123");
      expect(respond).toHaveBeenCalledWith(
        expect.objectContaining({ response_type: "ephemeral", text: "Connect your Google account" }),
      );
    });
  });

  describe("/google disconnect", () => {
    it("disconnects and confirms", async () => {
      const ack = makeAck();
      const respond = makeRespond();
      const command = { text: "disconnect", user_id: "U123" };

      await mock.fireCommand("/google", { ack, respond, command });

      expect(google.auth.disconnect).toHaveBeenCalledWith("U123");
      expect(respond).toHaveBeenCalledWith(
        expect.objectContaining({ text: expect.stringContaining("disconnected") }),
      );
    });
  });

  describe("/google status", () => {
    it("shows not connected by default", async () => {
      const ack = makeAck();
      const respond = makeRespond();
      const command = { text: "status", user_id: "U123" };

      await mock.fireCommand("/google", { ack, respond, command });

      expect(google.auth.isConnected).toHaveBeenCalledWith("U123");
      expect(respond).toHaveBeenCalledWith(
        expect.objectContaining({ text: "Not connected" }),
      );
    });

    it("shows connected when user has tokens", async () => {
      (google.auth.isConnected as ReturnType<typeof vi.fn>).mockReturnValue(true);
      const ack = makeAck();
      const respond = makeRespond();
      const command = { text: "status", user_id: "U123" };

      await mock.fireCommand("/google", { ack, respond, command });

      expect(respond).toHaveBeenCalledWith(
        expect.objectContaining({ text: "Connected" }),
      );
    });
  });

  describe("/google when integration disabled", () => {
    it("shows disabled message", async () => {
      const m = createMockApp(null);
      const ack = makeAck();
      const respond = makeRespond();
      const command = { text: "connect", user_id: "U123" };

      await m.fireCommand("/google", { ack, respond, command });

      expect(respond).toHaveBeenCalledWith(
        expect.objectContaining({ text: "Google integration is not configured." }),
      );
    });
  });
});

describe("/gcal command (LLM-powered)", () => {
  let google: GoogleServices;
  let mock: ReturnType<typeof createMockApp>;

  beforeEach(() => {
    mockCalendarHandleRequest.mockReset();
    mockCalendarHandleRequest.mockResolvedValue("Here are your events for today...");
    google = createMockGoogleServices();
    (google.auth.isConnected as ReturnType<typeof vi.fn>).mockReturnValue(true);
    mock = createMockApp(google);
  });

  it("prompts connect when not authenticated", async () => {
    (google.auth.isConnected as ReturnType<typeof vi.fn>).mockReturnValue(false);
    mock = createMockApp(google);

    const ack = makeAck();
    const respond = makeRespond();
    const command = { text: "what do I have today?", user_id: "U123" };

    await mock.fireCommand("/gcal", { ack, respond, command });

    expect(respond).toHaveBeenCalledWith(
      expect.objectContaining({ text: "Connect your Google account" }),
    );
  });

  it("shows help when no text is provided", async () => {
    const ack = makeAck();
    const respond = makeRespond();
    const command = { text: "", user_id: "U123" };

    await mock.fireCommand("/gcal", { ack, respond, command });

    expect(respond).toHaveBeenCalledWith(
      expect.objectContaining({ text: expect.stringContaining("Tell me what you need") }),
    );
  });

  it("routes free-text to the calendar agent", async () => {
    const ack = makeAck();
    const respond = makeRespond();
    const command = { text: "what do I have today?", user_id: "U123" };

    await mock.fireCommand("/gcal", { ack, respond, command });

    expect(mockCalendarHandleRequest).toHaveBeenCalledWith(
      "what do I have today?",
      google.calendar,
      "U123",
    );
    // First call is loading, second is the agent result
    expect(respond).toHaveBeenCalledTimes(2);
    expect(respond).toHaveBeenLastCalledWith(
      expect.objectContaining({ text: "Here are your events for today..." }),
    );
  });

  it("shows error when agent throws", async () => {
    mockCalendarHandleRequest.mockRejectedValueOnce(new Error("API failure"));
    const ack = makeAck();
    const respond = makeRespond();
    const command = { text: "book something", user_id: "U123" };

    await mock.fireCommand("/gcal", { ack, respond, command });

    expect(respond).toHaveBeenLastCalledWith(
      expect.objectContaining({ text: expect.stringContaining("API failure") }),
    );
  });
});

describe("/gdrive command (LLM-powered)", () => {
  let google: GoogleServices;
  let mock: ReturnType<typeof createMockApp>;

  beforeEach(() => {
    mockDriveHandleRequest.mockReset();
    mockDriveHandleRequest.mockResolvedValue("Found 3 files matching your query.");
    google = createMockGoogleServices();
    (google.auth.isConnected as ReturnType<typeof vi.fn>).mockReturnValue(true);
    mock = createMockApp(google);
  });

  it("shows help when no text is provided", async () => {
    const ack = makeAck();
    const respond = makeRespond();
    const command = { text: "", user_id: "U123" };

    await mock.fireCommand("/gdrive", { ack, respond, command });

    expect(respond).toHaveBeenCalledWith(
      expect.objectContaining({ text: expect.stringContaining("Tell me what you need") }),
    );
  });

  it("routes free-text to the drive agent", async () => {
    const ack = makeAck();
    const respond = makeRespond();
    const command = { text: "find the Q4 report", user_id: "U123" };

    await mock.fireCommand("/gdrive", { ack, respond, command });

    expect(mockDriveHandleRequest).toHaveBeenCalledWith(
      "find the Q4 report",
      google.drive,
      "U123",
    );
    expect(respond).toHaveBeenCalledTimes(2);
    expect(respond).toHaveBeenLastCalledWith(
      expect.objectContaining({ text: "Found 3 files matching your query." }),
    );
  });

  it("shows error when agent throws", async () => {
    mockDriveHandleRequest.mockRejectedValueOnce(new Error("Drive offline"));
    const ack = makeAck();
    const respond = makeRespond();
    const command = { text: "show files", user_id: "U123" };

    await mock.fireCommand("/gdrive", { ack, respond, command });

    expect(respond).toHaveBeenLastCalledWith(
      expect.objectContaining({ text: expect.stringContaining("Drive offline") }),
    );
  });
});
