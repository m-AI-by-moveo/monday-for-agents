import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { MeetingStore } from "../src/services/meeting-store.js";

describe("MeetingStore", () => {
  let store: MeetingStore;

  beforeEach(() => {
    store = new MeetingStore(":memory:");
  });

  afterEach(() => {
    store.close();
  });

  it("isProcessed returns false for unknown event", () => {
    expect(store.isProcessed("unknown-event")).toBe(false);
  });

  it("markPending then isProcessed returns true", () => {
    store.markPending("evt-1", "Sprint Planning");
    expect(store.isProcessed("evt-1")).toBe(true);
  });

  it("getPending returns pending meetings", () => {
    store.markPending("evt-1", "Sprint Planning");
    store.markPending("evt-2", "Retro");

    const pending = store.getPending();
    expect(pending).toHaveLength(2);
    expect(pending.map((p) => p.event_id).sort()).toEqual(["evt-1", "evt-2"]);
    expect(pending[0].status).toBe("pending");
  });

  it("markApproved updates status and stores task IDs", () => {
    store.markPending("evt-1", "Sprint Planning");
    store.markApproved("evt-1", ["123456", "789012"]);

    const pending = store.getPending();
    expect(pending).toHaveLength(0);

    // Still processed
    expect(store.isProcessed("evt-1")).toBe(true);
  });

  it("markDismissed updates status", () => {
    store.markPending("evt-1", "Sprint Planning");
    store.markDismissed("evt-1");

    const pending = store.getPending();
    expect(pending).toHaveLength(0);
    expect(store.isProcessed("evt-1")).toBe(true);
  });

  it("getPending does not return approved or dismissed", () => {
    store.markPending("evt-1", "Meeting A");
    store.markPending("evt-2", "Meeting B");
    store.markPending("evt-3", "Meeting C");

    store.markApproved("evt-1", ["task1"]);
    store.markDismissed("evt-2");

    const pending = store.getPending();
    expect(pending).toHaveLength(1);
    expect(pending[0].event_id).toBe("evt-3");
  });

  it("markPending overwrites existing pending", () => {
    store.markPending("evt-1", "Old Title");
    store.markPending("evt-1", "New Title");

    const pending = store.getPending();
    expect(pending).toHaveLength(1);
    expect(pending[0].title).toBe("New Title");
  });
});
