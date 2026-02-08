import type { App } from "@slack/bolt";
import {
  createA2AClient,
  extractTextFromTask,
  AGENT_URLS,
} from "../services/a2a-client.js";

const a2a = createA2AClient();

// ---------------------------------------------------------------------------
// /agents — list registered agents
// ---------------------------------------------------------------------------

function buildAgentList(): string {
  const lines = Object.entries(AGENT_URLS).map(
    ([name, url]) => `*${name}*  \u2192  \`${url}\``,
  );
  return [":robot_face: *Registered Agents*", "", ...lines].join("\n");
}

// ---------------------------------------------------------------------------
// /status — query Scrum Master for board status
// ---------------------------------------------------------------------------

async function fetchBoardStatus(): Promise<string> {
  const agentUrl = AGENT_URLS["scrum-master"];
  if (!agentUrl) return "Scrum Master agent is not configured.";

  try {
    const response = await a2a.sendMessage(
      agentUrl,
      "Give me the current board status summary.",
    );

    if (response.error) {
      return `:x: Agent error: ${response.error.message}`;
    }

    return response.result
      ? extractTextFromTask(response.result)
      : "_No status available from agent._";
  } catch (err) {
    console.error("[commands] /status failed:", err);
    return ":warning: Could not reach the Scrum Master agent.";
  }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

export function registerCommands(app: App): void {
  app.command("/agents", async ({ ack, respond }) => {
    await ack();
    console.log("[commands] /agents invoked");
    await respond({ response_type: "ephemeral", text: buildAgentList() });
  });

  app.command("/status", async ({ ack, respond }) => {
    await ack();
    console.log("[commands] /status invoked");
    await respond({
      response_type: "ephemeral",
      text: ":hourglass_flowing_sand: Fetching board status from Scrum Master...",
    });

    const statusText = await fetchBoardStatus();
    await respond({ response_type: "in_channel", text: statusText });
  });
}
