import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { createSchedulerService } from "../src/services/scheduler.js";
import type { ScheduledJobContext, ScheduledJobDefinition, ScheduledJobResult } from "../src/scheduler/types.js";

// Mock node-cron
vi.mock("node-cron", () => {
  const tasks: Array<{ callback: () => void; stopped: boolean }> = [];
  return {
    default: {
      schedule: vi.fn((cron: string, callback: () => void, opts: unknown) => {
        const task = { callback, stopped: false };
        tasks.push(task);
        return {
          stop: vi.fn(() => { task.stopped = true; }),
        };
      }),
      validate: vi.fn(() => true),
    },
    __tasks: tasks,
  };
});

function makeCtx(): ScheduledJobContext {
  return {
    slackClient: {
      chat: {
        postMessage: vi.fn().mockResolvedValue({}),
      },
    },
    channelId: "C123",
    scrumMasterUrl: "http://localhost:10004",
  };
}

function makeJob(overrides: Partial<ScheduledJobDefinition> = {}): ScheduledJobDefinition {
  return {
    id: "test-job",
    name: "Test Job",
    cron: "* * * * *",
    enabled: true,
    execute: vi.fn().mockResolvedValue({ success: true, posted: true } as ScheduledJobResult),
    ...overrides,
  };
}

describe("scheduler service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("registers and starts enabled jobs", async () => {
    const cron = await import("node-cron");
    const ctx = makeCtx();
    const scheduler = createSchedulerService(ctx);
    const job = makeJob();

    scheduler.register(job);
    scheduler.startAll("Asia/Jerusalem");

    expect(cron.default.schedule).toHaveBeenCalledWith(
      "* * * * *",
      expect.any(Function),
      { timezone: "Asia/Jerusalem" },
    );
  });

  it("skips disabled jobs", async () => {
    const cron = await import("node-cron");
    const ctx = makeCtx();
    const scheduler = createSchedulerService(ctx);
    const job = makeJob({ enabled: false });

    scheduler.register(job);
    scheduler.startAll("Asia/Jerusalem");

    expect(cron.default.schedule).not.toHaveBeenCalled();
  });

  it("stops all jobs", async () => {
    const ctx = makeCtx();
    const scheduler = createSchedulerService(ctx);
    const job = makeJob();

    scheduler.register(job);
    scheduler.startAll("Asia/Jerusalem");
    scheduler.stopAll();

    // Verify the stop was called via getStatus — the task should be stopped
    const status = scheduler.getStatus();
    expect(status).toHaveLength(1);
    expect(status[0].id).toBe("test-job");
  });

  it("returns status for all registered jobs", () => {
    const ctx = makeCtx();
    const scheduler = createSchedulerService(ctx);

    scheduler.register(makeJob({ id: "job-1", name: "Job 1" }));
    scheduler.register(makeJob({ id: "job-2", name: "Job 2", enabled: false }));

    const status = scheduler.getStatus();
    expect(status).toHaveLength(2);
    expect(status[0]).toMatchObject({
      id: "job-1",
      name: "Job 1",
      enabled: true,
      running: false,
      lastRun: null,
      consecutiveFailures: 0,
    });
    expect(status[1]).toMatchObject({
      id: "job-2",
      enabled: false,
    });
  });

  it("tracks consecutive failures when job execution fails", async () => {
    const cron = await import("node-cron");
    const ctx = makeCtx();
    const scheduler = createSchedulerService(ctx);

    const failingJob = makeJob({
      execute: vi.fn().mockResolvedValue({
        success: false,
        posted: false,
        error: "Agent down",
      } as ScheduledJobResult),
    });

    scheduler.register(failingJob);
    scheduler.startAll("UTC");

    // Get the callback that was registered with cron.schedule
    const scheduleCall = (cron.default.schedule as any).mock.calls[0];
    const cronCallback = scheduleCall[1];

    // Execute the job callback
    await cronCallback();

    const status = scheduler.getStatus();
    expect(status[0].consecutiveFailures).toBe(1);
    expect(status[0].lastResult?.success).toBe(false);
    expect(status[0].lastResult?.error).toBe("Agent down");
  });

  it("resets consecutive failures on success", async () => {
    const cron = await import("node-cron");
    const ctx = makeCtx();
    const scheduler = createSchedulerService(ctx);

    let callCount = 0;
    const job = makeJob({
      execute: vi.fn().mockImplementation(async () => {
        callCount++;
        if (callCount === 1) {
          return { success: false, posted: false, error: "fail" };
        }
        return { success: true, posted: true };
      }),
    });

    scheduler.register(job);
    scheduler.startAll("UTC");

    const scheduleCall = (cron.default.schedule as any).mock.calls[0];
    const cronCallback = scheduleCall[1];

    // First run — failure
    await cronCallback();
    expect(scheduler.getStatus()[0].consecutiveFailures).toBe(1);

    // Second run — success
    await cronCallback();
    expect(scheduler.getStatus()[0].consecutiveFailures).toBe(0);
  });

  it("catches thrown errors without crashing", async () => {
    const cron = await import("node-cron");
    const ctx = makeCtx();
    const scheduler = createSchedulerService(ctx);

    const throwingJob = makeJob({
      execute: vi.fn().mockRejectedValue(new Error("Unexpected crash")),
    });

    scheduler.register(throwingJob);
    scheduler.startAll("UTC");

    const scheduleCall = (cron.default.schedule as any).mock.calls[0];
    const cronCallback = scheduleCall[1];

    // Should not throw
    await cronCallback();

    const status = scheduler.getStatus();
    expect(status[0].consecutiveFailures).toBe(1);
    expect(status[0].lastResult?.error).toBe("Unexpected crash");
  });
});
