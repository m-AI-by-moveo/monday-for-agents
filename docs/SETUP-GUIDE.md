# Monday for Agents - Setup & Connection Guide

## Quick Overview

Monday for Agents is a multi-agent AI platform where 4 AI agents (Product Owner, Developer, Reviewer, Scrum Master) collaborate like a real dev team. They use **Monday.com** as their shared project board, communicate with each other via **Google A2A**, and interact with your team through **Slack**.

---

## Step 1: Connect Monday.com

### 1a. Get your API Token

1. Log into [monday.com](https://monday.com)
2. Click your **avatar** (bottom-left) → **Administration** → **Connections** → **API**
3. Click **Generate** to create a Personal API Token (or use an existing one)
4. Copy the token — it looks like: `eyJhbGciOi...`

> **Permissions needed:** The token needs read/write access to boards, items, columns, groups, and updates.

### 1b. Create the Task Board

You have two options:

**Option A: Automatic setup** (recommended)
```bash
# Set your token first
export MONDAY_API_TOKEN=eyJhbGciOi...

# Run the board setup command
make setup-board
```
This creates an "Agent Tasks" board with the correct columns (Status, Priority, Assignee, Type, Context ID) and groups (To Do, In Progress, In Review, Done, Blocked).

**Option B: Manual setup**
1. Create a new board called "Agent Tasks"
2. Add these columns:
   - **Status** (Status type): Labels → To Do, In Progress, In Review, Done, Blocked
   - **Priority** (Status type): Labels → Low, Medium, High, Critical
   - **Assignee** (Text type)
   - **Type** (Dropdown type): Options → Feature, Bug, Chore, Spike
   - **Context ID** (Text type)
3. Create groups: To Do, In Progress, In Review, Done, Blocked

### 1c. Get the Board ID

1. Open your "Agent Tasks" board in monday.com
2. Look at the URL: `https://your-org.monday.com/boards/123456789`
3. Copy the number — that's your Board ID

---

## Step 2: Connect Slack

### 2a. Create a Slack App

1. Go to [api.slack.com/apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name it "Monday Agents" (or your preferred name)
4. Select your organization's workspace

### 2b. Configure Bot Permissions

Go to **OAuth & Permissions** and add these **Bot Token Scopes**:

| Scope | Purpose |
|-------|---------|
| `app_mentions:read` | Detect @bot mentions |
| `chat:write` | Send messages and replies |
| `commands` | Handle slash commands |
| `channels:history` | Read thread replies |
| `groups:history` | Read thread replies in private channels |

### 2c. Enable Socket Mode (recommended for development)

1. Go to **Settings** → **Socket Mode** → **Enable Socket Mode**
2. When prompted, create an app-level token with `connections:write` scope
3. Name it "socket-token" and copy it — it looks like: `xapp-1-...`

### 2d. Enable Events

1. Go to **Event Subscriptions** → **Enable Events**
2. Under **Subscribe to bot events**, add:
   - `app_mention`
   - `message.channels`
   - `message.groups`

### 2e. Register Slash Commands

Go to **Slash Commands** and create:

| Command | Description | Usage Hint |
|---------|-------------|------------|
| `/agents` | List all registered AI agents | |
| `/status` | Get current board status summary | |

### 2f. Install the App

1. Go to **Install App** → **Install to Workspace**
2. Authorize the requested permissions
3. Copy the **Bot User OAuth Token** — it looks like: `xoxb-...`
4. Go to **Basic Information** and copy the **Signing Secret**

### 2g. Invite the Bot to a Channel

In Slack, go to the channel where you want to use the agents and type:
```
/invite @Monday Agents
```

---

## Step 3: Get Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Navigate to **API Keys** → **Create Key**
3. Copy the key — it looks like: `sk-ant-...`

---

## Step 4: Configure Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Fill in all the values:

```env
# Monday.com
MONDAY_API_TOKEN=eyJhbGciOi...          # From Step 1a
MONDAY_BOARD_ID=123456789                 # From Step 1c

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...              # From Step 3

# Slack
SLACK_BOT_TOKEN=xoxb-...                  # From Step 2f
SLACK_SIGNING_SECRET=abc123...            # From Step 2f
SLACK_APP_TOKEN=xapp-1-...               # From Step 2c (Socket Mode)

# Slack notification channel (where agents post proactive updates)
SLACK_CHANNEL_ID=C0123456789              # Right-click channel → Copy link → extract ID
```

> **To find Channel ID:** Right-click the Slack channel → "View channel details" → scroll to bottom → copy the Channel ID (starts with `C`).

---

## Step 5: Run the Platform

### Option A: Docker (recommended for production)

```bash
# Start all services
make docker-up

# View logs
make docker-logs

# Stop
make docker-down
```

### Option B: Local development

```bash
# Install dependencies
make install

# Terminal 1: Start all agents
make run-all

# Terminal 2: Start Slack app
make slack-dev
```

---

## Step 6: Test It

1. Go to the Slack channel where you invited the bot
2. Type: `@Monday Agents Build a user authentication system with JWT tokens`
3. Watch:
   - The PO agent responds in Slack with a task breakdown
   - Tasks appear on your Monday.com board
   - Developer agent picks up tasks and updates progress
   - Reviewer agent reviews completed work
   - Scrum Master reports status periodically

### Other commands to try:

```
@Monday Agents what's the current status?          → Routes to Scrum Master
@Monday Agents any blocked tasks?                  → Routes to Scrum Master
@Monday Agents build a payment integration         → Routes to Product Owner
/agents                                             → Lists all agents
/status                                             → Board status summary
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Bot doesn't respond to mentions | Make sure the bot is invited to the channel and `app_mention` event is subscribed |
| "MONDAY_API_TOKEN" errors | Verify the token in `.env` and that it has board read/write permissions |
| Tasks not appearing on board | Check `MONDAY_BOARD_ID` matches your board URL |
| Slack "not_authed" errors | Regenerate the Bot Token and update `.env` |
| Agents can't communicate | Ensure all 4 agent ports (10001-10004) are free |

---

## Architecture Summary

```
Human (Slack) → Slack Gateway → Product Owner Agent
                                      ↓ creates tasks
                                Monday.com Board ← all agents read/write
                                      ↓ delegates
                   Developer Agent ←→ Reviewer Agent
                                      ↓ monitors
                              Scrum Master Agent → Slack (status reports)
```

**Key principle:** Monday.com is the single source of truth. All agent actions (task creation, status changes, comments) are visible on the board. Humans can override anything at any time by editing the board directly.
