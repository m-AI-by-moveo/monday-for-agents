import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { MeetingSyncService } from "../src/services/meeting-sync.js";
import { MeetingStore } from "../src/services/meeting-store.js";
import type { MeetingNotesAgent, MeetingAnalysis } from "../src/services/meeting-notes-agent.js";
import type { GoogleAuthService } from "../src/services/google-auth.js";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

function createMockAuth() {
  return {
    getClient: vi.fn().mockResolvedValue({}),
    isConnected: vi.fn().mockReturnValue(true),
  } as unknown as GoogleAuthService;
}

function createMockSlackClient() {
  return {
    chat: {
      postMessage: vi.fn().mockResolvedValue({ ok: true }),
    },
  };
}

function createMockMeetingNotesAgent(analysis?: MeetingAnalysis) {
  const defaultAnalysis: MeetingAnalysis = {
    summary: "Team discussed upcoming features.",
    actionItems: [
      {
        title: "Build user dashboard",
        description: "Create the main dashboard view",
        assignee: "Alice",
        priority: "high",
      },
    ],
    decisions: ["Use React for frontend"],
  };

  return {
    analyzeMeetingTranscript: vi.fn().mockResolvedValue(analysis ?? defaultAnalysis),
  } as unknown as MeetingNotesAgent;
}

// Mock googleapis
vi.mock("googleapis", () => {
  let mockEvents: any[] = [];
  let mockFiles: any[] = [];
  let mockFileContent = "Sample transcript content for the meeting.";

  const calendarApi = {
    events: {
      list: vi.fn().mockImplementation(() =>
        Promise.resolve({ data: { items: mockEvents } }),
      ),
    },
  };

  const driveApi = {
    files: {
      list: vi.fn().mockImplementation(() =>
        Promise.resolve({ data: { files: mockFiles } }),
      ),
      export: vi.fn().mockImplementation(() =>
        Promise.resolve({ data: mockFileContent }),
      ),
    },
  };

  return {
    google: {
      calendar: vi.fn().mockReturnValue(calendarApi),
      drive: vi.fn().mockReturnValue(driveApi),
      // Expose setters for test control
      __setMockEvents: (events: any[]) => { mockEvents = events; },
      __setMockFiles: (files: any[]) => { mockFiles = files; },
      __setMockFileContent: (content: string) => { mockFileContent = content; },
      __getCalendarApi: () => calendarApi,
      __getDriveApi: () => driveApi,
    },
  };
});

// Access the mock controls
const { google } = await import("googleapis") as any;

describe("MeetingSyncService", () => {
  let store: MeetingStore;
  let slackClient: ReturnType<typeof createMockSlackClient>;

  beforeEach(() => {
    store = new MeetingStore(":memory:");
    slackClient = createMockSlackClient();
    vi.clearAllMocks();
  });

  afterEach(() => {
    store.close();
  });

  it("finds meeting, transcript, analyzes, and posts preview", async () => {
    google.__setMockEvents([
      {
        id: "evt-1",
        summary: "Sprint Planning",
        conferenceData: { conferenceId: "meet-123" },
        start: { dateTime: new Date().toISOString() },
        end: { dateTime: new Date().toISOString() },
      },
    ]);
    google.__setMockFiles([
      {
        id: "file-1",
        name: "Meeting transcript - Sprint Planning",
        mimeType: "application/vnd.google-apps.document",
      },
    ]);
    google.__setMockFileContent("Alice: Let's build the dashboard. Bob: I agree.");

    const auth = createMockAuth();
    const agent = createMockMeetingNotesAgent();

    const service = new MeetingSyncService(auth, store, agent, slackClient, "C123");
    const result = await service.checkRecentMeetings("U_ADMIN");

    expect(result.meetingsFound).toBe(1);
    expect(result.transcriptsFound).toBe(1);
    expect(result.previewsPosted).toBe(1);
    expect(result.errors).toHaveLength(0);
    expect(slackClient.chat.postMessage).toHaveBeenCalledOnce();
    expect(store.isProcessed("evt-1")).toBe(true);

    // Check message was posted with metadata
    const postCall = slackClient.chat.postMessage.mock.calls[0][0];
    expect(postCall.channel).toBe("C123");
    expect(postCall.metadata.event_type).toBe("meeting_analysis");
  });

  it("skips already-processed meetings", async () => {
    store.markPending("evt-1", "Already Processed");

    google.__setMockEvents([
      {
        id: "evt-1",
        summary: "Sprint Planning",
        conferenceData: { conferenceId: "meet-123" },
      },
    ]);

    const auth = createMockAuth();
    const agent = createMockMeetingNotesAgent();

    const service = new MeetingSyncService(auth, store, agent, slackClient, "C123");
    const result = await service.checkRecentMeetings("U_ADMIN");

    expect(result.meetingsFound).toBe(1);
    expect(result.skipped).toBe(1);
    expect(result.previewsPosted).toBe(0);
    expect(slackClient.chat.postMessage).not.toHaveBeenCalled();
  });

  it("handles missing transcript gracefully", async () => {
    google.__setMockEvents([
      {
        id: "evt-2",
        summary: "Quick Sync",
        hangoutLink: "https://meet.google.com/abc-def",
      },
    ]);
    google.__setMockFiles([]); // No transcript found

    const auth = createMockAuth();
    const agent = createMockMeetingNotesAgent();

    const service = new MeetingSyncService(auth, store, agent, slackClient, "C123");
    const result = await service.checkRecentMeetings("U_ADMIN");

    expect(result.meetingsFound).toBe(1);
    expect(result.transcriptsFound).toBe(0);
    expect(result.skipped).toBe(1);
    expect(result.previewsPosted).toBe(0);
  });

  it("handles no recent meetings", async () => {
    google.__setMockEvents([]);

    const auth = createMockAuth();
    const agent = createMockMeetingNotesAgent();

    const service = new MeetingSyncService(auth, store, agent, slackClient, "C123");
    const result = await service.checkRecentMeetings("U_ADMIN");

    expect(result.meetingsFound).toBe(0);
    expect(result.previewsPosted).toBe(0);
  });

  it("skips non-Meet events", async () => {
    google.__setMockEvents([
      {
        id: "evt-3",
        summary: "Regular Event",
        // No conferenceData or hangoutLink
      },
    ]);

    const auth = createMockAuth();
    const agent = createMockMeetingNotesAgent();

    const service = new MeetingSyncService(auth, store, agent, slackClient, "C123");
    const result = await service.checkRecentMeetings("U_ADMIN");

    expect(result.meetingsFound).toBe(0);
  });

  it("posts summary even when no action items are detected", async () => {
    google.__setMockEvents([
      {
        id: "evt-4",
        summary: "Casual Chat",
        conferenceData: { conferenceId: "meet-456" },
      },
    ]);
    google.__setMockFiles([
      {
        id: "file-2",
        name: "Meeting transcript - Casual Chat",
        mimeType: "application/vnd.google-apps.document",
      },
    ]);

    const noActionAnalysis: MeetingAnalysis = {
      summary: "Casual conversation, no tasks.",
      actionItems: [],
      decisions: [],
    };

    const auth = createMockAuth();
    const agent = createMockMeetingNotesAgent(noActionAnalysis);

    const service = new MeetingSyncService(auth, store, agent, slackClient, "C123");
    const result = await service.checkRecentMeetings("U_ADMIN");

    expect(result.transcriptsFound).toBe(1);
    expect(result.previewsPosted).toBe(1);
    expect(slackClient.chat.postMessage).toHaveBeenCalledOnce();
    expect(store.isProcessed("evt-4")).toBe(true);
  });
});
