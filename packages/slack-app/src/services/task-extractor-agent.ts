import Anthropic from "@anthropic-ai/sdk";

export interface ExtractedTask {
  taskName: string;
  description: string;
  assignee: string;
  priority: "Low" | "Medium" | "High" | "Critical";
  status: "To Do" | "Working on it" | "In Progress" | "Done";
}

const SYSTEM_PROMPT = `You are a task extraction assistant. Given a series of Slack messages from a conversation, identify the most relevant task being discussed and extract structured information.

Produce a JSON object with the following schema:
{
  "taskName": "Short, actionable task title",
  "description": "Detailed description of what needs to be done",
  "assignee": "Person responsible (empty string if not identifiable)",
  "priority": "Low" | "Medium" | "High" | "Critical",
  "status": "To Do" | "Working on it" | "In Progress" | "Done"
}

Rules:
- taskName should be concise and actionable (imperative form, e.g. "Fix login bug").
- description should capture relevant context from the conversation.
- assignee should be the display name of the person responsible. Use empty string if unclear.
- Default priority to "Medium" if not evident from the conversation.
- Default status to "To Do" unless the conversation indicates work has started.
- Respond ONLY with the JSON object, no other text.`;

const DEFAULTS: ExtractedTask = {
  taskName: "",
  description: "",
  assignee: "",
  priority: "Medium",
  status: "To Do",
};

export class TaskExtractorAgent {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic();
  }

  async extractTaskFromMessages(
    messages: { user: string; text: string }[],
  ): Promise<ExtractedTask> {
    if (!messages.length) {
      return { ...DEFAULTS };
    }

    const transcript = messages
      .map((m) => `${m.user}: ${m.text}`)
      .join("\n");

    const response = await this.client.messages.create({
      model: "claude-sonnet-4-5-20250929",
      max_tokens: 1024,
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content: `Slack conversation:\n\n${transcript}`,
        },
      ],
    });

    const textBlock = response.content.find((b) => b.type === "text");
    if (!textBlock || textBlock.type !== "text") {
      return { ...DEFAULTS };
    }

    try {
      // Strip markdown code fences if present (```json ... ```)
      let jsonText = textBlock.text.trim();
      if (jsonText.startsWith("```")) {
        jsonText = jsonText.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "");
      }

      const parsed = JSON.parse(jsonText);
      return {
        taskName: parsed.taskName ?? "",
        description: parsed.description ?? "",
        assignee: parsed.assignee ?? "",
        priority: ["Low", "Medium", "High", "Critical"].includes(parsed.priority)
          ? parsed.priority
          : "Medium",
        status: ["To Do", "Working on it", "In Progress", "Done"].includes(parsed.status)
          ? parsed.status
          : "To Do",
      };
    } catch {
      return { ...DEFAULTS };
    }
  }
}
