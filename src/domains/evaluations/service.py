import json
import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.llm.base import LLMProvider

from src.domains.simulations.models import (
    Session,
    Message,
)

from src.domains.evaluations.models import EvaluationResult

from src.domains.evaluations.crud import (
    CRUDEvaluationResult,
    CRUDDimensionScore,
    CRUDRedFlag,
)

from src.domains.evaluations.schemas import (
    EvaluationResultCreate,
    DimensionScoreCreate,
    RedFlagCreate,
)


EVALUATION_DIMENSIONS = (
    "Empathy",
    "Problem Solving",
    "Product Knowledge",
    "Communication",
    "Efficiency",
    "Professionalism",
    "De-escalation",
)


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

    # ================================================================
    # JSON HELPERS
    # ================================================================

    @staticmethod
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
            raise ValueError(
                "The evaluation model returned an invalid response."
            )

        text = response_text.strip()

        if not text:
            raise ValueError(
                "The evaluation model returned an empty response."
            )

        # ------------------------------------------------------------
        # Remove markdown code fences if the model ignored the
        # instruction not to use them.
        # ------------------------------------------------------------

        if text.startswith("```"):
            lines = text.splitlines()

            if lines:
                lines = lines[1:]

            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]

            text = "\n".join(lines).strip()

        # ------------------------------------------------------------
        # First attempt: the entire response is JSON.
        # ------------------------------------------------------------

        try:
            parsed = json.loads(text)

            if isinstance(parsed, dict):
                return parsed

        except json.JSONDecodeError:
            pass

        # ------------------------------------------------------------
        # Second attempt: locate the first JSON object.
        #
        # This handles responses such as:
        #
        # "Here is the evaluation:"
        # { ... }
        #
        # or:
        #
        # { ... }
        # "End of evaluation."
        # ------------------------------------------------------------

        first_brace = text.find("{")

        if first_brace == -1:
            raise ValueError(
                "The evaluation model did not return a JSON object."
            )

        decoder = json.JSONDecoder()

        try:
            parsed, _ = decoder.raw_decode(
                text[first_brace:]
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                "The evaluation model returned invalid JSON."
            ) from exc

        if not isinstance(parsed, dict):
            raise ValueError(
                "The evaluation model returned an invalid JSON response."
            )

        return parsed

    # ================================================================
    # BUILD EVALUATION PROMPT
    # ================================================================

    @staticmethod
    def _build_system_prompt() -> str:
        return """
You are an expert customer service evaluator.

Evaluate the trainee's performance in the customer-service
role-play transcript provided by the user.

You MUST score the trainee on exactly these 7 dimensions:

1. Empathy
2. Problem Solving
3. Product Knowledge
4. Communication
5. Efficiency
6. Professionalism
7. De-escalation

Each dimension must receive a score from 1 to 10.

Scoring guidance:

1-2 = Very poor
3-4 = Poor
5-6 = Average
7-8 = Good
9-10 = Excellent

Also identify any serious red flags, such as:

- Compliance or policy violations
- Abusive or inappropriate language
- Failure to follow required customer-service behaviour
- Ending or abandoning the interaction improperly

If there are no red flags, return an empty red_flags array.

The overall_score must be a score from 0 to 100.

IMPORTANT:

Return ONLY one valid JSON object.

Do NOT include:
- Markdown
- Code fences
- Explanations outside the JSON
- Comments
- Trailing commas

Make sure every string is properly closed and escaped.

Required format:

{
  "overall_score": 85,
  "summary": "Overall good performance.",
  "dimensions": [
    {
      "name": "Empathy",
      "score": 8,
      "rationale": "The trainee acknowledged the customer's concern."
    },
    {
      "name": "Problem Solving",
      "score": 9,
      "rationale": "The trainee identified an appropriate solution."
    },
    {
      "name": "Product Knowledge",
      "score": 7,
      "rationale": "The trainee demonstrated reasonable product knowledge."
    },
    {
      "name": "Communication",
      "score": 8,
      "rationale": "The trainee communicated clearly."
    },
    {
      "name": "Efficiency",
      "score": 8,
      "rationale": "The trainee handled the interaction efficiently."
    },
    {
      "name": "Professionalism",
      "score": 9,
      "rationale": "The trainee remained professional throughout."
    },
    {
      "name": "De-escalation",
      "score": 7,
      "rationale": "The trainee helped reduce the customer's frustration."
    }
  ],
  "red_flags": []
}
"""

    # ================================================================
    # EVALUATE SESSION
    # ================================================================

    async def evaluate_session(
        self,
        db: AsyncSession,
        tenant_id: uuid.UUID,
        session: Session,
        messages: Sequence[Message],
    ) -> EvaluationResult:

        # ------------------------------------------------------------
        # Prepare transcript
        # ------------------------------------------------------------

        transcript_lines = []

        for msg in messages:
            role = (
                "Trainee"
                if msg.role.value == "user"
                else "Customer"
            )

            transcript_lines.append(
                f"{role}: {msg.content}"
            )

        transcript = "\n".join(
            transcript_lines
        )

        if not transcript.strip():
            raise ValueError(
                "Cannot evaluate an empty conversation."
            )

        # ------------------------------------------------------------
        # Evaluation prompt
        # ------------------------------------------------------------

        system_prompt = (
            self._build_system_prompt()
        )

        llm_messages = [
            {
                "role": "user",
                "content": (
                    "Evaluate this customer-service "
                    "role-play transcript.\n\n"
                    f"{transcript}"
                ),
            }
        ]

        # ------------------------------------------------------------
        # Call evaluation LLM
        #
        # We allow one retry if the model returns malformed JSON.
        # This does NOT change the model or its configuration.
        # ------------------------------------------------------------

        eval_data = None
        last_json_error = None

        for attempt in range(2):
            response_text = (
                 await self.llm_provider.generate_response(
        system_prompt=system_prompt,
        messages=llm_messages,
        temperature=0.0,
        max_tokens=2000,
        json_mode=True,
                )
            )

            try:
                eval_data = self._extract_json(
                    response_text
                )
                break

            except ValueError as exc:
                last_json_error = exc

                if attempt == 0:
                    continue

                raise ValueError(
                    "The evaluation model returned invalid JSON "
                    "after two attempts."
                ) from exc

        if not isinstance(eval_data, dict):
            raise ValueError(
                "The evaluation model returned an invalid response."
            )

        # ------------------------------------------------------------
        # Validate overall score
        # ------------------------------------------------------------

        overall_score = eval_data.get(
            "overall_score"
        )

        if not isinstance(
            overall_score,
            (int, float),
        ):
            raise ValueError(
                "Evaluation did not contain a valid overall score."
            )

        overall_score = int(
            max(
                0,
                min(
                    100,
                    round(
                        float(
                            overall_score
                        )
                    ),
                ),
            )
        )

        # ------------------------------------------------------------
        # Validate summary
        # ------------------------------------------------------------

        summary = eval_data.get(
            "summary"
        )

        if not isinstance(
            summary,
            str,
        ):
            summary = (
                "No evaluation summary was provided."
            )

        # ------------------------------------------------------------
        # Validate dimensions
        # ------------------------------------------------------------

        raw_dimensions = eval_data.get(
            "dimensions"
        )

        if not isinstance(
            raw_dimensions,
            list,
        ):
            raise ValueError(
                "Evaluation did not contain dimension scores."
            )

        dimensions_by_name: dict[
            str,
            dict[str, object],
        ] = {}

        for dimension in raw_dimensions:
            if not isinstance(
                dimension,
                dict,
            ):
                continue

            name = dimension.get(
                "name"
            )

            if name not in EVALUATION_DIMENSIONS:
                continue

            score = dimension.get(
                "score"
            )

            if not isinstance(
                score,
                (int, float),
            ):
                continue

            score = int(
                max(
                    1,
                    min(
                        10,
                        round(
                            float(score)
                        ),
                    ),
                )
            )

            rationale = dimension.get(
                "rationale"
            )

            if not isinstance(
                rationale,
                str,
            ):
                rationale = (
                    "No rationale was provided."
                )

            dimensions_by_name[
                name
            ] = {
                "score": score,
                "rationale": rationale,
            }

        # ------------------------------------------------------------
        # Ensure all seven dimensions are present
        # ------------------------------------------------------------

        missing_dimensions = [
            dimension
            for dimension in EVALUATION_DIMENSIONS
            if dimension not in dimensions_by_name
        ]

        if missing_dimensions:
            raise ValueError(
                "Evaluation is missing required dimensions: "
                + ", ".join(
                    missing_dimensions
                )
            )

        # ------------------------------------------------------------
        # Save evaluation result
        # ------------------------------------------------------------

        eval_create = EvaluationResultCreate(
            session_id=session.id,
            overall_score=overall_score,
            summary=summary,
        )

        eval_result = (
            await self.eval_result_repo.create(
                db=db,
                obj_in=eval_create,
                tenant_id=tenant_id,
            )
        )

        # ------------------------------------------------------------
        # Save all 7 dimension scores
        # ------------------------------------------------------------

        for dimension_name in EVALUATION_DIMENSIONS:
            dimension = (
                dimensions_by_name[
                    dimension_name
                ]
            )

            dimension_create = (
                DimensionScoreCreate(
                    evaluation_id=eval_result.id,
                    dimension_name=dimension_name,
                    score=dimension["score"],
                    rationale=dimension[
                        "rationale"
                    ],
                )
            )

            await self.dimension_score_repo.create(
                db=db,
                obj_in=dimension_create,
            )

        # ------------------------------------------------------------
        # Save red flags
        # ------------------------------------------------------------

        raw_red_flags = eval_data.get(
            "red_flags",
            [],
        )

        if isinstance(
            raw_red_flags,
            list,
        ):
            for red_flag in raw_red_flags:
                if not isinstance(
                    red_flag,
                    dict,
                ):
                    continue

                reason = red_flag.get(
                    "reason"
                )

                description = red_flag.get(
                    "description"
                )

                if not isinstance(
                    reason,
                    str,
                ):
                    continue

                if not isinstance(
                    description,
                    str,
                ):
                    continue

                red_flag_create = (
                    RedFlagCreate(
                        evaluation_id=eval_result.id,
                        reason=reason,
                        description=description,
                    )
                )

                await self.red_flag_repo.create(
                    db=db,
                    obj_in=red_flag_create,
                )

        return eval_result