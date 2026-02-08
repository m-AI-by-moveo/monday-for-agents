import { describe, it, expect } from "vitest";
import {
  agentResponseBlocks,
  errorBlocks,
  warningBlocks,
  agentListBlocks,
  statusDashboardBlocks,
  loadingBlocks,
  noResponseBlocks,
} from "../src/ui/block-builder.js";

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
});
