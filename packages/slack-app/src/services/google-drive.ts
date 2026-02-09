import { google } from "googleapis";
import type { GoogleAuthService } from "./google-auth.js";
import type { DriveFile } from "../ui/google-blocks.js";

export interface ListFilesOptions {
  folderId?: string;
  maxResults?: number;
}

export interface CreateFileInput {
  name: string;
  mimeType: string;
  content?: string;
  parentFolderId?: string;
}

export class GoogleDriveService {
  constructor(private auth: GoogleAuthService) {}

  async listFiles(userId: string, opts?: ListFilesOptions): Promise<DriveFile[]> {
    const authClient = await this.auth.getClient(userId);
    const drive = google.drive({ version: "v3", auth: authClient });

    let q = "trashed = false";
    if (opts?.folderId) {
      q += ` and '${opts.folderId}' in parents`;
    }

    const res = await drive.files.list({
      q,
      pageSize: opts?.maxResults ?? 25,
      fields: "files(id, name, mimeType, webViewLink, modifiedTime)",
      orderBy: "modifiedTime desc",
    });

    return (res.data.files ?? []).map((f) => ({
      id: f.id ?? "",
      name: f.name ?? "",
      mimeType: f.mimeType ?? "",
      webViewLink: f.webViewLink ?? undefined,
      modifiedTime: f.modifiedTime ?? undefined,
    }));
  }

  async searchFiles(userId: string, query: string): Promise<DriveFile[]> {
    const authClient = await this.auth.getClient(userId);
    const drive = google.drive({ version: "v3", auth: authClient });

    const res = await drive.files.list({
      q: `name contains '${query.replace(/'/g, "\\'")}' and trashed = false`,
      pageSize: 25,
      fields: "files(id, name, mimeType, webViewLink, modifiedTime)",
      orderBy: "modifiedTime desc",
    });

    return (res.data.files ?? []).map((f) => ({
      id: f.id ?? "",
      name: f.name ?? "",
      mimeType: f.mimeType ?? "",
      webViewLink: f.webViewLink ?? undefined,
      modifiedTime: f.modifiedTime ?? undefined,
    }));
  }

  async readFile(userId: string, fileId: string): Promise<string> {
    const authClient = await this.auth.getClient(userId);
    const drive = google.drive({ version: "v3", auth: authClient });

    // Try to export as text for Google Docs; fall back to direct download
    const meta = await drive.files.get({ fileId, fields: "mimeType" });
    const mimeType = meta.data.mimeType ?? "";

    if (mimeType.startsWith("application/vnd.google-apps.")) {
      const res = await drive.files.export(
        { fileId, mimeType: "text/plain" },
        { responseType: "text" },
      );
      return String(res.data);
    }

    const res = await drive.files.get(
      { fileId, alt: "media" },
      { responseType: "text" },
    );
    return String(res.data);
  }

  async createFile(userId: string, input: CreateFileInput): Promise<DriveFile> {
    const authClient = await this.auth.getClient(userId);
    const drive = google.drive({ version: "v3", auth: authClient });

    const requestBody: Record<string, any> = {
      name: input.name,
      mimeType: input.mimeType,
    };
    if (input.parentFolderId) {
      requestBody.parents = [input.parentFolderId];
    }

    const res = await drive.files.create({
      requestBody,
      fields: "id, name, mimeType, webViewLink, modifiedTime",
    });

    return {
      id: res.data.id ?? "",
      name: res.data.name ?? "",
      mimeType: res.data.mimeType ?? "",
      webViewLink: res.data.webViewLink ?? undefined,
      modifiedTime: res.data.modifiedTime ?? undefined,
    };
  }

  async updateFile(
    userId: string,
    fileId: string,
    update: { name?: string; content?: string },
  ): Promise<DriveFile> {
    const authClient = await this.auth.getClient(userId);
    const drive = google.drive({ version: "v3", auth: authClient });

    const requestBody: Record<string, any> = {};
    if (update.name) requestBody.name = update.name;

    const res = await drive.files.update({
      fileId,
      requestBody,
      fields: "id, name, mimeType, webViewLink, modifiedTime",
    });

    return {
      id: res.data.id ?? "",
      name: res.data.name ?? "",
      mimeType: res.data.mimeType ?? "",
      webViewLink: res.data.webViewLink ?? undefined,
      modifiedTime: res.data.modifiedTime ?? undefined,
    };
  }

  async deleteFile(userId: string, fileId: string): Promise<void> {
    const authClient = await this.auth.getClient(userId);
    const drive = google.drive({ version: "v3", auth: authClient });

    await drive.files.delete({ fileId });
  }
}
