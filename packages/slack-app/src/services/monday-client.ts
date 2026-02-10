import axios from "axios";

export interface MondayBoard {
  id: string;
  name: string;
}

export interface MondayUser {
  id: string;
  name: string;
}

const MONDAY_API_URL = "https://api.monday.com/v2";
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

let cachedBoards: MondayBoard[] | null = null;
let cacheTimestamp = 0;

export function clearBoardCache(): void {
  cachedBoards = null;
  cacheTimestamp = 0;
}

export async function fetchBoards(): Promise<MondayBoard[]> {
  const now = Date.now();
  if (cachedBoards && now - cacheTimestamp < CACHE_TTL_MS) {
    return cachedBoards;
  }

  const token = process.env.MONDAY_API_TOKEN;
  if (!token) {
    throw new Error("MONDAY_API_TOKEN is not set");
  }

  const query = `{ boards(limit: 50, order_by: used_at) { id name } }`;

  const res = await axios.post(
    MONDAY_API_URL,
    { query },
    {
      headers: {
        Authorization: token,
        "Content-Type": "application/json",
      },
      timeout: 10_000,
    },
  );

  const boards: MondayBoard[] = res.data?.data?.boards ?? [];
  cachedBoards = boards;
  cacheTimestamp = now;
  return boards;
}

let cachedUsers: MondayUser[] | null = null;
let usersCacheTimestamp = 0;

export function clearUsersCache(): void {
  cachedUsers = null;
  usersCacheTimestamp = 0;
}

export async function fetchUsers(): Promise<MondayUser[]> {
  const now = Date.now();
  if (cachedUsers && now - usersCacheTimestamp < CACHE_TTL_MS) {
    return cachedUsers;
  }

  const token = process.env.MONDAY_API_TOKEN;
  if (!token) {
    throw new Error("MONDAY_API_TOKEN is not set");
  }

  const query = `{ users(limit: 100) { id name } }`;

  const res = await axios.post(
    MONDAY_API_URL,
    { query },
    {
      headers: {
        Authorization: token,
        "Content-Type": "application/json",
      },
      timeout: 10_000,
    },
  );

  const users: MondayUser[] = res.data?.data?.users ?? [];
  cachedUsers = users;
  usersCacheTimestamp = now;
  return users;
}
