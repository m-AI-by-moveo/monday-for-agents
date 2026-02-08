.PHONY: install dev run-all run stop clean setup-board sync-agents lint test test-unit test-integration test-e2e test-evals test-slack test-all test-coverage

# Install all dependencies
install:
	cd packages/monday-mcp && uv pip install -e .
	cd packages/a2a-server && uv pip install -e .
	cd packages/monday-sync && uv pip install -e .
	cd packages/slack-app && npm install

# Run all agents locally
run-all:
	mfa run-all --agents-dir agents

# Run a single agent (usage: make run AGENT=product-owner)
run:
	mfa run $(AGENT) --agents-dir agents

# Run the Slack app in dev mode
slack-dev:
	cd packages/slack-app && npm run dev

# Set up Monday.com boards
setup-board:
	monday-sync setup

# Sync agent definitions to Monday.com registry board
sync-agents:
	monday-sync sync --agents-dir agents

# Docker: build and start all services
docker-up:
	docker compose up --build -d

# Docker: stop all services
docker-down:
	docker compose down

# Docker: view logs
docker-logs:
	docker compose logs -f

# Clean build artifacts
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	rm -rf packages/slack-app/dist packages/slack-app/node_modules

# Run linters
lint:
	cd packages/a2a-server && uv run ruff check src/
	cd packages/monday-mcp && uv run ruff check src/

# ---- Testing ----

# Run all Python tests (unit + integration, no evals)
test:
	pytest tests/ -m "not eval and not e2e" -v

# Run unit tests only
test-unit:
	pytest tests/unit/ -v

# Run integration tests only
test-integration:
	pytest tests/integration/ -v

# Run end-to-end tests (requires running services)
test-e2e:
	pytest tests/e2e/ -v -m e2e

# Run LLM evaluation tests (requires ANTHROPIC_API_KEY)
test-evals:
	pytest tests/evals/ -v -m eval --timeout=120

# Run Slack app TypeScript tests
test-slack:
	cd packages/slack-app && npm test

# Run ALL tests (Python + TypeScript)
test-all: test test-slack

# Run tests with coverage report
test-coverage:
	pytest tests/ -m "not eval and not e2e" --cov --cov-report=html --cov-report=term-missing
	cd packages/slack-app && npm run test:coverage

# Run tests in parallel
test-fast:
	pytest tests/unit/ -n auto -v

# Test a single MCP tool (usage: make test-mcp TOOL=get_board_summary)
test-mcp:
	python -m monday_mcp.server

# Send a test A2A message to an agent (usage: make test-a2a AGENT=product-owner MSG="Build an auth system")
test-a2a:
	curl -s -X POST http://localhost:10001/ \
		-H "Content-Type: application/json" \
		-d '{"jsonrpc":"2.0","method":"message/send","params":{"message":{"role":"user","parts":[{"type":"text","text":"$(MSG)"}]}},"id":"test-1"}' | python -m json.tool
