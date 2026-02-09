import { describe, it, expect } from "vitest";
import {
  standupBlocks,
  staleTaskBlocks,
  weeklySummaryBlocks,
} from "../src/scheduler/blocks/scheduler-blocks.js";

describe("scheduler-blocks", () => {
  describe("standupBlocks", () => {
    it("creates header, section, and context blocks", () => {
      const { blocks, text } = standupBlocks("Here is today's standup.");

      expect(text).toBe("Here is today's standup.");
      expect(blocks).toHaveLength(3);
      expect(blocks[0]).toMatchObject({
        type: "header",
        text: { type: "plain_text" },
      });
      expect((blocks[0] as any).text.text).toContain("Daily Standup");
      expect(blocks[1]).toMatchObject({
        type: "section",
        text: { type: "mrkdwn", text: "Here is today's standup." },
      });
      expect(blocks[2]).toMatchObject({ type: "context" });
    });
  });

  describe("staleTaskBlocks", () => {
    it("creates header with warning, section, and context blocks", () => {
      const { blocks, text } = staleTaskBlocks("Task X has been stuck.");

      expect(text).toBe("Task X has been stuck.");
      expect(blocks).toHaveLength(3);
      expect((blocks[0] as any).text.text).toContain("Stale Tasks");
      expect(blocks[1]).toMatchObject({
        type: "section",
        text: { type: "mrkdwn", text: "Task X has been stuck." },
      });
    });
  });

  describe("weeklySummaryBlocks", () => {
    it("creates header with calendar, section, and context blocks", () => {
      const { blocks, text } = weeklySummaryBlocks("Weekly recap here.");

      expect(text).toBe("Weekly recap here.");
      expect(blocks).toHaveLength(3);
      expect((blocks[0] as any).text.text).toContain("Weekly Summary");
      expect(blocks[1]).toMatchObject({
        type: "section",
        text: { type: "mrkdwn", text: "Weekly recap here." },
      });
    });
  });
});
