import uuid
import json
from typing import List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from src.infrastructure.llm.base import LLMProvider
from src.domains.simulations.models import Session, Message, SessionStatus
from src.domains.evaluations.models import EvaluationResult

from src.domains.evaluations.crud import CRUDEvaluationResult, CRUDDimensionScore, CRUDRedFlag
from src.domains.evaluations.schemas import (
    EvaluationResultCreate, DimensionScoreCreate, RedFlagCreate
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

    async def evaluate_session(
        self, db: AsyncSession, tenant_id: uuid.UUID, session: Session, messages: Sequence[Message]
    ) -> EvaluationResult:
        
        # Prepare transcript
        transcript = ""
        for msg in messages:
            role = "Trainee" if msg.role.value == "user" else "Customer"
            transcript += f"{role}: {msg.content}\n"

        system_prompt = """
        You are an expert customer service evaluator. Evaluate the following transcript.
        Score the trainee on 7 dimensions (Empathy, Problem Solving, Product Knowledge, Communication, Efficiency, Professionalism, De-escalation) from 1 to 10.
        Also, identify any Red Flags (compliance issues, swearing, hanging up).
        Return purely a JSON text without markdown wrappers in the following format:
        {
          "overall_score": 85,
          "summary": "Overall good job...",
          "dimensions": [
            {"name": "Empathy", "score": 8, "rationale": "..."}
          ],
          "red_flags": [
            {"reason": "...", "description": "..."}
          ]
        }
        """

        llm_messages = [{"role": "user", "content": f"Transcript:\n{transcript}"}]

        response_text = await self.llm_provider.generate_response(
            system_prompt=system_prompt, messages=llm_messages, temperature=0.0
        )

        try:
            eval_data = json.loads(response_text)
        except json.JSONDecodeError:
            # Fallback if the LLM output is malformed
            eval_data = {
                "overall_score": 0,
                "summary": "Failed to parse JSON evaluation from LLM. Output was: "
                + response_text[:100],
                "dimensions": [],
                "red_flags": [],
            }

        eval_create = EvaluationResultCreate(
            session_id=session.id,
            overall_score=eval_data.get("overall_score"),
            summary=eval_data.get("summary")
        )
        eval_result = await self.eval_result_repo.create(db=db, obj_in=eval_create, tenant_id=tenant_id)

        for dim in eval_data.get("dimensions", []):
            ds_create = DimensionScoreCreate(
                evaluation_id=eval_result.id,
                dimension_name=dim.get("name"),
                score=dim.get("score"),
                rationale=dim.get("rationale")
            )
            await self.dimension_score_repo.create(db=db, obj_in=ds_create)

        for rf in eval_data.get("red_flags", []):
            rf_create = RedFlagCreate(
                evaluation_id=eval_result.id,
                reason=rf.get("reason"),
                description=rf.get("description")
            )
            await self.red_flag_repo.create(db=db, obj_in=rf_create)

        return eval_result
