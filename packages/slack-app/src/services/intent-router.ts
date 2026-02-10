import Anthropic from "@anthropic-ai/sdk";

// ---------------------------------------------------------------------------
// Intent types
// ---------------------------------------------------------------------------

export const INTENT_TYPES = [
  "create-task",
  "board-status",
  "meeting-sync",
  "calendar",
  "drive",
  "agent-chat",
] as const;

export type IntentType = (typeof INTENT_TYPES)[number];

export interface ClassificationResult {
  intent: IntentType;
  agentKey: string;
}

// ---------------------------------------------------------------------------
// Keyword pre-filter — skip LLM for high-confidence matches
// ---------------------------------------------------------------------------

interface KeywordRule {
  keywords: string[];
  intent: IntentType;
  agentKey: string;
}

const KEYWORD_RULES: KeywordRule[] = [
  {
    keywords: ["create a task", "create task", "make a task", "add a task", "new task"],
    intent: "create-task",
    agentKey: "product-owner",
  },
  {
    keywords: ["board status", "sprint status", "standup", "stand-up"],
    intent: "board-status",
    agentKey: "scrum-master",
  },
  {
    keywords: ["sync meeting", "sync my meeting", "meeting sync", "sync meetings"],
    intent: "meeting-sync",
    agentKey: "product-owner",
  },
  {
    keywords: ["calendar", "schedule", "what's on my", "my agenda", "my meetings today", "book a meeting"],
    intent: "calendar",
    agentKey: "product-owner",
  },
  {
    keywords: ["find the file", "find a file", "search drive", "google drive", "my drive", "find the doc", "find document"],
    intent: "drive",
    agentKey: "product-owner",
  },
];

function keywordPreFilter(text: string): ClassificationResult | null {
  const lower = text.toLowerCase();
  for (const rule of KEYWORD_RULES) {
    for (const kw of rule.keywords) {
      if (lower.includes(kw)) {
        return { intent: rule.intent, agentKey: rule.agentKey };
      }
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Enhanced keyword fallback (used when LLM fails)
// ---------------------------------------------------------------------------

const SCRUM_MASTER_KEYWORDS = [
  "status",
  "standup",
  "blocked",
  "summary",
  "report",
  "sprint",
  "board",
];

const CREATE_TASK_KEYWORDS = ["create", "task", "add item"];
const CALENDAR_KEYWORDS = ["calendar", "schedule", "meeting", "agenda", "appointment", "book"];
const DRIVE_KEYWORDS = ["drive", "file", "document", "doc", "sheet", "folder"];
const MEETING_SYNC_KEYWORDS = ["sync", "transcript", "meeting notes"];

export function classifyFallback(text: string): ClassificationResult {
  const lower = text.toLowerCase();

  // Check create-task first (higher specificity)
  if (CREATE_TASK_KEYWORDS.some((kw) => lower.includes(kw)) && lower.includes("task")) {
    return { intent: "create-task", agentKey: "product-owner" };
  }

  if (MEETING_SYNC_KEYWORDS.some((kw) => lower.includes(kw))) {
    return { intent: "meeting-sync", agentKey: "product-owner" };
  }

  if (CALENDAR_KEYWORDS.some((kw) => lower.includes(kw))) {
    return { intent: "calendar", agentKey: "product-owner" };
  }

  if (DRIVE_KEYWORDS.some((kw) => lower.includes(kw))) {
    return { intent: "drive", agentKey: "product-owner" };
  }

  if (SCRUM_MASTER_KEYWORDS.some((kw) => lower.includes(kw))) {
    return { intent: "board-status", agentKey: "scrum-master" };
  }

  return { intent: "agent-chat", agentKey: "product-owner" };
}

// ---------------------------------------------------------------------------
// LLM classifier
// ---------------------------------------------------------------------------

const CLASSIFIER_SYSTEM_PROMPT = `You are an intent classifier for a Slack bot. Given a user message, determine the user's intent and respond with a JSON object.

Intents:
- "create-task": User wants to create a Monday.com task from the conversation or a description. Examples: "create a task from this conversation", "make a task for fixing the login bug", "add a task to the board".
- "board-status": User wants to know the current status of the Monday.com board, sprint, tasks, or standup. Examples: "what's the board status?", "give me a standup summary", "what's blocked?".
- "meeting-sync": User wants to sync or check recent meeting transcripts/notes. Examples: "sync my recent meetings", "check for meeting transcripts", "pull meeting notes".
- "calendar": User wants to interact with their Google Calendar — view, create, or manage events. Examples: "what's on my calendar tomorrow?", "book a meeting at 3pm", "what meetings do I have today?".
- "drive": User wants to interact with Google Drive — find, read, or create files. Examples: "find the Q4 report", "search my drive for the design doc", "create a new document".
- "agent-chat": General conversation, planning, brainstorming, or anything that doesn't fit the above categories. Examples: "plan a feature for user onboarding", "help me write a PRD", "what do you think about this approach?".

For "agent-chat", also determine which agent to route to:
- "product-owner": For feature planning, PRDs, requirements, general product questions.
- "scrum-master": For process questions, workflow optimization, agile methodology.
- "developer": For technical questions, code review, implementation details.
- "reviewer": For code review requests.

Respond ONLY with a JSON object: {"intent": "<intent>", "agentKey": "<agent>"}`;

export class IntentRouter {
  private client: Anthropic;

  constructor() {
    this.client = new Anthropic();
  }

  async classify(message: string): Promise<ClassificationResult> {
    // 1. Try keyword pre-filter first (instant, free)
    const keywordResult = keywordPreFilter(message);
    if (keywordResult) {
      console.log(`[intent-router] Keyword match: ${keywordResult.intent}`);
      return keywordResult;
    }

    // 2. Use LLM classifier
    try {
      const response = await this.client.messages.create({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 150,
        system: CLASSIFIER_SYSTEM_PROMPT,
        messages: [{ role: "user", content: message }],
      });

      const textBlock = response.content.find((b) => b.type === "text");
      if (!textBlock || textBlock.type !== "text") {
        console.warn("[intent-router] No text in LLM response, falling back");
        return classifyFallback(message);
      }

      let jsonText = textBlock.text.trim();
      if (jsonText.startsWith("```")) {
        jsonText = jsonText.replace(/^```(?:json)?\s*/, "").replace(/\s*```$/, "");
      }

      const parsed = JSON.parse(jsonText);
      const intent = INTENT_TYPES.includes(parsed.intent) ? parsed.intent : "agent-chat";
      const agentKey = parsed.agentKey || "product-owner";

      console.log(`[intent-router] LLM classified: ${intent} (agent=${agentKey})`);
      return { intent, agentKey };
    } catch (err) {
      console.error("[intent-router] LLM classification failed, falling back:", err);
      return classifyFallback(message);
    }
  }
}
