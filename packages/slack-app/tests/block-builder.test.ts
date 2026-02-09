import { describe, it, expect } from "vitest";
import {
  agentResponseBlocks,
  errorBlocks,
  warningBlocks,
  agentListBlocks,
  statusDashboardBlocks,
  loadingBlocks,
  noResponseBlocks,
  schedulerStatusBlocks,
} from "../src/ui/block-builder.js";
import type { JobStatus } from "../src/scheduler/types.js";

describe("block-builder", () => {
  // -------------------------------------------------------------------------
  // agentResponseBlocks
  // -------------------------------------------------------------------------

  describe("agentResponseBlocks", () => {
    it("includes the response text in a section block", () => {
      const { blocks, text } = agentResponseBlocks("developer", "Here is the code.");
      expect(text).toBe("Here is the code.");
      expect(blocks).toHaveLength(2);
      expect(blocks[0]).toMatchObject({
        type: "section",
        text: { type: "mrkdwn", text: "Here is the code." },
      });
    });

    it("includes agent name in context block", () => {
      const { blocks } = agentResponseBlocks("scrum-master", "ok");
      const context = blocks[1] as any;
      expect(context.type).toBe("context");
      expect(context.elements[0].text).toContain("scrum-master");
    });
  });

  // -------------------------------------------------------------------------
  // errorBlocks
  // -------------------------------------------------------------------------

  describe("errorBlocks", () => {
    it("prefixes message with :x: emoji", () => {
      const { blocks, text } = errorBlocks("Something went wrong");
      expect(text).toBe(":x: Something went wrong");
      expect(blocks).toHaveLength(1);
      expect(blocks[0]).toMatchObject({
        type: "section",
        text: { type: "mrkdwn", text: ":x: Something went wrong" },
      });
    });
  });

  // -------------------------------------------------------------------------
  // warningBlocks
  // -------------------------------------------------------------------------

  describe("warningBlocks", () => {
    it("prefixes message with :warning: emoji", () => {
      const { blocks, text } = warningBlocks("Agent unreachable");
      expect(text).toBe(":warning: Agent unreachable");
      expect(blocks).toHaveLength(1);
      expect(blocks[0]).toMatchObject({
        type: "section",
        text: { type: "mrkdwn", text: ":warning: Agent unreachable" },
      });
    });
  });

  // -------------------------------------------------------------------------
  // agentListBlocks
  // -------------------------------------------------------------------------

  describe("agentListBlocks", () => {
    it("creates a header and list of agents", () => {
      const agents = {
        "product-owner": "http://localhost:10001",
        developer: "http://localhost:10002",
      };
      const { blocks, text } = agentListBlocks(agents);

      expect(text).toContain("product-owner");
      expect(text).toContain("developer");

      expect(blocks).toHaveLength(2);
      expect(blocks[0]).toMatchObject({
        type: "header",
        text: { type: "plain_text" },
      });
      const sectionText = (blocks[1] as any).text.text;
      expect(sectionText).toContain("product-owner");
      expect(sectionText).toContain("http://localhost:10001");
      expect(sectionText).toContain("developer");
      expect(sectionText).toContain("http://localhost:10002");
    });
  });

  // -------------------------------------------------------------------------
  // statusDashboardBlocks
  // -------------------------------------------------------------------------

  describe("statusDashboardBlocks", () => {
    it("creates header, status section, and context", () => {
      const { blocks, text } = statusDashboardBlocks("Sprint on track.");

      expect(text).toBe("Sprint on track.");
      expect(blocks).toHaveLength(3);
      expect(blocks[0]).toMatchObject({
        type: "header",
        text: { type: "plain_text" },
      });
      expect(blocks[1]).toMatchObject({
        type: "section",
        text: { type: "mrkdwn", text: "Sprint on track." },
      });
      expect(blocks[2]).toMatchObject({ type: "context" });
    });
  });

  // -------------------------------------------------------------------------
  // loadingBlocks
  // -------------------------------------------------------------------------

  describe("loadingBlocks", () => {
    it("uses default message when none provided", () => {
      const { text } = loadingBlocks();
      expect(text).toContain("Processing your request...");
    });

    it("uses custom message", () => {
      const { blocks, text } = loadingBlocks("Fetching data...");
      expect(text).toContain("Fetching data...");
      expect(blocks).toHaveLength(1);
    });
  });

  // -------------------------------------------------------------------------
  // noResponseBlocks
  // -------------------------------------------------------------------------

  describe("noResponseBlocks", () => {
    it("returns a no-response message", () => {
      const { blocks, text } = noResponseBlocks();
      expect(text).toBe("_No response from agent._");
      expect(blocks).toHaveLength(1);
    });
  });

  // -------------------------------------------------------------------------
  // schedulerStatusBlocks
  // -------------------------------------------------------------------------

  describe("schedulerStatusBlocks", () => {
    const baseJob: JobStatus = {
      id: "daily-standup",
      name: "Daily Standup",
      enabled: true,
      cron: "0 9 * * 1-5",
      running: false,
      lastRun: null,
      lastResult: null,
      consecutiveFailures: 0,
    };

    it("renders header and a section per job", () => {
      const jobs: JobStatus[] = [
        baseJob,
        { ...baseJob, id: "stale-tasks", name: "Stale Task Checker", enabled: false },
      ];
      const { blocks, text } = schedulerStatusBlocks(jobs);

      // Header + 2 job sections
      expect(blocks).toHaveLength(3);
      expect(blocks[0]).toMatchObject({
        type: "header",
        text: { type: "plain_text" },
      });
      expect(blocks[1]).toMatchObject({ type: "section" });
      expect(blocks[2]).toMatchObject({ type: "section" });

      // Fallback text includes job names
      expect(text).toContain("Daily Standup");
      expect(text).toContain("Stale Task Checker");
    });

    it("shows 'Never' when lastRun is null", () => {
      const { blocks } = schedulerStatusBlocks([baseJob]);
      const sectionText = (blocks[1] as any).text.text as string;
      expect(sectionText).toContain("Last run: Never");
    });

    it("shows relative time when lastRun is set", () => {
      const recentJob: JobStatus = {
        ...baseJob,
        lastRun: new Date(Date.now() - 120_000), // 2 minutes ago
      };
      const { blocks } = schedulerStatusBlocks([recentJob]);
      const sectionText = (blocks[1] as any).text.text as string;
      expect(sectionText).toContain("2m ago");
    });

    it("shows failure count when consecutiveFailures > 0", () => {
      const failingJob: JobStatus = {
        ...baseJob,
        consecutiveFailures: 3,
        lastResult: { success: false, posted: false, error: "timeout" },
        lastRun: new Date(),
      };
      const { blocks } = schedulerStatusBlocks([failingJob]);
      const sectionText = (blocks[1] as any).text.text as string;
      expect(sectionText).toContain("Consecutive failures: 3");
      expect(sectionText).toContain("Failed");
      expect(sectionText).toContain("timeout");
    });

    it("shows enabled/disabled status", () => {
      const disabledJob: JobStatus = { ...baseJob, enabled: false };
      const { blocks } = schedulerStatusBlocks([baseJob, disabledJob]);

      const enabledText = (blocks[1] as any).text.text as string;
      const disabledText = (blocks[2] as any).text.text as string;
      expect(enabledText).toContain("Enabled");
      expect(disabledText).toContain("Disabled");
    });
  });
});
