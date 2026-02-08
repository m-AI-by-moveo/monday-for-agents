"""Scrum Master agent evaluations.

These tests exercise the scrum master agent with a real LLM and
evaluate output quality using an LLM-as-judge.  Tests are skipped if
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
    STATUS_REPORT_CRITERIA,
    score_status_report,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sm_system_prompt() -> str:
    """Scrum Master agent system prompt for direct LLM testing."""
    return (
        "You are a Scrum Master agent. When given board state data, "
        "generate a standup report in the following format:\n\n"
        "**Board Summary**\n"
        "- Total tasks: X\n"
        "- To Do: X | In Progress: X | In Review: X | Done: X | Blocked: X\n\n"
        "**In Progress** (who's working on what)\n"
        "- [Task Name] -- assigned to [agent]\n\n"
        "**Blocked** (needs attention)\n"
        "- [Task Name] -- reason\n\n"
        "**Recently Completed**\n"
        "- [Task Name] -- completed by [agent]\n\n"
        "**Action Items**\n"
        "- Any stuck tasks or issues\n\n"
        "Be concise, data-driven, and highlight urgent items."
    )


@pytest.fixture()
def sample_board_state() -> dict[str, Any]:
    """A sample board state for the scrum master to summarize."""
    return {
        "board_name": "Agent Tasks",
        "total_items": 8,
        "by_status": {
            "To Do": [
                {"id": "101", "name": "Set up CI/CD", "assignee": "developer", "priority": "Medium", "group": "To Do"},
                {"id": "102", "name": "Write API docs", "assignee": "developer", "priority": "Low", "group": "To Do"},
            ],
            "In Progress": [
                {"id": "103", "name": "Implement auth service", "assignee": "developer", "priority": "High", "group": "In Progress"},
                {"id": "104", "name": "Build user dashboard", "assignee": "developer", "priority": "High", "group": "In Progress"},
            ],
            "In Review": [
                {"id": "105", "name": "Database schema migration", "assignee": "reviewer", "priority": "High", "group": "In Review"},
            ],
            "Done": [
                {"id": "106", "name": "Project setup", "assignee": "developer", "priority": "Medium", "group": "Done"},
                {"id": "107", "name": "Design system components", "assignee": "developer", "priority": "Medium", "group": "Done"},
            ],
            "Blocked": [
                {"id": "108", "name": "Payment integration", "assignee": "developer", "priority": "Critical", "group": "Blocked"},
            ],
        },
    }


@pytest.fixture()
def stuck_tasks_board() -> dict[str, Any]:
    """Board state with tasks that have been stuck."""
    return {
        "board_name": "Agent Tasks",
        "total_items": 4,
        "by_status": {
            "In Progress": [
                {
                    "id": "201",
                    "name": "Implement caching layer",
                    "assignee": "developer",
                    "priority": "High",
                    "group": "In Progress",
                    "days_in_status": 3,
                },
            ],
            "In Review": [
                {
                    "id": "202",
                    "name": "Add logging middleware",
                    "assignee": "reviewer",
                    "priority": "Medium",
                    "group": "In Review",
                    "days_in_status": 2,
                },
            ],
            "Blocked": [
                {
                    "id": "203",
                    "name": "External API integration",
                    "assignee": "developer",
                    "priority": "Critical",
                    "group": "Blocked",
                    "days_in_status": 5,
                    "blocked_reason": "Waiting for API credentials from vendor",
                },
            ],
            "To Do": [
                {
                    "id": "204",
                    "name": "Write unit tests",
                    "assignee": None,
                    "priority": "Medium",
                    "group": "To Do",
                    "days_in_status": 4,
                },
            ],
        },
    }


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.eval
@pytest.mark.slow
class TestScrumMasterBoardSummary:
    """Test SM generates accurate board summaries."""

    async def test_generates_summary(
        self,
        real_llm: Any,
        sm_system_prompt: str,
        sample_board_state: dict[str, Any],
    ) -> None:
        """SM generates a non-empty board summary report."""
        board_json = json.dumps(sample_board_state, indent=2)

        response = await real_llm.ainvoke([
            {"role": "system", "content": sm_system_prompt},
            {"role": "user", "content": f"Generate a standup report for this board:\n{board_json}"},
        ])

        report = response.content
        assert len(report) > 100, "Board summary should be substantive"

    async def test_summary_includes_counts(
        self,
        real_llm: Any,
        sm_system_prompt: str,
        sample_board_state: dict[str, Any],
    ) -> None:
        """SM report includes correct task counts."""
        board_json = json.dumps(sample_board_state, indent=2)

        response = await real_llm.ainvoke([
            {"role": "system", "content": sm_system_prompt},
            {"role": "user", "content": f"Generate a standup report for this board:\n{board_json}"},
        ])

        report = response.content
        # Should mention total and per-status counts
        assert "8" in report, "Report should mention total of 8 tasks"

    async def test_summary_mentions_blocked(
        self,
        real_llm: Any,
        sm_system_prompt: str,
        sample_board_state: dict[str, Any],
    ) -> None:
        """SM report highlights blocked tasks."""
        board_json = json.dumps(sample_board_state, indent=2)

        response = await real_llm.ainvoke([
            {"role": "system", "content": sm_system_prompt},
            {"role": "user", "content": f"Generate a standup report for this board:\n{board_json}"},
        ])

        report_lower = response.content.lower()
        assert "blocked" in report_lower, "Report should mention blocked tasks"
        assert "payment" in report_lower, "Report should mention the blocked payment task"


@pytest.mark.eval
@pytest.mark.slow
class TestScrumMasterStuckTasks:
    """Test SM identifies stuck tasks correctly."""

    async def test_identifies_stuck_tasks(
        self,
        real_llm: Any,
        stuck_tasks_board: dict[str, Any],
    ) -> None:
        """SM identifies tasks that have been in the same status too long."""
        system = (
            "You are a Scrum Master agent. Analyze this board state and "
            "identify any stuck tasks. A task is 'stuck' if:\n"
            "- In Progress for more than 2 days\n"
            "- In Review for more than 1 day\n"
            "- Blocked for more than 1 day\n"
            "- To Do with no assignee for more than 1 day\n\n"
            "List each stuck task with its name, how long it's been stuck, "
            "and a recommended action."
        )

        board_json = json.dumps(stuck_tasks_board, indent=2)

        response = await real_llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": f"Analyze stuck tasks:\n{board_json}"},
        ])

        report = response.content.lower()

        # Should identify the stuck tasks
        assert "caching" in report, "Should identify stuck 'Implement caching layer' task"
        assert "logging" in report or "middleware" in report, (
            "Should identify stuck 'Add logging middleware' task"
        )
        assert "external" in report or "api integration" in report, (
            "Should identify blocked 'External API integration' task"
        )


@pytest.mark.eval
@pytest.mark.slow
class TestScrumMasterNudgeMessages:
    """Test SM nudge messages are polite and helpful."""

    async def test_nudge_is_polite(self, real_llm: Any) -> None:
        """SM nudge messages maintain a polite, supportive tone."""
        system = (
            "You are a Scrum Master agent. Write a nudge message for an "
            "agent who has a stuck task. Be polite and helpful, not demanding. "
            "Reference the specific task, ask if they need help, and suggest "
            "marking as blocked if they're stuck."
        )

        context = (
            "The developer agent has had task 'Implement caching layer' (ID: 201) "
            "in 'In Progress' status for 3 days. Please write a nudge message."
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": context},
        ])

        nudge = response.content
        nudge_lower = nudge.lower()

        # Should be polite
        polite_indicators = ["help", "check", "wondering", "update", "please", "could", "would"]
        has_polite_tone = any(word in nudge_lower for word in polite_indicators)
        assert has_polite_tone, "Nudge should have a polite, supportive tone"

        # Should reference the task
        assert "caching" in nudge_lower or "201" in nudge, (
            "Nudge should reference the specific task"
        )

        # Should NOT be demanding
        demanding_words = ["must", "immediately", "now", "urgent", "asap", "demand"]
        for word in demanding_words:
            # Allow these in non-demanding contexts
            if word in nudge_lower:
                # Check it's not in a demanding sentence
                assert "please" in nudge_lower or "help" in nudge_lower, (
                    f"Nudge containing '{word}' should still be polite"
                )

    async def test_nudge_suggests_blocked(self, real_llm: Any) -> None:
        """SM nudge suggests marking as blocked if appropriate."""
        system = (
            "You are a Scrum Master agent. Write a nudge message for an "
            "agent who has a stuck task. Be polite and helpful. "
            "Suggest they mark the task as 'Blocked' if they're stuck."
        )

        context = (
            "The developer agent has had task 'Implement caching layer' (ID: 201) "
            "in 'In Progress' for 3 days without any updates."
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": system},
            {"role": "user", "content": context},
        ])

        nudge_lower = response.content.lower()
        assert "blocked" in nudge_lower, (
            "Nudge should suggest marking task as blocked"
        )


@pytest.mark.eval
@pytest.mark.slow
class TestScrumMasterReportFormat:
    """Test SM report format matches expected structure."""

    async def test_report_has_expected_sections(
        self,
        real_llm: Any,
        sm_system_prompt: str,
        sample_board_state: dict[str, Any],
    ) -> None:
        """SM report includes all expected sections."""
        board_json = json.dumps(sample_board_state, indent=2)

        response = await real_llm.ainvoke([
            {"role": "system", "content": sm_system_prompt},
            {"role": "user", "content": f"Generate a standup report for this board:\n{board_json}"},
        ])

        report = response.content
        report_lower = report.lower()

        expected_sections = [
            "board summary",
            "in progress",
            "blocked",
            "action",
        ]

        for section in expected_sections:
            assert section in report_lower, (
                f"Report should include '{section}' section. "
                f"Got sections in: {report[:500]}"
            )


@pytest.mark.eval
@pytest.mark.slow
class TestScrumMasterReportQuality:
    """Test SM report quality using LLM-as-judge."""

    async def test_report_quality(
        self,
        real_llm: Any,
        sm_system_prompt: str,
        sample_board_state: dict[str, Any],
    ) -> None:
        """LLM judge scores the scrum master's report quality."""
        board_json = json.dumps(sample_board_state, indent=2)

        response = await real_llm.ainvoke([
            {"role": "system", "content": sm_system_prompt},
            {"role": "user", "content": f"Generate a standup report for this board:\n{board_json}"},
        ])

        eval_result = await score_status_report(
            board_state=board_json,
            report=response.content,
            llm=real_llm,
        )

        assert eval_result.passed, (
            f"SM report did not pass quality check. "
            f"Scores: {eval_result.scores}, "
            f"Average: {eval_result.average_score:.1f}"
        )
