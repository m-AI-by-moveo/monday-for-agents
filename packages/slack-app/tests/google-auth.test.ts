import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// ---------------------------------------------------------------------------
// Mock googleapis — vi.hoisted ensures fns exist before vi.mock hoist
// ---------------------------------------------------------------------------

const {
  mockGenerateAuthUrl,
  mockGetToken,
  mockRefreshAccessToken,
  mockRevokeToken,
  mockSetCredentials,
  MockOAuth2,
} = vi.hoisted(() => {
  const mockGenerateAuthUrl = vi.fn().mockReturnValue("https://accounts.google.com/o/oauth2/auth?mock");
  const mockGetToken = vi.fn();
  const mockRefreshAccessToken = vi.fn();
  const mockRevokeToken = vi.fn();
  const mockSetCredentials = vi.fn();

  class MockOAuth2 {
    generateAuthUrl = mockGenerateAuthUrl;
    getToken = mockGetToken;
    refreshAccessToken = mockRefreshAccessToken;
    revokeToken = mockRevokeToken;
    setCredentials = mockSetCredentials;
    constructor(..._args: any[]) {}
  }

  return {
    mockGenerateAuthUrl,
    mockGetToken,
    mockRefreshAccessToken,
    mockRevokeToken,
    mockSetCredentials,
    MockOAuth2,
  };
});

vi.mock("googleapis", () => ({
  google: {
    auth: {
      OAuth2: MockOAuth2,
    },
  },
}));

import { GoogleTokenStore } from "../src/services/google-token-store.js";
import { GoogleAuthService } from "../src/services/google-auth.js";

describe("GoogleAuthService", () => {
  let store: GoogleTokenStore;
  let auth: GoogleAuthService;

  beforeEach(() => {
    process.env.GOOGLE_CLIENT_ID = "test-client-id";
    process.env.GOOGLE_CLIENT_SECRET = "test-client-secret";
    process.env.GOOGLE_REDIRECT_URI = "http://localhost:3000/api/google/callback";
    process.env.SLACK_SIGNING_SECRET = "test-signing-secret";

    store = new GoogleTokenStore(":memory:");
    auth = new GoogleAuthService(store);

    mockGenerateAuthUrl.mockClear();
    mockGetToken.mockClear();
    mockRefreshAccessToken.mockClear();
    mockRevokeToken.mockClear();
    mockSetCredentials.mockClear();
  });

  afterEach(() => {
    store.close();
    vi.restoreAllMocks();
  });

  describe("getAuthUrl", () => {
    it("returns a URL string", () => {
      const url = auth.getAuthUrl("U12345");
      expect(url).toContain("google.com");
      expect(mockGenerateAuthUrl).toHaveBeenCalledOnce();
    });

    it("passes an HMAC-signed state to the OAuth URL generator", () => {
      auth.getAuthUrl("U12345");
      const callArgs = mockGenerateAuthUrl.mock.calls[0][0];
      expect(callArgs.state).toMatch(/^U12345:.+$/);
    });
  });

  describe("handleCallback", () => {
    it("exchanges code for tokens and stores them", async () => {
      mockGetToken.mockResolvedValue({
        tokens: {
          access_token: "ya29.access",
          refresh_token: "1//refresh",
          expiry_date: 9999999999999,
          scope: "calendar drive",
        },
      });

      // Generate a valid state using the internal HMAC mechanism
      const url = auth.getAuthUrl("U12345");
      const stateArg = mockGenerateAuthUrl.mock.calls[0][0].state;

      const userId = await auth.handleCallback("auth-code", stateArg);
      expect(userId).toBe("U12345");
      expect(store.has("U12345")).toBe(true);

      const record = store.get("U12345");
      expect(record!.access_token).toBe("ya29.access");
    });

    it("throws on tampered state", async () => {
      await expect(auth.handleCallback("code", "U12345:badsignature")).rejects.toThrow(
        "Invalid or tampered OAuth state",
      );
    });
  });

  describe("isConnected", () => {
    it("returns false when no tokens stored", () => {
      expect(auth.isConnected("U12345")).toBe(false);
    });

    it("returns true when tokens exist", () => {
      store.upsert({
        slack_user_id: "U12345",
        access_token: "ya29.access",
        refresh_token: "1//refresh",
        expiry_date: Date.now() + 3600_000,
        scope: "calendar drive",
      });
      expect(auth.isConnected("U12345")).toBe(true);
    });
  });

  describe("disconnect", () => {
    it("revokes token and removes from store", async () => {
      store.upsert({
        slack_user_id: "U12345",
        access_token: "ya29.access",
        refresh_token: "1//refresh",
        expiry_date: Date.now() + 3600_000,
        scope: "calendar drive",
      });

      mockRevokeToken.mockResolvedValue({});
      await auth.disconnect("U12345");

      expect(store.has("U12345")).toBe(false);
      expect(mockRevokeToken).toHaveBeenCalledWith("ya29.access");
    });

    it("does not throw if revocation fails", async () => {
      store.upsert({
        slack_user_id: "U12345",
        access_token: "ya29.expired",
        refresh_token: "1//refresh",
        expiry_date: 0,
        scope: "calendar drive",
      });

      mockRevokeToken.mockRejectedValue(new Error("Token expired"));
      await expect(auth.disconnect("U12345")).resolves.toBeUndefined();
      expect(store.has("U12345")).toBe(false);
    });

    it("is a no-op for unknown user", async () => {
      await expect(auth.disconnect("UNKNOWN")).resolves.toBeUndefined();
    });
  });

  describe("getClient", () => {
    it("throws if user not connected", async () => {
      await expect(auth.getClient("UNKNOWN")).rejects.toThrow("No Google tokens found");
    });

    it("returns an OAuth2 client for connected user", async () => {
      store.upsert({
        slack_user_id: "U12345",
        access_token: "ya29.access",
        refresh_token: "1//refresh",
        expiry_date: Date.now() + 3600_000,
        scope: "calendar drive",
      });

      const client = await auth.getClient("U12345");
      expect(client).toBeDefined();
      expect(mockSetCredentials).toHaveBeenCalled();
    });

    it("auto-refreshes expired tokens", async () => {
      store.upsert({
        slack_user_id: "U12345",
        access_token: "ya29.expired",
        refresh_token: "1//refresh",
        expiry_date: Date.now() - 1000, // expired
        scope: "calendar drive",
      });

      mockRefreshAccessToken.mockResolvedValue({
        credentials: {
          access_token: "ya29.refreshed",
          expiry_date: Date.now() + 3600_000,
        },
      });

      await auth.getClient("U12345");
      expect(mockRefreshAccessToken).toHaveBeenCalled();
      expect(store.get("U12345")!.access_token).toBe("ya29.refreshed");
    });
  });
});
