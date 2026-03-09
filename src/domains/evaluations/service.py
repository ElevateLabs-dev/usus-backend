import uuid
import json
from typing import List

from src.infrastructure.storage.memory import MemoryRepository
from src.infrastructure.llm.base import LLMProvider
from src.domains.simulations.models import Session, Message, SessionStatus
from src.domains.evaluations.models import EvaluationResult, DimensionScore, RedFlag


class EvaluationService:
    def __init__(
        self,
        eval_result_repo: MemoryRepository[EvaluationResult],
        dimension_score_repo: MemoryRepository[DimensionScore],
        red_flag_repo: MemoryRepository[RedFlag],
        llm_provider: LLMProvider,
    ):
        self.eval_result_repo = eval_result_repo
        self.dimension_score_repo = dimension_score_repo
        self.red_flag_repo = red_flag_repo
        self.llm_provider = llm_provider

    async def evaluate_session(
        self, tenant_id: uuid.UUID, session: Session, messages: List[Message]
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

        eval_id = uuid.uuid4()
        eval_result = EvaluationResult(
            id=eval_id,
            tenant_id=tenant_id,
            session_id=session.id,
            overall_score=eval_data.get("overall_score"),
            summary=eval_data.get("summary"),
        )
        self.eval_result_repo.save(tenant_id, eval_result)

        for dim in eval_data.get("dimensions", []):
            ds = DimensionScore(
                id=uuid.uuid4(),
                evaluation_id=eval_id,
                dimension_name=dim.get("name"),
                score=dim.get("score"),
                rationale=dim.get("rationale"),
            )
            self.dimension_score_repo.save(tenant_id, ds)

        for rf in eval_data.get("red_flags", []):
            flag = RedFlag(
                id=uuid.uuid4(),
                evaluation_id=eval_id,
                reason=rf.get("reason"),
                description=rf.get("description"),
            )
            self.red_flag_repo.save(tenant_id, flag)

        session.status = SessionStatus.EVALUATED

        return eval_result
