import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import nock from "nock";
import type { ScheduledJobContext } from "../src/scheduler/types.js";

// ---------------------------------------------------------------------------
// Test helpers
// ---------------------------------------------------------------------------

function makeCtx(): ScheduledJobContext {
  return {
    slackClient: {
      chat: {
        postMessage: vi.fn().mockResolvedValue({}),
      },
    },
    channelId: "C-TEST",
    scrumMasterUrl: "http://localhost:10004",
  };
}

function a2aSuccessReply(text: string) {
  return {
    jsonrpc: "2.0",
    id: "rpc-1",
    result: {
      id: "task-1",
      contextId: "ctx-1",
      status: {
        state: "completed",
        message: {
          role: "agent",
          parts: [{ type: "text", text }],
        },
      },
    },
  };
}

function a2aErrorReply(message: string) {
  return {
    jsonrpc: "2.0",
    id: "rpc-1",
    error: { code: -32000, message },
  };
}

// ---------------------------------------------------------------------------
// Daily Standup
// ---------------------------------------------------------------------------

describe("daily-standup job", () => {
  beforeEach(() => {
    vi.resetModules();
    nock.cleanAll();
  });

  afterEach(() => {
    nock.cleanAll();
    nock.enableNetConnect();
  });

  it("posts standup report to Slack on success", async () => {
    const scope = nock("http://localhost:10004")
      .post("/")
      .reply(200, a2aSuccessReply("In Progress: task-1\nBlocked: none"));

    const { createDailyStandupJob } = await import(
      "../src/scheduler/jobs/daily-standup.js"
    );
    const job = createDailyStandupJob(true, "0 9 * * 1-5");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(true);
    expect(result.posted).toBe(true);
    expect(ctx.slackClient.chat.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        channel: "C-TEST",
        text: expect.stringContaining("In Progress: task-1"),
      }),
    );
    expect(scope.isDone()).toBe(true);
  });

  it("returns failure when A2A returns error", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, a2aErrorReply("Agent unavailable"));

    const { createDailyStandupJob } = await import(
      "../src/scheduler/jobs/daily-standup.js"
    );
    const job = createDailyStandupJob(true, "0 9 * * 1-5");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(false);
    expect(result.posted).toBe(false);
    expect(result.error).toContain("Agent unavailable");
  });

  it("returns failure when A2A returns no result", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, { jsonrpc: "2.0", id: "rpc-1" });

    const { createDailyStandupJob } = await import(
      "../src/scheduler/jobs/daily-standup.js"
    );
    const job = createDailyStandupJob(true, "0 9 * * 1-5");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(false);
    expect(result.error).toContain("No result");
  });
});

// ---------------------------------------------------------------------------
// Stale Task Checker
// ---------------------------------------------------------------------------

describe("stale-task-checker job", () => {
  beforeEach(() => {
    vi.resetModules();
    nock.cleanAll();
  });

  afterEach(() => {
    nock.cleanAll();
    nock.enableNetConnect();
  });

  it("posts to Slack when stale tasks are found", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, a2aSuccessReply("Task X stuck for 3 hours"));

    const { createStaleTaskCheckerJob } = await import(
      "../src/scheduler/jobs/stale-task-checker.js"
    );
    const job = createStaleTaskCheckerJob(true, "*/30 * * * *");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(true);
    expect(result.posted).toBe(true);
    expect(ctx.slackClient.chat.postMessage).toHaveBeenCalled();
  });

  it("suppresses Slack post when NO_STALE_TASKS sentinel is returned", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, a2aSuccessReply("NO_STALE_TASKS"));

    const { createStaleTaskCheckerJob } = await import(
      "../src/scheduler/jobs/stale-task-checker.js"
    );
    const job = createStaleTaskCheckerJob(true, "*/30 * * * *");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(true);
    expect(result.posted).toBe(false);
    expect(ctx.slackClient.chat.postMessage).not.toHaveBeenCalled();
  });

  it("returns failure when A2A returns error", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, a2aErrorReply("timeout"));

    const { createStaleTaskCheckerJob } = await import(
      "../src/scheduler/jobs/stale-task-checker.js"
    );
    const job = createStaleTaskCheckerJob(true, "*/30 * * * *");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(false);
    expect(result.posted).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Weekly Summary
// ---------------------------------------------------------------------------

describe("weekly-summary job", () => {
  beforeEach(() => {
    vi.resetModules();
    nock.cleanAll();
  });

  afterEach(() => {
    nock.cleanAll();
    nock.enableNetConnect();
  });

  it("posts weekly summary to Slack on success", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, a2aSuccessReply("Completed: 5 tasks. In progress: 2."));

    const { createWeeklySummaryJob } = await import(
      "../src/scheduler/jobs/weekly-summary.js"
    );
    const job = createWeeklySummaryJob(true, "0 9 * * 1");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(true);
    expect(result.posted).toBe(true);
    expect(ctx.slackClient.chat.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        channel: "C-TEST",
        text: expect.stringContaining("Completed: 5 tasks"),
      }),
    );
  });

  it("returns failure when A2A returns error", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, a2aErrorReply("Agent crash"));

    const { createWeeklySummaryJob } = await import(
      "../src/scheduler/jobs/weekly-summary.js"
    );
    const job = createWeeklySummaryJob(true, "0 9 * * 1");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(false);
    expect(result.error).toContain("Agent crash");
  });

  it("returns failure when A2A returns no result", async () => {
    nock("http://localhost:10004")
      .post("/")
      .reply(200, { jsonrpc: "2.0", id: "rpc-1" });

    const { createWeeklySummaryJob } = await import(
      "../src/scheduler/jobs/weekly-summary.js"
    );
    const job = createWeeklySummaryJob(true, "0 9 * * 1");
    const ctx = makeCtx();

    const result = await job.execute(ctx);

    expect(result.success).toBe(false);
    expect(result.error).toContain("No result");
  });
});
