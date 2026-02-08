import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import nock from "nock";

// ---------------------------------------------------------------------------
// We need to test AGENT_URLS with env-var overrides. Because the module
// evaluates `process.env.*` at import time, we use dynamic imports with
// vi.resetModules() to re-evaluate the module with different env values.
// ---------------------------------------------------------------------------

describe("a2a-client", () => {
  // -------------------------------------------------------------------------
  // AGENT_URLS
  // -------------------------------------------------------------------------

  describe("AGENT_URLS", () => {
    beforeEach(() => {
      vi.resetModules();
    });

    afterEach(() => {
      // Clean up any env overrides
      delete process.env.PO_AGENT_PORT;
      delete process.env.DEV_AGENT_PORT;
      delete process.env.REVIEWER_AGENT_PORT;
      delete process.env.SM_AGENT_PORT;
    });

    it("has all 4 agents with correct default ports", async () => {
      const { AGENT_URLS } = await import("../src/services/a2a-client.js");

      expect(Object.keys(AGENT_URLS)).toHaveLength(4);
      expect(AGENT_URLS["product-owner"]).toBe("http://localhost:10001");
      expect(AGENT_URLS["developer"]).toBe("http://localhost:10002");
      expect(AGENT_URLS["reviewer"]).toBe("http://localhost:10003");
      expect(AGENT_URLS["scrum-master"]).toBe("http://localhost:10004");
    });

    it("respects env var overrides for agent ports", async () => {
      process.env.PO_AGENT_PORT = "20001";
      process.env.DEV_AGENT_PORT = "20002";
      process.env.REVIEWER_AGENT_PORT = "20003";
      process.env.SM_AGENT_PORT = "20004";

      const { AGENT_URLS } = await import("../src/services/a2a-client.js");

      expect(AGENT_URLS["product-owner"]).toBe("http://localhost:20001");
      expect(AGENT_URLS["developer"]).toBe("http://localhost:20002");
      expect(AGENT_URLS["reviewer"]).toBe("http://localhost:20003");
      expect(AGENT_URLS["scrum-master"]).toBe("http://localhost:20004");
    });
  });

  // -------------------------------------------------------------------------
  // createA2AClient — sendMessage / getTask
  // -------------------------------------------------------------------------

  describe("createA2AClient", () => {
    let createA2AClient: typeof import("../src/services/a2a-client.js")["createA2AClient"];

    beforeEach(async () => {
      vi.resetModules();
      const mod = await import("../src/services/a2a-client.js");
      createA2AClient = mod.createA2AClient;
      nock.cleanAll();
    });

    afterEach(() => {
      nock.cleanAll();
      nock.enableNetConnect();
    });

    // -- sendMessage --------------------------------------------------------

    describe("sendMessage()", () => {
      it("sends correct JSON-RPC payload without contextId", async () => {
        const client = createA2AClient();

        const scope = nock("http://localhost:10001")
          .post("/", (body: Record<string, unknown>) => {
            expect(body.jsonrpc).toBe("2.0");
            expect(body.method).toBe("message/send");
            expect(body.id).toBeDefined();

            const params = body.params as Record<string, unknown>;
            expect(params.message).toEqual({
              role: "user",
              parts: [{ type: "text", text: "hello agent" }],
            });
            // No configuration when contextId is omitted
            expect(params.configuration).toBeUndefined();
            return true;
          })
          .reply(200, {
            jsonrpc: "2.0",
            id: "test-id",
            result: {
              id: "task-1",
              contextId: "ctx-1",
              status: { state: "completed", message: { role: "agent", parts: [{ type: "text", text: "hi" }] } },
            },
          });

        const response = await client.sendMessage(
          "http://localhost:10001",
          "hello agent",
        );

        expect(response.jsonrpc).toBe("2.0");
        expect(response.result?.status.state).toBe("completed");
        expect(scope.isDone()).toBe(true);
      });

      it("includes configuration with contextId when provided", async () => {
        const client = createA2AClient();

        const scope = nock("http://localhost:10001")
          .post("/", (body: Record<string, unknown>) => {
            const params = body.params as Record<string, unknown>;
            expect(params.configuration).toEqual({ context_id: "my-ctx-123" });
            return true;
          })
          .reply(200, {
            jsonrpc: "2.0",
            id: "test-id",
            result: {
              id: "task-2",
              contextId: "my-ctx-123",
              status: { state: "completed" },
            },
          });

        await client.sendMessage(
          "http://localhost:10001",
          "hello",
          "my-ctx-123",
        );

        expect(scope.isDone()).toBe(true);
      });

      it("omits configuration when no contextId is provided", async () => {
        const client = createA2AClient();

        const scope = nock("http://localhost:10001")
          .post("/", (body: Record<string, unknown>) => {
            const params = body.params as Record<string, unknown>;
            expect(params).not.toHaveProperty("configuration");
            return true;
          })
          .reply(200, { jsonrpc: "2.0", id: "1", result: null });

        await client.sendMessage("http://localhost:10001", "hi");
        expect(scope.isDone()).toBe(true);
      });

      it("handles HTTP errors gracefully and returns error response", async () => {
        const client = createA2AClient();

        nock("http://localhost:10001")
          .post("/")
          .replyWithError("Connection refused");

        const response = await client.sendMessage(
          "http://localhost:10001",
          "hello",
        );

        expect(response.jsonrpc).toBe("2.0");
        expect(response.error).toBeDefined();
        expect(response.error!.code).toBe(-32000);
        expect(response.error!.message).toContain("HTTP error");
        expect(response.result).toBeUndefined();
      });

      it("handles timeout", async () => {
        const client = createA2AClient();

        nock("http://localhost:10001")
          .post("/")
          .delay(130_000) // exceeds the 120s timeout
          .reply(200, { jsonrpc: "2.0", id: "1" });

        // Use a shorter-lived approach: axios will throw ECONNABORTED on timeout.
        // Since we can't really wait 120s, we'll simulate via nock's delay + abort.
        // nock with delay > axios timeout triggers a timeout error.
        // For a practical test we can replyWithError to simulate timeout.
        nock.cleanAll();
        nock("http://localhost:10001")
          .post("/")
          .replyWithError({ message: "timeout of 120000ms exceeded", code: "ECONNABORTED" });

        const response = await client.sendMessage(
          "http://localhost:10001",
          "hello",
        );

        expect(response.error).toBeDefined();
        expect(response.error!.code).toBe(-32000);
        expect(response.error!.message).toContain("timeout");
      });
    });

    // -- getTask ------------------------------------------------------------

    describe("getTask()", () => {
      it("sends correct JSON-RPC payload", async () => {
        const client = createA2AClient();

        const scope = nock("http://localhost:10002")
          .post("/", (body: Record<string, unknown>) => {
            expect(body.jsonrpc).toBe("2.0");
            expect(body.method).toBe("task/get");
            expect(body.id).toBeDefined();

            const params = body.params as Record<string, unknown>;
            expect(params.id).toBe("task-42");
            return true;
          })
          .reply(200, {
            jsonrpc: "2.0",
            id: "rpc-id",
            result: {
              id: "task-42",
              contextId: "ctx-99",
              status: { state: "completed" },
            },
          });

        const response = await client.getTask(
          "http://localhost:10002",
          "task-42",
        );

        expect(response.jsonrpc).toBe("2.0");
        expect(response.result?.id).toBe("task-42");
        expect(scope.isDone()).toBe(true);
      });
    });
  });

  // -------------------------------------------------------------------------
  // extractTextFromTask
  // -------------------------------------------------------------------------

  describe("extractTextFromTask()", () => {
    let extractTextFromTask: typeof import("../src/services/a2a-client.js")["extractTextFromTask"];

    beforeEach(async () => {
      vi.resetModules();
      const mod = await import("../src/services/a2a-client.js");
      extractTextFromTask = mod.extractTextFromTask;
    });

    it("extracts text from a completed task with a text part", () => {
      const result = extractTextFromTask({
        id: "task-1",
        contextId: "ctx-1",
        status: {
          state: "completed",
          message: {
            role: "agent",
            parts: [{ type: "text", text: "Here is the result." }],
          },
        },
      });

      expect(result).toBe("Here is the result.");
    });

    it("returns fallback for tasks without a text part in the message", () => {
      const result = extractTextFromTask({
        id: "task-7",
        contextId: "ctx-1",
        status: {
          state: "completed",
          message: {
            role: "agent",
            parts: [] as any,
          },
        },
      });

      expect(result).toBe("[Agent task task-7 is completed]");
    });

    it("returns fallback when status has no message", () => {
      const result = extractTextFromTask({
        id: "task-9",
        contextId: "ctx-1",
        status: {
          state: "working",
        },
      });

      expect(result).toBe("[Agent task task-9 is working]");
    });

    it("handles input-required state", () => {
      const result = extractTextFromTask({
        id: "task-5",
        contextId: "ctx-1",
        status: {
          state: "input-required",
          message: {
            role: "agent",
            parts: [{ type: "text", text: "I need more info." }],
          },
        },
      });

      expect(result).toBe("I need more info.");
    });

    it("returns fallback for input-required without message text", () => {
      const result = extractTextFromTask({
        id: "task-6",
        contextId: "ctx-1",
        status: {
          state: "input-required",
        },
      });

      expect(result).toBe("[Agent task task-6 is input-required]");
    });
  });
});
