import json
import logging
import uuid
from typing import Sequence

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.training import category_name, dimension_name
from src.domains.evaluations.crud import (
    CRUDDimensionScore,
    CRUDEvaluationResult,
    CRUDRedFlag,
)
from src.domains.evaluations.models import DimensionScore, EvaluationResult, RedFlag
from src.domains.evaluations.prompts import (
    build_evaluation_system_prompt,
    build_evaluation_user_prompt,
)
from src.domains.metrics import service as metrics_service
from src.domains.metrics.service import MetricSpec
from src.domains.scenarios.models import Scenario
from src.domains.simulations.models import Message, MessageRole, Session, SessionStatus
from src.infrastructure.llm.base import LLMProvider

logger = logging.getLogger("usus.evaluations")


# Below this, a session is too short to assess and scores 0 without asking
# the LLM (e.g. a trainee who only says "hi" and ends the session).
MIN_TRAINEE_TURNS = 2
MIN_TRAINEE_WORDS = 15


class EvaluationFailedError(Exception):
    """The LLM did not return a usable evaluation (after retrying)."""


class _LLMDimension(BaseModel):
    score: int = Field(ge=0, le=100)
    rationale: str


class _LLMRedFlag(BaseModel):
    reason: str
    description: str


class _LLMStaffView(BaseModel):
    """The same feedback written about the trainee, for their managers."""

    summary: str
    rationales: dict[str, str] = {}
    strengths: list[str] = []
    improvements: list[str] = []
    missed_opportunities: list[str] = []
    recommendations: list[str] = []


class _LLMEvaluation(BaseModel):
    # Written to the trainee ("You ...").
    summary: str
    dimensions: dict[str, _LLMDimension]
    strengths: list[str] = []
    improvements: list[str] = []
    missed_opportunities: list[str] = []
    recommendations: list[str] = []
    red_flags: list[_LLMRedFlag] = []
    # Written about the trainee ("The trainee ..."); None if the model left it
    # out, in which case staff see the trainee's wording.
    staff_view: _LLMStaffView | None = None


class EvaluationService:
    def __init__(
        self,
        eval_result_repo: CRUDEvaluationResult,
        dimension_score_repo: CRUDDimensionScore,
        red_flag_repo: CRUDRedFlag,
        llm_provider: LLMProvider,
    ):
        self.eval_result_repo = eval_result_repo
        self.dimension_score_repo = dimension_score_repo
        self.red_flag_repo = red_flag_repo
        self.llm_provider = llm_provider

    async def evaluate_session(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        session: Session,
        messages: Sequence[Message],
    ) -> EvaluationResult:
        """
        Score a finished session on its scenario's metrics and save the feedback.

        Raises EvaluationFailedError if the LLM output is unusable twice; nothing
        is saved in that case, so the evaluation can simply be retried.
        """
        scenario = await db.get(Scenario, session.scenario_id)
        metrics = await metrics_service.for_scenario(db, tenant_id, scenario)
        keys = [m.key for m in metrics]

        trainee_turns, trainee_words = _trainee_effort(messages)
        if trainee_turns == 0:
            evaluation = _empty_evaluation(keys)
        elif trainee_turns < MIN_TRAINEE_TURNS or trainee_words < MIN_TRAINEE_WORDS:
            evaluation = _too_short_evaluation(keys)
        else:
            evaluation = await self._ask_llm(scenario, metrics, messages)

        overall = round(sum(evaluation.dimensions[k].score for k in keys) / len(keys))

        # Save the evaluation, its metric scores, red flags and the session's
        # EVALUATED status in ONE transaction: a client polling for the result
        # sees either nothing or the complete evaluation, never a partial one.
        result = EvaluationResult(
            tenant_id=tenant_id,
            session_id=session.id,
            overall_score=overall,
            summary=evaluation.summary,
            strengths=evaluation.strengths,
            improvements=evaluation.improvements,
            missed_opportunities=evaluation.missed_opportunities,
            recommendations=evaluation.recommendations,
            staff_feedback=_staff_feedback(evaluation),
        )
        result.dimension_scores = [
            DimensionScore(
                dimension_key=metric.key,
                dimension_name=metric.name,
                score=evaluation.dimensions[metric.key].score,
                rationale=evaluation.dimensions[metric.key].rationale,
            )
            for metric in metrics  # fixed display order
        ]
        result.red_flags = [
            RedFlag(reason=flag.reason[:255], description=flag.description)
            for flag in evaluation.red_flags
        ]
        session.status = SessionStatus.EVALUATED

        db.add_all([result, session])
        await db.commit()
        await db.refresh(result)

        return result

    async def _ask_llm(
        self,
        scenario: Scenario | None,
        metrics: Sequence[MetricSpec],
        messages: Sequence[Message],
    ) -> _LLMEvaluation:
        transcript = "\n".join(
            f"{'Trainee' if m.role == MessageRole.USER else 'Customer'}: {m.content}"
            for m in messages
            if m.role != MessageRole.SYSTEM
        )
        llm_messages = [
            {
                "role": "user",
                "content": build_evaluation_user_prompt(
                    _scenario_context(scenario), transcript, *_trainee_effort(messages)
                ),
            }
        ]

        last_error: Exception | None = None
        for _attempt in range(2):
            response_text = await self.llm_provider.generate_response(
                system_prompt=build_evaluation_system_prompt(metrics),
                messages=llm_messages,
                temperature=0.0,
                max_tokens=2000,
                json_mode=True,
            )
            try:
                evaluation = _LLMEvaluation.model_validate(_extract_json(response_text))
                missing = {m.key for m in metrics} - set(evaluation.dimensions)
                if missing:
                    raise ValueError(f"missing dimensions: {sorted(missing)}")
                return evaluation
            except (ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning("Unusable evaluation from LLM, retrying: %s", exc)

        raise EvaluationFailedError(str(last_error))


def _extract_json(response_text: str) -> dict:
    """
    Extract and parse a JSON object from the LLM response.

    Handles:
    - Pure JSON
    - JSON surrounded by whitespace
    - Markdown ```json fences
    - Extra text before/after the JSON object
    """
    if not isinstance(response_text, str):
        raise ValueError("The evaluation model returned an invalid response.")

    text = response_text.strip()
    if not text:
        raise ValueError("The evaluation model returned an empty response.")

    # Remove markdown code fences if the model ignored the instruction not to
    # use them.
    if text.startswith("```"):
        lines = text.splitlines()[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    # First attempt: the entire response is JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Second attempt: locate the first JSON object, e.g.
    # "Here is the evaluation: { ... }" or "{ ... } End of evaluation."
    first_brace = text.find("{")
    if first_brace == -1:
        raise ValueError("The evaluation model did not return a JSON object.")
    try:
        parsed, _ = json.JSONDecoder().raw_decode(text[first_brace:])
    except json.JSONDecodeError as exc:
        raise ValueError("The evaluation model returned invalid JSON.") from exc
    if not isinstance(parsed, dict):
        raise ValueError("The evaluation model returned an invalid JSON response.")
    return parsed


def _scenario_context(scenario: Scenario | None) -> str:
    if scenario is None:
        return "(unknown scenario)"
    parts = [
        ("Scenario", f"{scenario.name} — {scenario.description}"),
        ("Category", category_name(scenario.category)),
        ("Difficulty", scenario.difficulty.value),
        (
            "Skills this scenario focuses on",
            ", ".join(dimension_name(s) for s in scenario.skills or []),
        ),
        ("What happened", scenario.situation),
        ("What the customer wants", scenario.customer_goal),
        ("Trainee's objective", scenario.trainee_objective),
        ("What success looks like", scenario.success_criteria),
    ]
    lines = [f"{label}: {value}" for label, value in parts if value]
    for info in scenario.important_information or []:
        lines.append(
            f"Policy/fact the trainee could use — {info['label']}: {info['content']}"
        )
    return "\n".join(lines)


def _staff_feedback(evaluation: _LLMEvaluation) -> dict | None:
    """The staff wording as stored in EvaluationResult.staff_feedback."""
    view = evaluation.staff_view
    if view is None:
        logger.warning("Evaluation has no staff_view; staff will see trainee text")
        return None
    return {
        "summary": view.summary,
        "rationales": dict(view.rationales),
        "strengths": view.strengths,
        "improvements": view.improvements,
        "missed_opportunities": view.missed_opportunities,
        "recommendations": view.recommendations,
    }


def _trainee_effort(messages: Sequence[Message]) -> tuple[int, int]:
    """How many messages and words the trainee sent."""
    said = [m.content for m in messages if m.role == MessageRole.USER]
    return len(said), sum(len(text.split()) for text in said)


def _too_short_evaluation(keys: list[str]) -> _LLMEvaluation:
    """Deterministic result when the trainee barely engaged (no LLM call)."""
    reason = "The conversation was too short to show this skill, so it scores 0."
    staff_reason = "The conversation was too short for the trainee to show this skill."
    return _LLMEvaluation(
        summary=(
            "The session ended before you dealt with the customer's problem, "
            "so there was nothing to assess."
        ),
        dimensions={k: _LLMDimension(score=0, rationale=reason) for k in keys},
        improvements=[
            "Stay in the conversation until the customer's problem is handled."
        ],
        recommendations=[
            "Greet the customer, find out what they need, and work towards a "
            "solution before ending the session."
        ],
        staff_view=_LLMStaffView(
            summary=(
                "The trainee ended the session before dealing with the "
                "customer's problem, so there was nothing to assess."
            ),
            rationales={k: staff_reason for k in keys},
            improvements=[
                "The trainee should stay in the conversation until the "
                "customer's problem is handled."
            ],
            recommendations=[
                "The trainee should find out what the customer needs and work "
                "towards a solution before ending the session."
            ],
        ),
    )


def _empty_evaluation(keys: list[str]) -> _LLMEvaluation:
    """Deterministic result when the trainee never replied (no LLM call)."""
    reason = "You did not respond to the customer, so nothing could be scored."
    staff_reason = (
        "The trainee did not respond to the customer, so nothing could be scored."
    )
    return _LLMEvaluation(
        summary="The session ended before you responded to the customer.",
        dimensions={k: _LLMDimension(score=0, rationale=reason) for k in keys},
        improvements=["Respond to the customer before ending the session."],
        recommendations=[
            "Start by greeting the customer and acknowledging their problem."
        ],
        staff_view=_LLMStaffView(
            summary="The session ended before the trainee responded to the customer.",
            rationales={k: staff_reason for k in keys},
            improvements=[
                "The trainee should respond to the customer before ending the session."
            ],
            recommendations=[
                "The trainee should start by greeting the customer and "
                "acknowledging their problem."
            ],
        ),
    )
