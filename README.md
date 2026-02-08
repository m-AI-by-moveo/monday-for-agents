# Monday for Agents

An internal platform where AI agents collaborate like a real dev team — with **Monday.com** as their shared task board, **Google A2A** for inter-agent communication, **MCP** for tool access, **LangGraph** for orchestration, and **Slack** for human-in-the-loop participation.

## Architecture

```
Human (Slack) → Slack App (Gateway) → Product Owner Agent (A2A)
                                           ├── Developer Agent (A2A)
                                           └── Reviewer Agent (A2A)
                                       All agents ↔ Monday.com (via MCP)
                                       Scrum Master (monitors + nudges)
```

**Key principle:** Each agent = 1 process = 1 A2A server. Monday.com is the single source of truth for all task state.

## Agents

| Agent | Port | Role |
|-------|------|------|
| **Product Owner** | 10001 | Receives feature requests, breaks into tasks, delegates |
| **Developer** | 10002 | Picks up tasks, produces implementation plans |
| **Reviewer** | 10003 | Reviews work, approves or requests changes |
| **Scrum Master** | 10004 | Monitors board, nudges stuck agents, reports to Slack |

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 22+
- [uv](https://github.com/astral-sh/uv) (Python package manager)
- A Monday.com account with API token
- An Anthropic API key
- A Slack workspace with a bot app configured

### Setup

1. **Clone and install dependencies:**

```bash
cp .env.example .env
# Edit .env with your actual tokens
make install
```

2. **Create Monday.com boards:**

```bash
make setup-board
# Note the board IDs and add them to .env
```

3. **Sync agent definitions to Monday.com:**

```bash
make sync-agents
```

4. **Run all agents:**

```bash
make run-all
```

5. **Run the Slack app (in a separate terminal):**

```bash
make slack-dev
```

### Using Docker

```bash
docker compose up --build
```

## How It Works

1. A human mentions the bot in Slack: `@agents Build a user authentication system`
2. The Slack app routes the message to the **Product Owner** agent via A2A
3. The Product Owner breaks the request into tasks on the Monday.com board
4. The Product Owner notifies the **Developer** agent about new tasks via A2A
5. The Developer picks up tasks, updates status to "In Progress", and works on them
6. When done, the Developer moves tasks to "In Review" and notifies the **Reviewer**
7. The Reviewer approves (→ Done) or requests changes (→ back to In Progress)
8. The **Scrum Master** periodically scans the board and nudges stuck agents
9. Humans can observe everything on Monday.com and intervene by editing tasks directly

## Project Structure

```
monday-for-agents/
├── agents/              # Agent YAML definitions
├── packages/
│   ├── a2a-server/      # A2A server + LangGraph agent runner
│   ├── monday-mcp/      # MCP server wrapping Monday.com API
│   ├── slack-app/        # TypeScript Slack gateway
│   └── monday-sync/     # Sync agent YAML → Monday.com registry
├── docker-compose.yaml
├── Makefile
└── .env.example
```

## Configuration

All agent configuration lives in YAML files under `agents/`. Environment variables are expanded at load time (`${MONDAY_BOARD_ID}` → actual value).

See `agents/product-owner.yaml` for a complete example.

## MCP Tools

The Monday.com MCP server exposes these tools to all agents:

| Tool | Description |
|------|-------------|
| `create_task` | Create a task on the board |
| `update_task_status` | Change task status + optional comment |
| `get_my_tasks` | Get tasks filtered by assignee |
| `get_board_summary` | All tasks grouped by status |
| `get_task_details` | Full item details with comments |
| `add_task_comment` | Add a comment to a task |
| `create_subtask` | Create a subtask under a parent |
| `move_task_to_group` | Move task between board groups |

## Development

```bash
# Run a single agent
make run AGENT=product-owner

# Test A2A endpoint
make test-a2a AGENT=product-owner MSG="Build an auth system"

# View Docker logs
make docker-logs
```
