"""Developer agent evaluations.

These tests exercise the developer agent with a real LLM and evaluate
output quality using an LLM-as-judge.  Tests are skipped if
``ANTHROPIC_API_KEY`` is not available.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from tests.evals.eval_utils import (
    EvalResult,
    LLMJudge,
    IMPLEMENTATION_PLAN_CRITERIA,
    score_implementation_plan,
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


@pytest.fixture()
def dev_system_prompt() -> str:
    """Developer agent system prompt for direct LLM testing."""
    return (
        "You are a Developer agent. When given a task, produce a detailed "
        "implementation plan. Your plan should include:\n"
        "1. Technical approach and architecture decisions\n"
        "2. Step-by-step implementation steps\n"
        "3. Key technical decisions with rationale\n"
        "4. Potential risks and mitigations\n"
        "5. Testing strategy\n\n"
        "Respond with a structured, professional implementation plan."
    )


@pytest.fixture()
def sample_task() -> dict[str, str]:
    """A sample task for the developer to work on."""
    return {
        "name": "Implement JWT-based authentication",
        "description": (
            "Build a JWT-based authentication system for the API. "
            "Requirements: issue access and refresh tokens on login, "
            "validate tokens on protected endpoints, handle token "
            "expiry and refresh, store refresh tokens in Redis."
        ),
        "priority": "High",
        "type": "Feature",
    }


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.eval
@pytest.mark.slow
class TestDeveloperImplementationPlan:
    """Test developer reads task and produces implementation plan."""

    async def test_produces_plan(
        self, real_llm: Any, dev_system_prompt: str, sample_task: dict[str, str]
    ) -> None:
        """Developer produces a non-empty implementation plan for a task."""
        task_text = (
            f"Task: {sample_task['name']}\n"
            f"Description: {sample_task['description']}\n"
            f"Priority: {sample_task['priority']}\n"
            f"Type: {sample_task['type']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": dev_system_prompt},
            {"role": "user", "content": f"Work on this task:\n{task_text}"},
        ])

        plan = response.content
        assert len(plan) > 100, "Implementation plan should be substantive"

        # Plan should mention key technical concepts
        plan_lower = plan.lower()
        assert any(word in plan_lower for word in ["jwt", "token", "auth"]), (
            "Plan should reference JWT/token/auth concepts"
        )

    async def test_plan_has_structure(
        self, real_llm: Any, dev_system_prompt: str, sample_task: dict[str, str]
    ) -> None:
        """Developer's plan has clear structure (headers, steps, etc.)."""
        task_text = f"Task: {sample_task['name']}\nDescription: {sample_task['description']}"

        response = await real_llm.ainvoke([
            {"role": "system", "content": dev_system_prompt},
            {"role": "user", "content": f"Work on this task:\n{task_text}"},
        ])

        plan = response.content
        # A structured plan should have numbered steps or headers
        has_structure = (
            any(f"{i}." in plan for i in range(1, 6))
            or "#" in plan
            or "**" in plan
            or "Step" in plan
        )
        assert has_structure, "Plan should have structured sections or numbered steps"


@pytest.mark.eval
@pytest.mark.slow
class TestDeveloperStatusUpdates:
    """Test developer updates task status correctly."""

    async def test_status_update_response(self, real_llm: Any) -> None:
        """Developer produces appropriate status update messages."""
        system = (
            "You are a Developer agent. You have just started working on a task. "
            "Produce a brief status update comment to post on the Monday.com task. "
            "Include: what you're starting with, your approach, and estimated effort. "
            "Keep it concise (2-4 sentences)."
        )

        task = "Implement JWT-based authentication for the API"

        response = await real_llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": f"Write a status update for starting work on: {task}"},
        ])

        update = response.content
        assert len(update) > 20, "Status update should have meaningful content"
        assert len(update) < 2000, "Status update should be concise"


@pytest.mark.eval
@pytest.mark.slow
class TestDeveloperProgressComments:
    """Test developer adds meaningful progress comments."""

    async def test_progress_comment_quality(self, real_llm: Any) -> None:
        """Developer progress comments are meaningful and informative."""
        system = (
            "You are a Developer agent midway through implementing a task. "
            "Write a progress comment for the Monday.com task board. "
            "Include: what you've completed, what's remaining, and any "
            "decisions you've made. Be technical and precise."
        )

        context = (
            "Task: Implement JWT-based authentication\n"
            "Progress: You have completed the token generation logic and "
            "the login endpoint. You still need to implement the refresh "
            "token flow and the middleware for protected routes."
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": context},
        ])

        comment = response.content
        comment_lower = comment.lower()

        # Should mention completed and remaining work
        mentions_progress = any(
            word in comment_lower
            for word in ["completed", "done", "finished", "implemented"]
        )
        mentions_remaining = any(
            word in comment_lower
            for word in ["remaining", "next", "still", "todo", "to do", "left"]
        )

        assert mentions_progress, "Comment should mention what's been completed"
        assert mentions_remaining, "Comment should mention what's remaining"


@pytest.mark.eval
@pytest.mark.slow
class TestDeveloperResponseQuality:
    """Test developer response quality using LLM-as-judge."""

    async def test_implementation_plan_quality(
        self, real_llm: Any, dev_system_prompt: str, sample_task: dict[str, str]
    ) -> None:
        """LLM judge scores the developer's implementation plan quality."""
        task_text = (
            f"Task: {sample_task['name']}\n"
            f"Description: {sample_task['description']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": dev_system_prompt},
            {"role": "user", "content": f"Work on this task:\n{task_text}"},
        ])

        plan = response.content

        eval_result = await score_implementation_plan(
            task_description=task_text,
            plan=plan,
            llm=real_llm,
        )

        assert eval_result.passed, (
            f"Developer plan did not pass quality check. "
            f"Scores: {eval_result.scores}, "
            f"Average: {eval_result.average_score:.1f}"
        )
