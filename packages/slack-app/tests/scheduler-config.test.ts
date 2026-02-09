import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

describe("scheduler config", () => {
  const ENV_KEYS = [
    "SCHEDULER_ENABLED",
    "SCHEDULER_TIMEZONE",
    "SLACK_CHANNEL_ID",
    "SCHEDULER_STANDUP_ENABLED",
    "SCHEDULER_STANDUP_CRON",
    "SCHEDULER_STALE_CHECK_ENABLED",
    "SCHEDULER_STALE_CHECK_CRON",
    "SCHEDULER_WEEKLY_ENABLED",
    "SCHEDULER_WEEKLY_CRON",
  ];

  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    for (const key of ENV_KEYS) {
      delete process.env[key];
    }
  });

  it("returns sensible defaults when no env vars are set (disabled due to empty channel)", async () => {
    delete process.env.SLACK_CHANNEL_ID;
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");
    const cfg = loadSchedulerConfig();

    expect(cfg.enabled).toBe(false);
    expect(cfg.timezone).toBe("Asia/Jerusalem");
    expect(cfg.standup.enabled).toBe(true);
    expect(cfg.standup.cron).toBe("0 9 * * 1-5");
    expect(cfg.staleCheck.enabled).toBe(true);
    expect(cfg.staleCheck.cron).toBe("*/30 * * * *");
    expect(cfg.weekly.enabled).toBe(true);
    expect(cfg.weekly.cron).toBe("0 9 * * 1");
  });

  it("is enabled when SLACK_CHANNEL_ID is set and SCHEDULER_ENABLED is not explicitly false", async () => {
    process.env.SLACK_CHANNEL_ID = "C123";
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");
    const cfg = loadSchedulerConfig();

    expect(cfg.enabled).toBe(true);
    expect(cfg.channelId).toBe("C123");
  });

  it("is disabled when SCHEDULER_ENABLED=false even with channel ID", async () => {
    process.env.SLACK_CHANNEL_ID = "C123";
    process.env.SCHEDULER_ENABLED = "false";
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");
    const cfg = loadSchedulerConfig();

    expect(cfg.enabled).toBe(false);
  });

  it("respects custom cron expressions", async () => {
    process.env.SLACK_CHANNEL_ID = "C123";
    process.env.SCHEDULER_STANDUP_CRON = "0 8 * * 1-5";
    process.env.SCHEDULER_STALE_CHECK_CRON = "*/15 * * * *";
    process.env.SCHEDULER_WEEKLY_CRON = "0 10 * * 5";
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");
    const cfg = loadSchedulerConfig();

    expect(cfg.standup.cron).toBe("0 8 * * 1-5");
    expect(cfg.staleCheck.cron).toBe("*/15 * * * *");
    expect(cfg.weekly.cron).toBe("0 10 * * 5");
  });

  it("respects custom timezone", async () => {
    process.env.SLACK_CHANNEL_ID = "C123";
    process.env.SCHEDULER_TIMEZONE = "America/New_York";
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");
    const cfg = loadSchedulerConfig();

    expect(cfg.timezone).toBe("America/New_York");
  });

  it("allows disabling individual jobs", async () => {
    process.env.SLACK_CHANNEL_ID = "C123";
    process.env.SCHEDULER_STANDUP_ENABLED = "false";
    process.env.SCHEDULER_STALE_CHECK_ENABLED = "false";
    process.env.SCHEDULER_WEEKLY_ENABLED = "false";
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");
    const cfg = loadSchedulerConfig();

    expect(cfg.enabled).toBe(true);
    expect(cfg.standup.enabled).toBe(false);
    expect(cfg.staleCheck.enabled).toBe(false);
    expect(cfg.weekly.enabled).toBe(false);
  });

  it("throws on invalid cron expression when enabled", async () => {
    process.env.SLACK_CHANNEL_ID = "C123";
    process.env.SCHEDULER_STANDUP_CRON = "not-a-cron";
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");

    expect(() => loadSchedulerConfig()).toThrow("Invalid cron expression");
  });

  it("does not validate cron when scheduler is disabled", async () => {
    process.env.SCHEDULER_ENABLED = "false";
    process.env.SCHEDULER_STANDUP_CRON = "not-a-cron";
    const { loadSchedulerConfig } = await import("../src/scheduler/config.js");

    // Should not throw even with invalid cron
    expect(() => loadSchedulerConfig()).not.toThrow();
  });
});
