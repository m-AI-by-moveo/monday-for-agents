import Anthropic from "@anthropic-ai/sdk";

export interface ActionItem {
  title: string;
  description: string;
  assignee?: string;
  priority?: "high" | "medium" | "low";
  deadline?: string;
}

export interface MeetingAnalysis {
  summary: string;
  actionItems: ActionItem[];
  decisions: string[];
}

const SYSTEM_PROMPT = `You are a meeting transcript analyzer. Your job is to extract structured information from meeting transcripts.

Given a meeting transcript, produce a JSON object with the following schema:
{
  "summary": "2-3 sentence summary of the meeting",
  "actionItems": [
    {
      "title": "Short task title",
      "description": "What needs to be done",
      "assignee": "Person responsible (if mentioned)",
      "priority": "high" | "medium" | "low",
      "deadline": "Any mentioned deadline (if any)"
    }
  ],
  "decisions": ["Key decision 1", "Key decision 2"]
}

Rules:
- Only include action items that are clearly stated or strongly implied.
- If no action items are found, return an empty actionItems array.
- If no decisions were made, return an empty decisions array.
- assignee, priority, and deadline are optional — omit them if not mentioned.
- Default priority to "medium" if importance is unclear.
- Keep the summary concise: 2-3 sentences max.
- Respond ONLY with the JSON object, no other text.`;

export class MeetingNotesAgent {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic();
  }

  async analyzeMeetingTranscript(
    transcript: string,
    meetingTitle: string,
  ): Promise<MeetingAnalysis> {
    const trimmed = transcript.trim();
    if (!trimmed || trimmed.length < 20) {
      return { summary: "Empty or too-short transcript.", actionItems: [], decisions: [] };
    }

    const response = await this.client.messages.create({
      model: "claude-sonnet-4-5-20250929",
      max_tokens: 2048,
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content: `Meeting title: "${meetingTitle}"\n\nTranscript:\n${trimmed}`,
        },
      ],
    });

    const textBlock = response.content.find((b) => b.type === "text");
    if (!textBlock || textBlock.type !== "text") {
      return { summary: "Failed to analyze transcript.", actionItems: [], decisions: [] };
    }

    try {
      const parsed = JSON.parse(textBlock.text);
      return {
        summary: parsed.summary ?? "",
        actionItems: Array.isArray(parsed.actionItems) ? parsed.actionItems : [],
        decisions: Array.isArray(parsed.decisions) ? parsed.decisions : [],
      };
    } catch {
      return { summary: "Failed to parse analysis.", actionItems: [], decisions: [] };
    }
  }
}
