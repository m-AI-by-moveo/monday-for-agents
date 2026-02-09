import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { GoogleTokenStore } from "../src/services/google-token-store.js";
import type { GoogleTokenRecord } from "../src/services/google-token-store.js";

describe("GoogleTokenStore", () => {
  let store: GoogleTokenStore;

  beforeEach(() => {
    store = new GoogleTokenStore(":memory:");
  });

  afterEach(() => {
    store.close();
  });

  const sampleRecord: GoogleTokenRecord = {
    slack_user_id: "U12345",
    access_token: "ya29.access",
    refresh_token: "1//refresh",
    expiry_date: Date.now() + 3600_000,
    scope: "calendar drive",
  };

  it("returns undefined for unknown user", () => {
    expect(store.get("UNKNOWN")).toBeUndefined();
  });

  it("has() returns false for unknown user", () => {
    expect(store.has("UNKNOWN")).toBe(false);
  });

  it("upsert + get round-trips a record", () => {
    store.upsert(sampleRecord);
    const got = store.get("U12345");
    expect(got).toBeDefined();
    expect(got!.access_token).toBe("ya29.access");
    expect(got!.refresh_token).toBe("1//refresh");
    expect(got!.scope).toBe("calendar drive");
  });

  it("has() returns true after upsert", () => {
    store.upsert(sampleRecord);
    expect(store.has("U12345")).toBe(true);
  });

  it("upsert overwrites existing record", () => {
    store.upsert(sampleRecord);
    store.upsert({ ...sampleRecord, access_token: "ya29.new" });
    const got = store.get("U12345");
    expect(got!.access_token).toBe("ya29.new");
  });

  it("delete removes a record", () => {
    store.upsert(sampleRecord);
    store.delete("U12345");
    expect(store.get("U12345")).toBeUndefined();
    expect(store.has("U12345")).toBe(false);
  });

  it("delete is a no-op for unknown user", () => {
    expect(() => store.delete("UNKNOWN")).not.toThrow();
  });
});
