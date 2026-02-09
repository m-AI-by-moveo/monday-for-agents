import type { KnownBlock, Block } from "@slack/types";

type BlockResult = { blocks: (KnownBlock | Block)[]; text: string };

export function googleConnectBlocks(authUrl: string): BlockResult {
  const text = "Connect your Google account to use Calendar and Drive features.";
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text: `:link: ${text}` },
      accessory: {
        type: "button",
        text: { type: "plain_text", text: "Connect Google", emoji: true },
        url: authUrl,
        action_id: "google_connect",
        style: "primary",
      },
    },
  ];
  return { blocks, text };
}

export function googleStatusBlocks(connected: boolean, email?: string): BlockResult {
  const status = connected
    ? `:white_check_mark: Google account connected${email ? ` (${email})` : ""}`
    : `:x: Google account not connected. Use \`/google connect\` to link your account.`;
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "section",
      text: { type: "mrkdwn", text: status },
    },
  ];
  return { blocks, text: status };
}

export interface CalendarEvent {
  id: string;
  summary: string;
  start: string;
  end: string;
  location?: string;
  htmlLink?: string;
}

export function calendarEventBlocks(events: CalendarEvent[]): BlockResult {
  if (events.length === 0) {
    const text = "No upcoming events found.";
    return {
      blocks: [{ type: "section", text: { type: "mrkdwn", text } }],
      text,
    };
  }

  const lines = events.map((e) => {
    const link = e.htmlLink ? ` (<${e.htmlLink}|open>)` : "";
    const loc = e.location ? ` — _${e.location}_` : "";
    return `*${e.summary}*\n    ${e.start} → ${e.end}${loc}${link}`;
  });

  const text = `Found ${events.length} event(s)`;
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":calendar: Calendar Events", emoji: true },
    },
    ...lines.map(
      (line): KnownBlock | Block => ({
        type: "section",
        text: { type: "mrkdwn", text: line },
      }),
    ),
  ];
  return { blocks, text };
}

export interface DriveFile {
  id: string;
  name: string;
  mimeType: string;
  webViewLink?: string;
  modifiedTime?: string;
}

export function driveFileBlocks(files: DriveFile[]): BlockResult {
  if (files.length === 0) {
    const text = "No files found.";
    return {
      blocks: [{ type: "section", text: { type: "mrkdwn", text } }],
      text,
    };
  }

  const lines = files.map((f) => {
    const link = f.webViewLink ? `<${f.webViewLink}|${f.name}>` : f.name;
    const modified = f.modifiedTime ? ` — modified ${f.modifiedTime}` : "";
    return `${link}${modified}`;
  });

  const text = `Found ${files.length} file(s)`;
  const blocks: (KnownBlock | Block)[] = [
    {
      type: "header",
      text: { type: "plain_text", text: ":file_folder: Drive Files", emoji: true },
    },
    {
      type: "section",
      text: { type: "mrkdwn", text: lines.join("\n") },
    },
  ];
  return { blocks, text };
}
