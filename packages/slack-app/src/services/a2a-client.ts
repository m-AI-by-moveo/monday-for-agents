import axios, { AxiosError } from "axios";
import { v4 as uuidv4 } from "uuid";

const MFA_API_KEY = process.env.MFA_API_KEY || "";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface A2APart {
  type?: "text";
  kind?: "text";
  text: string;
}

export interface A2AMessage {
  role: "user" | "agent";
  parts: A2APart[];
}

export interface A2ATaskStatus {
  state: "submitted" | "working" | "input-required" | "completed" | "failed" | "canceled";
  message?: A2AMessage;
}

export interface A2ATask {
  id: string;
  contextId: string;
  status: A2ATaskStatus;
  history?: A2AMessage[];
}

export interface A2AResponse {
  jsonrpc: "2.0";
  id: string | number;
  result?: A2ATask;
  error?: { code: number; message: string; data?: unknown };
}

export type A2ATaskResponse = A2AResponse;

// ---------------------------------------------------------------------------
// Agent URL registry
// ---------------------------------------------------------------------------

export const AGENT_URLS: Record<string, string> = {
  "product-owner": `http://localhost:${process.env.PO_AGENT_PORT || 10001}`,
  "developer": `http://localhost:${process.env.DEV_AGENT_PORT || 10002}`,
  "reviewer": `http://localhost:${process.env.REVIEWER_AGENT_PORT || 10003}`,
  "scrum-master": `http://localhost:${process.env.SM_AGENT_PORT || 10004}`,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildJsonRpcRequest(method: string, params: Record<string, unknown>) {
  return {
    jsonrpc: "2.0" as const,
    id: uuidv4(),
    method,
    params,
  };
}

/**
 * Extract the first text part from an A2A agent message, falling back to a
 * human-readable description when no text part is found.
 */
export function extractTextFromTask(task: A2ATask): string {
  const msg = task.status?.message;
  if (msg) {
    // SDK v0.3+ uses "kind" instead of "type" for part discriminator
    const textPart = msg.parts.find(
      (p: any) => p.type === "text" || p.kind === "text",
    );
    if (textPart) return textPart.text;
  }
  return `[Agent task ${task.id} is ${task.status.state}]`;
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export interface A2AClient {
  sendMessage(
    agentUrl: string,
    message: string,
    contextId?: string,
  ): Promise<A2AResponse>;
  getTask(agentUrl: string, taskId: string): Promise<A2ATaskResponse>;
}

export function createA2AClient(): A2AClient {
  async function rpc(agentUrl: string, method: string, params: Record<string, unknown>): Promise<A2AResponse> {
    const body = buildJsonRpcRequest(method, params);
    console.log(`[a2a-client] POST ${agentUrl} method=${method}`);

    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Correlation-ID": uuidv4(),
      };
      if (MFA_API_KEY) {
        headers["X-API-Key"] = MFA_API_KEY;
      }
      const res = await axios.post<A2AResponse>(agentUrl, body, {
        headers,
        timeout: 120_000, // 2 min – agents may take a while
      });
      const data = res.data;

      if (data.error) {
        console.error(`[a2a-client] JSON-RPC error from ${agentUrl}:`, data.error);
      }
      return data;
    } catch (err) {
      const axErr = err as AxiosError;
      console.error(
        `[a2a-client] HTTP error calling ${agentUrl}:`,
        axErr.message,
      );
      return {
        jsonrpc: "2.0",
        id: body.id,
        error: {
          code: -32000,
          message: `HTTP error: ${axErr.message}`,
        },
      };
    }
  }

  return {
    async sendMessage(agentUrl, message, contextId) {
      const params: Record<string, unknown> = {
        message: {
          role: "user",
          parts: [{ type: "text", text: message }],
          messageId: uuidv4(),
        },
      };
      if (contextId) {
        params.configuration = { context_id: contextId };
      }
      return rpc(agentUrl, "message/send", params);
    },

    async getTask(agentUrl, taskId) {
      return rpc(agentUrl, "task/get", { id: taskId });
    },
  };
}
