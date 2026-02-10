import Anthropic from "@anthropic-ai/sdk";
import type { MondayBoard } from "./monday-client.js";

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
  suggestedBoardId?: string;
}

const BASE_SYSTEM_PROMPT = `You are a meeting transcript analyzer. Your job is to extract structured information from meeting transcripts.

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

const BOARD_SUGGESTION_ADDENDUM = `

Additionally, a list of available Monday.com boards will be provided. Based on the meeting content (client name, project name, topic), suggest the most relevant board by including a "suggestedBoardId" field in your JSON response with the board's ID. If no board seems relevant, omit the field.`;

export class MeetingNotesAgent {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic();
  }

  async analyzeMeetingTranscript(
    transcript: string,
    meetingTitle: string,
    boardList?: MondayBoard[],
  ): Promise<MeetingAnalysis> {
    const trimmed = transcript.trim();
    if (!trimmed || trimmed.length < 20) {
      return { summary: "Empty or too-short transcript.", actionItems: [], decisions: [] };
    }

    const systemPrompt = boardList && boardList.length > 0
      ? BASE_SYSTEM_PROMPT + BOARD_SUGGESTION_ADDENDUM
      : BASE_SYSTEM_PROMPT;

    let userContent = `Meeting title: "${meetingTitle}"\n\nTranscript:\n${trimmed}`;
    if (boardList && boardList.length > 0) {
      const boardLines = boardList.map((b) => `- ${b.id}: ${b.name}`).join("\n");
      userContent += `\n\nAvailable Monday.com boards:\n${boardLines}`;
    }

    const response = await this.client.messages.create({
      model: "claude-sonnet-4-5-20250929",
      max_tokens: 2048,
      system: systemPrompt,
      messages: [
        {
          role: "user",
          content: userContent,
        },
      ],
    });

    const textBlock = response.content.find((b) => b.type === "text");
    if (!textBlock || textBlock.type !== "text") {
      return { summary: "Failed to analyze transcript.", actionItems: [], decisions: [] };
    }

    try {
      // Strip markdown code fences if present (```json ... ```)
      let jsonText = textBlock.text.trim();
      if (jsonText.startsWith("```")) {
        jsonText = jsonText.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "");
      }

      const parsed = JSON.parse(jsonText);
      const result: MeetingAnalysis = {
        summary: parsed.summary ?? "",
        actionItems: Array.isArray(parsed.actionItems) ? parsed.actionItems : [],
        decisions: Array.isArray(parsed.decisions) ? parsed.decisions : [],
      };
      if (parsed.suggestedBoardId) {
        result.suggestedBoardId = String(parsed.suggestedBoardId);
      }
      return result;
    } catch {
      // Return raw text as summary if JSON parsing fails
      return {
        summary: textBlock.text.substring(0, 500),
        actionItems: [],
        decisions: [],
      };
    }
  }
}
