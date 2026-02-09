import { google } from "googleapis";
import { createHmac } from "crypto";
import { GoogleTokenStore } from "./google-token-store.js";
import type { GoogleTokenRecord } from "./google-token-store.js";

const SCOPES = [
  "https://www.googleapis.com/auth/calendar",
  "https://www.googleapis.com/auth/drive",
];

export class GoogleAuthService {
  private clientId: string;
  private clientSecret: string;
  private redirectUri: string;
  private signingSecret: string;
  private tokenStore: GoogleTokenStore;

  constructor(tokenStore: GoogleTokenStore) {
    this.clientId = process.env.GOOGLE_CLIENT_ID ?? "";
    this.clientSecret = process.env.GOOGLE_CLIENT_SECRET ?? "";
    this.redirectUri = process.env.GOOGLE_REDIRECT_URI ?? "";
    this.signingSecret = process.env.SLACK_SIGNING_SECRET ?? "";
    this.tokenStore = tokenStore;

    if (!this.clientId || !this.clientSecret || !this.redirectUri) {
      console.warn(
        "[google-auth] Missing GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, or GOOGLE_REDIRECT_URI — Google integration disabled",
      );
    }
  }

  private createOAuth2Client() {
    return new google.auth.OAuth2(this.clientId, this.clientSecret, this.redirectUri);
  }

  private signState(slackUserId: string): string {
    const hmac = createHmac("sha256", this.signingSecret);
    hmac.update(slackUserId);
    const signature = hmac.digest("hex");
    return `${slackUserId}:${signature}`;
  }

  private verifyState(state: string): string | null {
    const parts = state.split(":");
    if (parts.length !== 2) return null;
    const [userId, signature] = parts;
    const expected = createHmac("sha256", this.signingSecret)
      .update(userId)
      .digest("hex");
    if (signature !== expected) return null;
    return userId;
  }

  getAuthUrl(slackUserId: string): string {
    const oauth2Client = this.createOAuth2Client();
    const state = this.signState(slackUserId);
    return oauth2Client.generateAuthUrl({
      access_type: "offline",
      scope: SCOPES,
      state,
      prompt: "consent",
    });
  }

  async handleCallback(code: string, state: string): Promise<string> {
    const slackUserId = this.verifyState(state);
    if (!slackUserId) {
      throw new Error("Invalid or tampered OAuth state");
    }

    const oauth2Client = this.createOAuth2Client();
    const { tokens } = await oauth2Client.getToken(code);

    if (!tokens.access_token || !tokens.refresh_token) {
      throw new Error("Missing tokens in OAuth response");
    }

    const record: GoogleTokenRecord = {
      slack_user_id: slackUserId,
      access_token: tokens.access_token,
      refresh_token: tokens.refresh_token,
      expiry_date: tokens.expiry_date ?? 0,
      scope: tokens.scope ?? SCOPES.join(" "),
    };

    this.tokenStore.upsert(record);
    return slackUserId;
  }

  async getClient(slackUserId: string) {
    const record = this.tokenStore.get(slackUserId);
    if (!record) {
      throw new Error("No Google tokens found. Please connect with /google connect");
    }

    const oauth2Client = this.createOAuth2Client();
    oauth2Client.setCredentials({
      access_token: record.access_token,
      refresh_token: record.refresh_token,
      expiry_date: record.expiry_date,
    });

    // Auto-refresh if expired
    if (record.expiry_date && record.expiry_date < Date.now()) {
      const { credentials } = await oauth2Client.refreshAccessToken();
      this.tokenStore.upsert({
        ...record,
        access_token: credentials.access_token ?? record.access_token,
        expiry_date: credentials.expiry_date ?? record.expiry_date,
      });
      oauth2Client.setCredentials(credentials);
    }

    return oauth2Client;
  }

  isConnected(slackUserId: string): boolean {
    return this.tokenStore.has(slackUserId);
  }

  async disconnect(slackUserId: string): Promise<void> {
    const record = this.tokenStore.get(slackUserId);
    if (record) {
      try {
        const oauth2Client = this.createOAuth2Client();
        oauth2Client.setCredentials({ access_token: record.access_token });
        await oauth2Client.revokeToken(record.access_token);
      } catch {
        // Revocation may fail if token is already expired — continue with deletion
      }
      this.tokenStore.delete(slackUserId);
    }
  }
}
