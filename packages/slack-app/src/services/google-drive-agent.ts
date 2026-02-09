import Anthropic from "@anthropic-ai/sdk";
import type { GoogleDriveService } from "./google-drive.js";

const DRIVE_TOOLS: Anthropic.Tool[] = [
  {
    name: "list_files",
    description:
      "List files in Google Drive, optionally within a specific folder. Shows recent files by default.",
    input_schema: {
      type: "object" as const,
      properties: {
        folder_id: {
          type: "string",
          description: "Optional folder ID to list contents of",
        },
        max_results: {
          type: "number",
          description: "Maximum number of files to return (default 25)",
        },
      },
      required: [],
    },
  },
  {
    name: "search_files",
    description: "Search for files by name in Google Drive.",
    input_schema: {
      type: "object" as const,
      properties: {
        query: {
          type: "string",
          description: "Search query to match against file names",
        },
      },
      required: ["query"],
    },
  },
  {
    name: "read_file",
    description:
      "Read the text content of a file. Works with Google Docs, Sheets, and plain text files.",
    input_schema: {
      type: "object" as const,
      properties: {
        file_id: {
          type: "string",
          description: "The file ID to read",
        },
      },
      required: ["file_id"],
    },
  },
  {
    name: "create_file",
    description: "Create a new file or Google Doc in Drive.",
    input_schema: {
      type: "object" as const,
      properties: {
        name: {
          type: "string",
          description: "File name",
        },
        mime_type: {
          type: "string",
          description:
            'MIME type. Common values: "application/vnd.google-apps.document" (Google Doc), "application/vnd.google-apps.spreadsheet" (Sheet), "text/plain"',
        },
      },
      required: ["name"],
    },
  },
  {
    name: "delete_file",
    description: "Delete a file from Google Drive.",
    input_schema: {
      type: "object" as const,
      properties: {
        file_id: {
          type: "string",
          description: "The file ID to delete",
        },
      },
      required: ["file_id"],
    },
  },
];

export class GoogleDriveAgent {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic();
  }

  async handleRequest(
    userMessage: string,
    driveService: GoogleDriveService,
    userId: string,
  ): Promise<string> {
    const systemPrompt = `You are a Google Drive assistant integrated into Slack. Help the user manage their files.

Instructions:
- Use the provided tools to interact with the user's Google Drive.
- Keep responses concise — this is Slack.
- Use Slack mrkdwn formatting (*bold*, _italic_, \`code\`).
- NEVER use ** for bold — Slack uses single * for bold.
- When listing files, format them nicely with names and links.
- When searching, be helpful about what was found or suggest alternatives.`;

    const messages: Anthropic.MessageParam[] = [
      { role: "user", content: userMessage },
    ];

    let iterations = 0;
    const maxIterations = 5;

    while (iterations < maxIterations) {
      iterations++;

      const response = await this.client.messages.create({
        model: "claude-sonnet-4-5-20250929",
        max_tokens: 1024,
        system: systemPrompt,
        tools: DRIVE_TOOLS,
        messages,
      });

      const textParts: string[] = [];
      const toolUseBlocks: Anthropic.ToolUseBlock[] = [];

      for (const block of response.content) {
        if (block.type === "text") {
          textParts.push(block.text);
        } else if (block.type === "tool_use") {
          toolUseBlocks.push(block);
        }
      }

      if (toolUseBlocks.length === 0) {
        return textParts.join("\n") || "Done.";
      }

      messages.push({ role: "assistant", content: response.content });

      const toolResults: Anthropic.ToolResultBlockParam[] = [];

      for (const toolUse of toolUseBlocks) {
        const result = await this.executeTool(
          toolUse.name,
          toolUse.input as Record<string, any>,
          driveService,
          userId,
        );
        toolResults.push({
          type: "tool_result",
          tool_use_id: toolUse.id,
          content: JSON.stringify(result),
        });
      }

      messages.push({ role: "user", content: toolResults });
    }

    return "I hit the maximum number of steps. Please try a simpler request.";
  }

  private async executeTool(
    name: string,
    input: Record<string, any>,
    driveService: GoogleDriveService,
    userId: string,
  ): Promise<any> {
    try {
      switch (name) {
        case "list_files":
          return await driveService.listFiles(userId, {
            folderId: input.folder_id,
            maxResults: input.max_results,
          });
        case "search_files":
          return await driveService.searchFiles(userId, input.query);
        case "read_file":
          return { content: await driveService.readFile(userId, input.file_id) };
        case "create_file":
          return await driveService.createFile(userId, {
            name: input.name,
            mimeType: input.mime_type ?? "application/vnd.google-apps.document",
          });
        case "delete_file":
          await driveService.deleteFile(userId, input.file_id);
          return { status: "deleted", file_id: input.file_id };
        default:
          return { error: `Unknown tool: ${name}` };
      }
    } catch (err: any) {
      return { error: err.message ?? String(err) };
    }
  }
}
