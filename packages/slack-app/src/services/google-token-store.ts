import Database from "better-sqlite3";

export interface GoogleTokenRecord {
  slack_user_id: string;
  access_token: string;
  refresh_token: string;
  expiry_date: number;
  scope: string;
}

export class GoogleTokenStore {
  private db: Database.Database;

  constructor(dbPath?: string) {
    const path = dbPath ?? process.env.GOOGLE_TOKEN_DB_PATH ?? "./data/google-tokens.sqlite";
    this.db = new Database(path);
    this.db.pragma("journal_mode = WAL");
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS google_tokens (
        slack_user_id TEXT PRIMARY KEY,
        access_token TEXT NOT NULL,
        refresh_token TEXT NOT NULL,
        expiry_date INTEGER NOT NULL,
        scope TEXT NOT NULL
      )
    `);
  }

  get(userId: string): GoogleTokenRecord | undefined {
    const row = this.db
      .prepare("SELECT * FROM google_tokens WHERE slack_user_id = ?")
      .get(userId) as GoogleTokenRecord | undefined;
    return row;
  }

  upsert(record: GoogleTokenRecord): void {
    this.db
      .prepare(
        `INSERT INTO google_tokens (slack_user_id, access_token, refresh_token, expiry_date, scope)
         VALUES (@slack_user_id, @access_token, @refresh_token, @expiry_date, @scope)
         ON CONFLICT(slack_user_id) DO UPDATE SET
           access_token = @access_token,
           refresh_token = @refresh_token,
           expiry_date = @expiry_date,
           scope = @scope`,
      )
      .run(record);
  }

  delete(userId: string): void {
    this.db.prepare("DELETE FROM google_tokens WHERE slack_user_id = ?").run(userId);
  }

  has(userId: string): boolean {
    const row = this.db
      .prepare("SELECT 1 FROM google_tokens WHERE slack_user_id = ?")
      .get(userId);
    return row !== undefined;
  }

  close(): void {
    this.db.close();
  }
}
