"""Reviewer agent evaluations.

These tests exercise the reviewer agent with a real LLM and evaluate
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
    REVIEW_FEEDBACK_CRITERIA,
    score_review_feedback,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def reviewer_system_prompt() -> str:
    """Reviewer agent system prompt for direct LLM testing."""
    return (
        "You are a Reviewer agent. When given a task and the developer's "
        "implementation output, review the work and provide feedback.\n\n"
        "Your review should:\n"
        "1. Assess completeness against the original requirements\n"
        "2. Evaluate technical soundness of the approach\n"
        "3. Note any issues or improvements needed\n"
        "4. Provide a clear verdict: APPROVED or CHANGES_NEEDED\n"
        "5. Be constructive and specific\n\n"
        "Start your response with 'VERDICT: APPROVED' or "
        "'VERDICT: CHANGES_NEEDED', then provide detailed feedback."
    )


@pytest.fixture()
def good_work_submission() -> dict[str, str]:
    """A high-quality developer submission that should be approved."""
    return {
        "task": "Implement JWT-based authentication for the API",
        "requirements": (
            "Issue access and refresh tokens on login, validate tokens "
            "on protected endpoints, handle token expiry and refresh."
        ),
        "developer_output": (
            "## Implementation Plan\n\n"
            "### 1. Token Generation (completed)\n"
            "- Using `jsonwebtoken` library for JWT creation and verification\n"
            "- Access tokens: 15-minute expiry, signed with RS256\n"
            "- Refresh tokens: 7-day expiry, stored in Redis with user ID index\n\n"
            "### 2. Login Endpoint (completed)\n"
            "- POST /api/auth/login accepts email + password\n"
            "- Validates credentials against bcrypt-hashed passwords\n"
            "- Returns { accessToken, refreshToken, expiresIn }\n\n"
            "### 3. Token Validation Middleware (completed)\n"
            "- Extracts Bearer token from Authorization header\n"
            "- Verifies signature and expiry\n"
            "- Attaches decoded user to request context\n\n"
            "### 4. Refresh Flow (completed)\n"
            "- POST /api/auth/refresh accepts refresh token\n"
            "- Validates against Redis store, issues new access token\n"
            "- Implements token rotation (old refresh token invalidated)\n\n"
            "### 5. Testing\n"
            "- Unit tests for token generation and validation\n"
            "- Integration tests for login and refresh flows\n"
            "- Edge cases: expired tokens, invalid signatures, revoked tokens"
        ),
    }


@pytest.fixture()
def poor_work_submission() -> dict[str, str]:
    """A low-quality submission that should request changes."""
    return {
        "task": "Implement JWT-based authentication for the API",
        "requirements": (
            "Issue access and refresh tokens on login, validate tokens "
            "on protected endpoints, handle token expiry and refresh."
        ),
        "developer_output": (
            "I'll use JWT for auth. Here's the basic idea:\n"
            "- Login endpoint that checks credentials\n"
            "- Return a token\n"
            "- Check the token on other routes\n\n"
            "Should be straightforward."
        ),
    }


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.eval
@pytest.mark.slow
class TestReviewerApproval:
    """Test reviewer correctly approves good work."""

    async def test_approves_good_work(
        self,
        real_llm: Any,
        reviewer_system_prompt: str,
        good_work_submission: dict[str, str],
    ) -> None:
        """Reviewer approves a thorough, well-structured implementation."""
        review_input = (
            f"Task: {good_work_submission['task']}\n"
            f"Requirements: {good_work_submission['requirements']}\n\n"
            f"Developer's Work:\n{good_work_submission['developer_output']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": reviewer_system_prompt},
            {"role": "user", "content": f"Review this work:\n{review_input}"},
        ])

        content = response.content.upper()
        # Good work should be approved
        assert "APPROVED" in content, (
            f"Reviewer should approve good work. Got: {response.content[:200]}"
        )


@pytest.mark.eval
@pytest.mark.slow
class TestReviewerChangesRequested:
    """Test reviewer identifies issues and requests changes."""

    async def test_requests_changes_for_poor_work(
        self,
        real_llm: Any,
        reviewer_system_prompt: str,
        poor_work_submission: dict[str, str],
    ) -> None:
        """Reviewer requests changes for an incomplete, shallow submission."""
        review_input = (
            f"Task: {poor_work_submission['task']}\n"
            f"Requirements: {poor_work_submission['requirements']}\n\n"
            f"Developer's Work:\n{poor_work_submission['developer_output']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": reviewer_system_prompt},
            {"role": "user", "content": f"Review this work:\n{review_input}"},
        ])

        content = response.content.upper()
        # Poor work should get changes requested
        assert "CHANGES" in content or "CHANGE" in content, (
            f"Reviewer should request changes for poor work. Got: {response.content[:200]}"
        )


@pytest.mark.eval
@pytest.mark.slow
class TestReviewerFeedbackQuality:
    """Test reviewer feedback is constructive and specific."""

    async def test_feedback_is_constructive(
        self,
        real_llm: Any,
        reviewer_system_prompt: str,
        poor_work_submission: dict[str, str],
    ) -> None:
        """Reviewer feedback contains specific, actionable suggestions."""
        review_input = (
            f"Task: {poor_work_submission['task']}\n"
            f"Requirements: {poor_work_submission['requirements']}\n\n"
            f"Developer's Work:\n{poor_work_submission['developer_output']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": reviewer_system_prompt},
            {"role": "user", "content": f"Review this work:\n{review_input}"},
        ])

        feedback = response.content
        feedback_lower = feedback.lower()

        # Feedback should be substantive
        assert len(feedback) > 100, "Feedback should be detailed, not superficial"

        # Should mention specific missing elements
        mentions_specifics = any(
            word in feedback_lower
            for word in [
                "refresh token",
                "token expir",
                "middleware",
                "testing",
                "validation",
                "detail",
                "missing",
                "incomplete",
            ]
        )
        assert mentions_specifics, (
            "Feedback should mention specific issues (e.g. missing refresh "
            f"token handling, testing). Got: {feedback[:300]}"
        )

    async def test_feedback_is_not_harsh(
        self,
        real_llm: Any,
        reviewer_system_prompt: str,
        poor_work_submission: dict[str, str],
    ) -> None:
        """Reviewer feedback maintains a professional, supportive tone."""
        review_input = (
            f"Task: {poor_work_submission['task']}\n"
            f"Requirements: {poor_work_submission['requirements']}\n\n"
            f"Developer's Work:\n{poor_work_submission['developer_output']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": reviewer_system_prompt},
            {"role": "user", "content": f"Review this work:\n{review_input}"},
        ])

        feedback_lower = response.content.lower()

        # Should not contain unnecessarily harsh language
        harsh_words = ["terrible", "awful", "incompetent", "lazy", "unacceptable"]
        for word in harsh_words:
            assert word not in feedback_lower, (
                f"Feedback should not contain harsh language like '{word}'"
            )


@pytest.mark.eval
@pytest.mark.slow
class TestReviewerResponseQuality:
    """Test reviewer response quality using LLM-as-judge."""

    async def test_review_quality_good_work(
        self,
        real_llm: Any,
        reviewer_system_prompt: str,
        good_work_submission: dict[str, str],
    ) -> None:
        """LLM judge scores the reviewer's feedback quality on good work."""
        review_input = (
            f"Task: {good_work_submission['task']}\n"
            f"Requirements: {good_work_submission['requirements']}\n\n"
            f"Developer's Work:\n{good_work_submission['developer_output']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": reviewer_system_prompt},
            {"role": "user", "content": f"Review this work:\n{review_input}"},
        ])

        eval_result = await score_review_feedback(
            task_with_work=review_input,
            feedback=response.content,
            llm=real_llm,
        )

        assert eval_result.passed, (
            f"Reviewer feedback did not pass quality check. "
            f"Scores: {eval_result.scores}, "
            f"Average: {eval_result.average_score:.1f}"
        )

    async def test_review_quality_poor_work(
        self,
        real_llm: Any,
        reviewer_system_prompt: str,
        poor_work_submission: dict[str, str],
    ) -> None:
        """LLM judge scores the reviewer's feedback quality on poor work."""
        review_input = (
            f"Task: {poor_work_submission['task']}\n"
            f"Requirements: {poor_work_submission['requirements']}\n\n"
            f"Developer's Work:\n{poor_work_submission['developer_output']}"
        )

        response = await real_llm.ainvoke([
            {"role": "system", "content": reviewer_system_prompt},
            {"role": "user", "content": f"Review this work:\n{review_input}"},
        ])

        eval_result = await score_review_feedback(
            task_with_work=review_input,
            feedback=response.content,
            llm=real_llm,
        )

        assert eval_result.passed, (
            f"Reviewer feedback on poor work did not pass quality check. "
            f"Scores: {eval_result.scores}, "
            f"Average: {eval_result.average_score:.1f}"
        )
