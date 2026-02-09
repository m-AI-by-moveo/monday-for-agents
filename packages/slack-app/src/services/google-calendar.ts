import { google } from "googleapis";
import type { GoogleAuthService } from "./google-auth.js";
import type { CalendarEvent } from "../ui/google-blocks.js";

export interface ListEventsOptions {
  timeRange?: "today" | "week";
  maxResults?: number;
  calendarId?: string;
}

export interface CreateEventInput {
  summary: string;
  start: string;
  end: string;
  description?: string;
  location?: string;
}

export class GoogleCalendarService {
  constructor(private auth: GoogleAuthService) {}

  async listEvents(userId: string, opts?: ListEventsOptions): Promise<CalendarEvent[]> {
    const authClient = await this.auth.getClient(userId);
    const calendar = google.calendar({ version: "v3", auth: authClient });

    const now = new Date();
    let timeMin = now.toISOString();
    let timeMax: string | undefined;

    if (opts?.timeRange === "today") {
      const endOfDay = new Date(now);
      endOfDay.setHours(23, 59, 59, 999);
      timeMax = endOfDay.toISOString();
    } else if (opts?.timeRange === "week") {
      const endOfWeek = new Date(now);
      endOfWeek.setDate(endOfWeek.getDate() + 7);
      timeMax = endOfWeek.toISOString();
    }

    const res = await calendar.events.list({
      calendarId: opts?.calendarId ?? "primary",
      timeMin,
      timeMax,
      maxResults: opts?.maxResults ?? 25,
      singleEvents: true,
      orderBy: "startTime",
    });

    return (res.data.items ?? []).map((e) => ({
      id: e.id ?? "",
      summary: e.summary ?? "(no title)",
      start: e.start?.dateTime ?? e.start?.date ?? "",
      end: e.end?.dateTime ?? e.end?.date ?? "",
      location: e.location ?? undefined,
      htmlLink: e.htmlLink ?? undefined,
    }));
  }

  async createEvent(userId: string, input: CreateEventInput): Promise<CalendarEvent> {
    const authClient = await this.auth.getClient(userId);
    const calendar = google.calendar({ version: "v3", auth: authClient });

    const res = await calendar.events.insert({
      calendarId: "primary",
      requestBody: {
        summary: input.summary,
        description: input.description,
        location: input.location,
        start: { dateTime: input.start },
        end: { dateTime: input.end },
      },
    });

    return {
      id: res.data.id ?? "",
      summary: res.data.summary ?? "",
      start: res.data.start?.dateTime ?? res.data.start?.date ?? "",
      end: res.data.end?.dateTime ?? res.data.end?.date ?? "",
      location: res.data.location ?? undefined,
      htmlLink: res.data.htmlLink ?? undefined,
    };
  }

  async updateEvent(
    userId: string,
    eventId: string,
    update: Record<string, string>,
  ): Promise<CalendarEvent> {
    const authClient = await this.auth.getClient(userId);
    const calendar = google.calendar({ version: "v3", auth: authClient });

    const existing = await calendar.events.get({
      calendarId: "primary",
      eventId,
    });

    const requestBody: Record<string, any> = { ...existing.data };
    for (const [key, value] of Object.entries(update)) {
      if (key === "start") {
        requestBody.start = { dateTime: value };
      } else if (key === "end") {
        requestBody.end = { dateTime: value };
      } else {
        requestBody[key] = value;
      }
    }

    const res = await calendar.events.update({
      calendarId: "primary",
      eventId,
      requestBody,
    });

    return {
      id: res.data.id ?? "",
      summary: res.data.summary ?? "",
      start: res.data.start?.dateTime ?? res.data.start?.date ?? "",
      end: res.data.end?.dateTime ?? res.data.end?.date ?? "",
      location: res.data.location ?? undefined,
      htmlLink: res.data.htmlLink ?? undefined,
    };
  }

  async deleteEvent(userId: string, eventId: string): Promise<void> {
    const authClient = await this.auth.getClient(userId);
    const calendar = google.calendar({ version: "v3", auth: authClient });

    await calendar.events.delete({
      calendarId: "primary",
      eventId,
    });
  }
}
