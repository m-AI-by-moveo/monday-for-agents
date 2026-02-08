import type { App } from "@slack/bolt";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
} from "../services/a2a-client.js";
import {
  agentListBlocks,
  statusDashboardBlocks,
  loadingBlocks,
  errorBlocks,
  warningBlocks,
} from "../ui/block-builder.js";

const a2a = createA2AClient();

// ---------------------------------------------------------------------------
// /status — query Scrum Master for board status
// ---------------------------------------------------------------------------

async function fetchBoardStatus(): Promise<{ blocks: any[]; text: string }> {
  const agentUrl = AGENT_URLS["scrum-master"];
  if (!agentUrl) {
    return errorBlocks("Scrum Master agent is not configured.");
  }

  try {
    const response = await a2a.sendMessage(
      agentUrl,
      "Give me the current board status summary.",
    );

    if (response.error) {
      return errorBlocks(`Agent error: ${response.error.message}`);
    }

    if (response.result) {
      const statusText = extractTextFromTask(response.result);
      return statusDashboardBlocks(statusText);
    }
    return { blocks: [], text: "_No status available from agent._" };
  } catch (err) {
    console.error("[commands] /status failed:", err);
    return warningBlocks("Could not reach the Scrum Master agent.");
  }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

export function registerCommands(app: App): void {
  app.command("/agents", async ({ ack, respond }) => {
    await ack();
    console.log("[commands] /agents invoked");
    const { blocks, text } = agentListBlocks(AGENT_URLS);
    await respond({ response_type: "ephemeral", blocks, text });
  });

  app.command("/status", async ({ ack, respond }) => {
    await ack();
    console.log("[commands] /status invoked");

    const loading = loadingBlocks("Fetching board status from Scrum Master...");
    await respond({
      response_type: "ephemeral",
      blocks: loading.blocks,
      text: loading.text,
    });

    const result = await fetchBoardStatus();
    await respond({
      response_type: "in_channel",
      blocks: result.blocks,
      text: result.text,
    });
  });
}
