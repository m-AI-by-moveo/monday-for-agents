import { describe, it, expect, beforeEach, afterEach } from "vitest";
import nock from "nock";
import { fetchBoards, clearBoardCache } from "../src/services/monday-client.js";

describe("monday-client", () => {
  beforeEach(() => {
    clearBoardCache();
    process.env.MONDAY_API_TOKEN = "test-monday-token";
    nock.disableNetConnect();
  });

  afterEach(() => {
    nock.cleanAll();
    nock.enableNetConnect();
    delete process.env.MONDAY_API_TOKEN;
  });

  it("fetches boards from Monday.com API", async () => {
    const mockBoards = [
      { id: "111", name: "Project Alpha" },
      { id: "222", name: "Project Beta" },
    ];

    nock("https://api.monday.com")
      .post("/v2")
      .reply(200, { data: { boards: mockBoards } });

    const boards = await fetchBoards();

    expect(boards).toHaveLength(2);
    expect(boards[0]).toEqual({ id: "111", name: "Project Alpha" });
    expect(boards[1]).toEqual({ id: "222", name: "Project Beta" });
  });

  it("returns cached boards on subsequent calls", async () => {
    const mockBoards = [{ id: "111", name: "Project Alpha" }];

    const scope = nock("https://api.monday.com")
      .post("/v2")
      .once()
      .reply(200, { data: { boards: mockBoards } });

    const first = await fetchBoards();
    const second = await fetchBoards();

    expect(first).toEqual(second);
    expect(scope.isDone()).toBe(true);
  });

  it("throws when MONDAY_API_TOKEN is not set", async () => {
    delete process.env.MONDAY_API_TOKEN;

    await expect(fetchBoards()).rejects.toThrow("MONDAY_API_TOKEN is not set");
  });

  it("returns empty array when API returns no boards", async () => {
    nock("https://api.monday.com")
      .post("/v2")
      .reply(200, { data: { boards: [] } });

    const boards = await fetchBoards();
    expect(boards).toHaveLength(0);
  });

  it("propagates API errors", async () => {
    nock("https://api.monday.com")
      .post("/v2")
      .replyWithError("Network failure");

    await expect(fetchBoards()).rejects.toThrow();
  });
});
