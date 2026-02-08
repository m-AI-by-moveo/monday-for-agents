"""Evaluation utilities for LLM-as-judge scoring.

Provides the ``EvalResult`` dataclass, a general-purpose ``LLMJudge``
class, and domain-specific scoring functions for each agent role.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring criteria constants
# ---------------------------------------------------------------------------

TASK_BREAKDOWN_CRITERIA = """\
Evaluate whether the Product Owner agent correctly broke down a feature
request into actionable tasks.  Score each dimension from 0 to 10.

Dimensions:
- completeness: Are all aspects of the feature covered by at least one task?
- granularity: Are tasks sized appropriately (not too big, not too small)?
- clarity: Does each task have a clear, descriptive name?
- prioritisation: Are priorities assigned sensibly (e.g. core auth = High)?
- typing: Are task types (Feature, Bug, Chore, Spike) correct?
- assignment: Are tasks assigned to the right agent (developer vs reviewer)?

Return ONLY a JSON object with the keys above and integer scores 0-10.
"""

IMPLEMENTATION_PLAN_CRITERIA = """\
Evaluate the developer agent's implementation plan for a given task.
Score each dimension from 0 to 10.

Dimensions:
- technical_accuracy: Is the approach technically sound?
- completeness: Does the plan address all requirements in the task?
- structure: Is the plan well-organized and easy to follow?
- feasibility: Is the plan realistic and implementable?
- detail: Does it include enough detail to guide implementation?

Return ONLY a JSON object with the keys above and integer scores 0-10.
"""

REVIEW_FEEDBACK_CRITERIA = """\
Evaluate the reviewer agent's feedback on submitted work.
Score each dimension from 0 to 10.

Dimensions:
- thoroughness: Does the review address all aspects of the work?
- constructiveness: Is the feedback helpful and actionable?
- specificity: Does the review reference specific issues, not generalities?
- tone: Is the tone professional, supportive, and not harsh?
- accuracy: Are the reviewer's observations technically correct?

Return ONLY a JSON object with the keys above and integer scores 0-10.
"""

STATUS_REPORT_CRITERIA = """\
Evaluate the scrum master agent's board status report.
Score each dimension from 0 to 10.

Dimensions:
- accuracy: Does the report correctly reflect the board state?
- format: Does it follow the expected standup report structure?
- completeness: Are all status categories represented?
- actionability: Are action items clear and specific?
- conciseness: Is the report concise without losing important details?

Return ONLY a JSON object with the keys above and integer scores 0-10.
"""


# ---------------------------------------------------------------------------
# EvalResult dataclass
# ---------------------------------------------------------------------------


@dataclass
class EvalResult:
    """Result of an evaluation run.

    Attributes:
        input: The input that was evaluated (feature request, task, etc.).
        output: The agent's output that was scored.
        scores: Mapping of dimension names to integer scores (0-10).
        passed: Whether the overall evaluation is considered passing.
        explanation: Optional free-text explanation from the judge.
    """

    input: str
    output: str
    scores: dict[str, int] = field(default_factory=dict)
    passed: bool = False
    explanation: str = ""

    @property
    def average_score(self) -> float:
        """Return the mean across all scored dimensions."""
        if not self.scores:
            return 0.0
        return sum(self.scores.values()) / len(self.scores)


# ---------------------------------------------------------------------------
# LLMJudge
# ---------------------------------------------------------------------------


class LLMJudge:
    """Uses a chat LLM to evaluate agent outputs against criteria.

    The judge sends the criteria, input, and output to the LLM and
    parses the JSON scores from the response.

    Args:
        llm: A LangChain-compatible chat model instance.
        passing_threshold: Minimum average score to consider ``passed``.
    """

    def __init__(self, llm: Any, passing_threshold: float = 6.0) -> None:
        self.llm = llm
        self.passing_threshold = passing_threshold

    async def evaluate(
        self,
        criteria: str,
        input_text: str,
        output_text: str,
    ) -> EvalResult:
        """Score *output_text* against *criteria* given *input_text*.

        Args:
            criteria: The scoring rubric (one of the *_CRITERIA constants).
            input_text: The original input (feature request, task, etc.).
            output_text: The agent's output to evaluate.

        Returns:
            An :class:`EvalResult` with parsed scores and pass/fail.
        """
        prompt = (
            f"You are an evaluation judge.  Score the following agent output "
            f"against the criteria below.\n\n"
            f"## Criteria\n{criteria}\n\n"
            f"## Input\n{input_text}\n\n"
            f"## Agent Output\n{output_text}\n\n"
            f"Respond with ONLY the JSON scores object, nothing else."
        )

        try:
            response = await self.llm.ainvoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)

            # Extract JSON from the response (handle markdown code blocks)
            json_text = content.strip()
            if json_text.startswith("```"):
                # Remove markdown code fences
                lines = json_text.split("\n")
                json_text = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )

            scores = json.loads(json_text)

            if not isinstance(scores, dict):
                raise ValueError(f"Expected dict, got {type(scores)}")

            # Ensure all values are ints
            scores = {k: int(v) for k, v in scores.items()}

        except Exception:
            logger.exception("Failed to parse LLM judge response")
            return EvalResult(
                input=input_text,
                output=output_text,
                scores={},
                passed=False,
                explanation=f"Failed to parse judge response: {content if 'content' in dir() else 'no response'}",
            )

        avg = sum(scores.values()) / len(scores) if scores else 0.0
        passed = avg >= self.passing_threshold

        return EvalResult(
            input=input_text,
            output=output_text,
            scores=scores,
            passed=passed,
            explanation=f"Average score: {avg:.1f} (threshold: {self.passing_threshold})",
        )


# ---------------------------------------------------------------------------
# Domain-specific scoring functions
# ---------------------------------------------------------------------------


async def score_task_breakdown(
    feature_request: str,
    created_tasks: list[dict[str, Any]],
    llm: Any,
) -> EvalResult:
    """Judge whether the PO correctly broke down a feature into tasks.

    Args:
        feature_request: The original feature request text.
        created_tasks: List of task dicts created by the PO agent.
        llm: The LLM to use as judge.

    Returns:
        An :class:`EvalResult` with breakdown quality scores.
    """
    tasks_text = json.dumps(created_tasks, indent=2)
    judge = LLMJudge(llm)
    return await judge.evaluate(
        criteria=TASK_BREAKDOWN_CRITERIA,
        input_text=feature_request,
        output_text=tasks_text,
    )


async def score_implementation_plan(
    task_description: str,
    plan: str,
    llm: Any,
) -> EvalResult:
    """Judge the quality of a developer's implementation plan.

    Args:
        task_description: The task the developer was asked to implement.
        plan: The developer's plan/approach text.
        llm: The LLM to use as judge.

    Returns:
        An :class:`EvalResult` with plan quality scores.
    """
    judge = LLMJudge(llm)
    return await judge.evaluate(
        criteria=IMPLEMENTATION_PLAN_CRITERIA,
        input_text=task_description,
        output_text=plan,
    )


async def score_review_feedback(
    task_with_work: str,
    feedback: str,
    llm: Any,
) -> EvalResult:
    """Judge the quality of reviewer feedback.

    Args:
        task_with_work: Description of the task and the developer's work.
        feedback: The reviewer's feedback text.
        llm: The LLM to use as judge.

    Returns:
        An :class:`EvalResult` with feedback quality scores.
    """
    judge = LLMJudge(llm)
    return await judge.evaluate(
        criteria=REVIEW_FEEDBACK_CRITERIA,
        input_text=task_with_work,
        output_text=feedback,
    )


async def score_status_report(
    board_state: str,
    report: str,
    llm: Any,
) -> EvalResult:
    """Judge the quality of a scrum master's status report.

    Args:
        board_state: JSON or text description of the board state.
        report: The scrum master's generated report.
        llm: The LLM to use as judge.

    Returns:
        An :class:`EvalResult` with report quality scores.
    """
    judge = LLMJudge(llm)
    return await judge.evaluate(
        criteria=STATUS_REPORT_CRITERIA,
        input_text=board_state,
        output_text=report,
    )
