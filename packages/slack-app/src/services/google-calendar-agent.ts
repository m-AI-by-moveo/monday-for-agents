import Anthropic from "@anthropic-ai/sdk";
import type { GoogleCalendarService } from "./google-calendar.js";
import type { CalendarEvent } from "../ui/google-blocks.js";

const CALENDAR_TOOLS: Anthropic.Tool[] = [
  {
    name: "list_events",
    description:
      "List calendar events for a time range. Use this to check what meetings are scheduled, find upcoming events, or see today's/this week's agenda.",
    input_schema: {
      type: "object" as const,
      properties: {
        time_min: {
          type: "string",
          description: "Start of time range in ISO 8601 format (e.g. 2026-02-10T00:00:00+02:00)",
        },
        time_max: {
          type: "string",
          description: "End of time range in ISO 8601 format (e.g. 2026-02-10T23:59:59+02:00)",
        },
        max_results: {
          type: "number",
          description: "Maximum number of events to return (default 25)",
        },
      },
      required: ["time_min", "time_max"],
    },
  },
  {
    name: "create_event",
    description:
      "Create a new calendar event / meeting / appointment. Use this to book, schedule, or set up events.",
    input_schema: {
      type: "object" as const,
      properties: {
        summary: {
          type: "string",
          description: "Event title / name",
        },
        start: {
          type: "string",
          description: "Start time in ISO 8601 format with timezone (e.g. 2026-02-10T14:00:00+02:00)",
        },
        end: {
          type: "string",
          description: "End time in ISO 8601 format with timezone (e.g. 2026-02-10T15:00:00+02:00)",
        },
        description: {
          type: "string",
          description: "Optional event description",
        },
        location: {
          type: "string",
          description: "Optional event location",
        },
      },
      required: ["summary", "start", "end"],
    },
  },
  {
    name: "update_event",
    description: "Update an existing calendar event. You need the event ID from list_events.",
    input_schema: {
      type: "object" as const,
      properties: {
        event_id: { type: "string", description: "The event ID to update" },
        summary: { type: "string", description: "New event title" },
        start: { type: "string", description: "New start time in ISO 8601" },
        end: { type: "string", description: "New end time in ISO 8601" },
        description: { type: "string", description: "New description" },
        location: { type: "string", description: "New location" },
      },
      required: ["event_id"],
    },
  },
  {
    name: "delete_event",
    description: "Delete / cancel a calendar event. You need the event ID from list_events.",
    input_schema: {
      type: "object" as const,
      properties: {
        event_id: { type: "string", description: "The event ID to delete" },
      },
      required: ["event_id"],
    },
  },
];

export class GoogleCalendarAgent {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic();
  }

  async handleRequest(
    userMessage: string,
    calendarService: GoogleCalendarService,
    userId: string,
  ): Promise<string> {
    const now = new Date();
    const tzOffset = "+02:00"; // Israel timezone offset
    const systemPrompt = `You are a Google Calendar assistant integrated into Slack. Help the user manage their calendar.

Current date/time: ${now.toISOString()} (user timezone: Asia/Jerusalem, offset: ${tzOffset})

Instructions:
- Use the provided tools to interact with the user's Google Calendar.
- When the user says "tomorrow", "next Monday", "in 2 hours", etc., calculate the correct ISO 8601 datetime with the timezone offset ${tzOffset}.
- For "book a meeting" without a title, use a sensible default like "Meeting".
- For finding free slots, list events in the requested range and identify gaps.
- When creating events, if no end time is specified, default to 1 hour duration.
- Keep responses concise — this is Slack, not email.
- Format times in a human-readable way in your response (e.g. "Tomorrow 1:00 PM - 2:00 PM").
- Use Slack mrkdwn formatting (*bold*, _italic_, \`code\`).
- NEVER use ** for bold — Slack uses single * for bold.`;

    const messages: Anthropic.MessageParam[] = [
      { role: "user", content: userMessage },
    ];

    // Agentic loop — keep calling tools until Claude gives a final text response
    let iterations = 0;
    const maxIterations = 5;

    while (iterations < maxIterations) {
      iterations++;

      const response = await this.client.messages.create({
        model: "claude-sonnet-4-5-20250929",
        max_tokens: 1024,
        system: systemPrompt,
        tools: CALENDAR_TOOLS,
        messages,
      });

      // Collect text and tool_use blocks
      const textParts: string[] = [];
      const toolUseBlocks: Anthropic.ToolUseBlock[] = [];

      for (const block of response.content) {
        if (block.type === "text") {
          textParts.push(block.text);
        } else if (block.type === "tool_use") {
          toolUseBlocks.push(block);
        }
      }

      // If no tool calls, return the final text
      if (toolUseBlocks.length === 0) {
        return textParts.join("\n") || "Done.";
      }

      // Execute tool calls and build tool_result messages
      messages.push({ role: "assistant", content: response.content });

      const toolResults: Anthropic.ToolResultBlockParam[] = [];

      for (const toolUse of toolUseBlocks) {
        const result = await this.executeTool(
          toolUse.name,
          toolUse.input as Record<string, any>,
          calendarService,
          userId,
        );
        toolResults.push({
          type: "tool_result",
          tool_use_id: toolUse.id,
          content: JSON.stringify(result),
        });
      }

      messages.push({ role: "user", content: toolResults });

      // If stop_reason is "end_turn" with tool calls, continue the loop
      // to let Claude process the results
    }

    return "I hit the maximum number of steps. Please try a simpler request.";
  }

  private async executeTool(
    name: string,
    input: Record<string, any>,
    calendarService: GoogleCalendarService,
    userId: string,
  ): Promise<any> {
    try {
      switch (name) {
        case "list_events": {
          const authClient = await calendarService["auth"].getClient(userId);
          const { google } = await import("googleapis");
          const calendar = google.calendar({ version: "v3", auth: authClient });

          const res = await calendar.events.list({
            calendarId: "primary",
            timeMin: input.time_min,
            timeMax: input.time_max,
            maxResults: input.max_results ?? 25,
            singleEvents: true,
            orderBy: "startTime",
          });

          return (res.data.items ?? []).map((e) => ({
            id: e.id,
            summary: e.summary ?? "(no title)",
            start: e.start?.dateTime ?? e.start?.date ?? "",
            end: e.end?.dateTime ?? e.end?.date ?? "",
            location: e.location,
            htmlLink: e.htmlLink,
          }));
        }
        case "create_event": {
          return await calendarService.createEvent(userId, {
            summary: input.summary,
            start: input.start,
            end: input.end,
            description: input.description,
            location: input.location,
          });
        }
        case "update_event": {
          const update: Record<string, string> = {};
          if (input.summary) update.summary = input.summary;
          if (input.start) update.start = input.start;
          if (input.end) update.end = input.end;
          if (input.description) update.description = input.description;
          if (input.location) update.location = input.location;
          return await calendarService.updateEvent(userId, input.event_id, update);
        }
        case "delete_event": {
          await calendarService.deleteEvent(userId, input.event_id);
          return { status: "deleted", event_id: input.event_id };
        }
        default:
          return { error: `Unknown tool: ${name}` };
      }
    } catch (err: any) {
      return { error: err.message ?? String(err) };
    }
  }
}
