import json
import logging
import uuid
from typing import Sequence

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.training import (
    SkillDimension,
    category_name,
    dimension_name,
)
from src.domains.evaluations.crud import (
    CRUDDimensionScore,
    CRUDEvaluationResult,
    CRUDRedFlag,
)
from src.domains.evaluations.models import DimensionScore, EvaluationResult, RedFlag
from src.domains.evaluations.prompts import (
    EVALUATION_SYSTEM_PROMPT,
    build_evaluation_user_prompt,
)
from src.domains.scenarios.models import Scenario
from src.domains.simulations.models import Message, MessageRole, Session, SessionStatus
from src.infrastructure.llm.base import LLMProvider

logger = logging.getLogger("usus.evaluations")


class EvaluationFailedError(Exception):
    """The LLM did not return a usable evaluation (after retrying)."""


class _LLMDimension(BaseModel):
    score: int = Field(ge=0, le=100)
    rationale: str


class _LLMRedFlag(BaseModel):
    reason: str
    description: str


class _LLMEvaluation(BaseModel):
    summary: str
    dimensions: dict[SkillDimension, _LLMDimension]
    strengths: list[str] = []
    improvements: list[str] = []
    missed_opportunities: list[str] = []
    recommendations: list[str] = []
    red_flags: list[_LLMRedFlag] = []


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
        Score a finished session on the 7 dimensions and save the feedback.

        Raises EvaluationFailedError if the LLM output is unusable twice; nothing
        is saved in that case, so the evaluation can simply be retried.
        """
        scenario = await db.get(Scenario, session.scenario_id)

        if not any(m.role == MessageRole.USER for m in messages):
            evaluation = _empty_evaluation()
        else:
            evaluation = await self._ask_llm(scenario, messages)

        overall = round(
            sum(d.score for d in evaluation.dimensions.values())
            / len(evaluation.dimensions)
        )

        # Save the evaluation, its 7 dimensions, red flags and the session's
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
        )
        result.dimension_scores = [
            DimensionScore(
                dimension_key=dimension.value,
                dimension_name=dimension_name(dimension),
                score=evaluation.dimensions[dimension].score,
                rationale=evaluation.dimensions[dimension].rationale,
            )
            for dimension in SkillDimension  # fixed display order
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
        self, scenario: Scenario | None, messages: Sequence[Message]
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
                    _scenario_context(scenario), transcript
                ),
            }
        ]

        last_error: Exception | None = None
        for _attempt in range(2):
            response_text = await self.llm_provider.generate_response(
                system_prompt=EVALUATION_SYSTEM_PROMPT,
                messages=llm_messages,
                temperature=0.0,
                max_tokens=2000,
                json_mode=True,
            )
            try:
                evaluation = _LLMEvaluation.model_validate(_extract_json(response_text))
                missing = set(SkillDimension) - set(evaluation.dimensions)
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


def _empty_evaluation() -> _LLMEvaluation:
    """Deterministic result when the trainee never replied (no LLM call)."""
    reason = "The trainee did not respond to the customer, so nothing could be scored."
    return _LLMEvaluation(
        summary="The session ended before the trainee responded to the customer.",
        dimensions={
            d: _LLMDimension(score=0, rationale=reason) for d in SkillDimension
        },
        improvements=["Respond to the customer before ending the session."],
        recommendations=[
            "Start by greeting the customer and acknowledging their problem."
        ],
    )
