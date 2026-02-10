import Database from "better-sqlite3";

export interface ProcessedMeeting {
  event_id: string;
  title: string;
  processed_at: string;
  status: "approved" | "dismissed" | "pending";
  task_ids?: string;
}

export class MeetingStore {
  private db: Database.Database;

  constructor(dbPath?: string) {
    const path =
      dbPath ?? process.env.MEETING_STORE_DB_PATH ?? "./data/meeting-store.db";
    this.db = new Database(path);
    this.db.pragma("journal_mode = WAL");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS processed_meetings (
        event_id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        processed_at TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        task_ids TEXT
      )
    `);
  }

  isProcessed(eventId: string): boolean {
    const row = this.db
      .prepare("SELECT 1 FROM processed_meetings WHERE event_id = ?")
      .get(eventId);
    return row !== undefined;
  }

  markPending(eventId: string, title: string): void {
    this.db
      .prepare(
        `INSERT INTO processed_meetings (event_id, title, processed_at, status)
         VALUES (@event_id, @title, @processed_at, 'pending')
         ON CONFLICT(event_id) DO UPDATE SET
           title = @title,
           processed_at = @processed_at,
           status = 'pending'`,
      )
      .run({
        event_id: eventId,
        title,
        processed_at: new Date().toISOString(),
      });
  }

  markApproved(eventId: string, taskIds: string[]): void {
    this.db
      .prepare(
        `UPDATE processed_meetings
         SET status = 'approved', task_ids = @task_ids
         WHERE event_id = @event_id`,
      )
      .run({
        event_id: eventId,
        task_ids: taskIds.join(","),
      });
  }

  markDismissed(eventId: string, title?: string): void {
    this.db
      .prepare(
        `INSERT INTO processed_meetings (event_id, title, processed_at, status)
         VALUES (@event_id, @title, @processed_at, 'dismissed')
         ON CONFLICT(event_id) DO UPDATE SET
           status = 'dismissed'`,
      )
      .run({
        event_id: eventId,
        title: title ?? "",
        processed_at: new Date().toISOString(),
      });
  }

  getPending(): ProcessedMeeting[] {
    return this.db
      .prepare(
        "SELECT * FROM processed_meetings WHERE status = 'pending'",
      )
      .all() as ProcessedMeeting[];
  }

  close(): void {
    this.db.close();
  }
}
