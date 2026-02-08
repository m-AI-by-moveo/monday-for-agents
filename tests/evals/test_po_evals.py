"""Product Owner agent evaluations.

These tests exercise the PO agent with a real LLM (mocking only the
Monday.com API) and evaluate output quality using an LLM-as-judge.
Tests are skipped if ``ANTHROPIC_API_KEY`` is not available.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

import monday_mcp.client as client_module
from monday_mcp.client import MONDAY_API_URL
from monday_mcp.tools.items import create_task

from tests.evals.eval_utils import (
    EvalResult,
    LLMJudge,
    TASK_BREAKDOWN_CRITERIA,
    score_task_breakdown,
)


# ---------------------------------------------------------------------------
# Skip condition
# ---------------------------------------------------------------------------

_SKIP_REASON = "ANTHROPIC_API_KEY not set; skipping eval tests"


def _should_skip() -> bool:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    return not key or key == "test-key-do-not-use"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    client_module._client = None


@pytest.fixture()
def po_system_prompt() -> str:
    """The PO agent's system prompt, extracted for direct LLM testing."""
    return (
        "You are a Product Owner agent. When given a feature request, "
        "respond with a JSON array of task objects. Each task must have: "
        '"name" (string), "priority" (Low/Medium/High/Critical), '
        '"type" (Feature/Bug/Chore/Spike), "assignee" (developer/reviewer), '
        '"description" (string with acceptance criteria). '
        "Break complex features into 2-6 well-scoped tasks."
    )


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.eval
@pytest.mark.slow
class TestPOTaskBreakdown:
    """Test PO breaks feature requests into well-structured tasks."""

    async def test_auth_feature_breakdown(self, real_llm: Any, po_system_prompt: str) -> None:
        """PO breaks 'Build user auth' into multiple tasks with correct fields."""
        feature_request = (
            "Build a user authentication system with email/password login, "
            "password reset, and session management."
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": po_system_prompt},
            {"role": "user", "content": feature_request},
        ])

        content = response.content
        # Extract JSON from the response
        if "```" in content:
            lines = content.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        tasks = json.loads(content)
        assert isinstance(tasks, list), "PO should return a list of tasks"
        assert len(tasks) >= 2, "Auth feature should produce at least 2 tasks"

        # Each task should have the required fields
        for task in tasks:
            assert "name" in task, f"Task missing 'name': {task}"
            assert "priority" in task, f"Task missing 'priority': {task}"
            assert "type" in task, f"Task missing 'type': {task}"
            assert "assignee" in task, f"Task missing 'assignee': {task}"

    async def test_auth_priority_is_high(self, real_llm: Any, po_system_prompt: str) -> None:
        """PO assigns High or Critical priority for auth tasks."""
        feature_request = "Build user authentication with email/password login."

        response = await real_llm.ainvoke([
            {"role": "system", "content": po_system_prompt},
            {"role": "user", "content": feature_request},
        ])

        content = response.content
        if "```" in content:
            lines = content.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        tasks = json.loads(content)
        high_priority = [t for t in tasks if t.get("priority") in ("High", "Critical")]
        assert len(high_priority) >= 1, (
            f"Auth tasks should have at least one High/Critical priority. "
            f"Got priorities: {[t.get('priority') for t in tasks]}"
        )

    async def test_correct_task_types(self, real_llm: Any, po_system_prompt: str) -> None:
        """PO assigns correct types (Feature for new functionality)."""
        feature_request = "Add a dark mode toggle to the settings page."

        response = await real_llm.ainvoke([
            {"role": "system", "content": po_system_prompt},
            {"role": "user", "content": feature_request},
        ])

        content = response.content
        if "```" in content:
            lines = content.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        tasks = json.loads(content)
        for task in tasks:
            assert task.get("type") in ("Feature", "Bug", "Chore", "Spike"), (
                f"Invalid task type: {task.get('type')}"
            )

        # A new feature should produce Feature type tasks
        feature_tasks = [t for t in tasks if t.get("type") == "Feature"]
        assert len(feature_tasks) >= 1, "Dark mode toggle should include Feature tasks"


@pytest.mark.eval
@pytest.mark.slow
class TestPOClarification:
    """Test PO asks clarifying questions for vague requests."""

    async def test_vague_request_gets_questions(self, real_llm: Any) -> None:
        """PO asks clarifying questions for a vague feature request."""
        system = (
            "You are a Product Owner agent. If a feature request is too vague "
            "or ambiguous to create well-defined tasks, respond with clarifying "
            "questions instead of tasks. Prefix your response with 'CLARIFY:' "
            "when asking questions, or 'TASKS:' when providing task breakdown."
        )
        vague_request = "We need some kind of notification thing."

        response = await real_llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": vague_request},
        ])

        content = response.content.lower()
        # The PO should ask questions, not just create tasks blindly
        has_questions = (
            "?" in response.content
            or "clarif" in content
            or "what" in content
            or "which" in content
            or "how" in content
        )
        assert has_questions, (
            "PO should ask clarifying questions for vague requests. "
            f"Got: {response.content[:200]}"
        )


@pytest.mark.eval
@pytest.mark.slow
class TestPOSubtasks:
    """Test PO creates subtasks for complex features."""

    async def test_complex_feature_subtasks(self, real_llm: Any, po_system_prompt: str) -> None:
        """PO creates multiple tasks for a complex feature."""
        complex_request = (
            "Implement a complete rate limiting system for our API. "
            "It should support per-endpoint limits, per-API-key limits, "
            "sliding window algorithm, Redis-backed counters, "
            "configurable via admin panel, and return proper 429 responses "
            "with Retry-After headers."
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": po_system_prompt},
            {"role": "user", "content": complex_request},
        ])

        content = response.content
        if "```" in content:
            lines = content.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        tasks = json.loads(content)
        assert len(tasks) >= 3, (
            f"Complex rate-limiting feature should produce 3+ tasks, got {len(tasks)}"
        )


@pytest.mark.eval
@pytest.mark.slow
class TestPOResponseQuality:
    """Test PO response quality using LLM-as-judge."""

    async def test_task_breakdown_quality(self, real_llm: Any, po_system_prompt: str) -> None:
        """LLM judge scores the PO's task breakdown quality."""
        feature_request = (
            "Build a user authentication system with email/password login, "
            "password reset, and session management."
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": po_system_prompt},
            {"role": "user", "content": feature_request},
        ])

        content = response.content
        if "```" in content:
            lines = content.split("\n")
            json_lines = []
            in_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_block = not in_block
                    continue
                if in_block:
                    json_lines.append(line)
            content = "\n".join(json_lines)

        try:
            tasks = json.loads(content)
        except json.JSONDecodeError:
            pytest.fail(f"PO output was not valid JSON: {content[:200]}")

        eval_result = await score_task_breakdown(
            feature_request=feature_request,
            created_tasks=tasks,
            llm=real_llm,
        )

        assert eval_result.passed, (
            f"PO task breakdown did not pass quality check. "
            f"Scores: {eval_result.scores}, "
            f"Average: {eval_result.average_score:.1f}"
        )
