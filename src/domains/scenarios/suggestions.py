"""
AI-suggested scenarios, written from the organization's knowledge base and
metrics. Suggestions are drafts: nothing is saved until the company creates
one with POST /scenarios/.

Suggestions too similar to an existing scenario, or to each other, are
dropped (cosine similarity of their embeddings >= the threshold).
"""

import logging
import math
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.database import get_db
from src.core.dependencies import AuthContext, UserRole, require_roles
from src.core.training import CATEGORY_INFO, SkillDimension, TrainingCategory
from src.domains.evaluations.service import _extract_json
from src.domains.knowledge import service as knowledge
from src.domains.metrics import service as metrics_service
from src.domains.scenarios.models import CustomerPersona, DifficultyLevel, Scenario
from src.domains.scenarios.schemas import ScenarioWrite
from src.domains.tenants.models import Tenant
from src.infrastructure.llm.base import LLMProvider
from src.infrastructure.llm.factory import get_llm_provider

logger = logging.getLogger("usus.suggestions")

router = APIRouter(prefix="/api/v1/scenarios", tags=["Scenarios"])

_PASSAGES = 12
_EXTRA = 2  # ask for a few more, since some may be dropped as duplicates

_Editor = Annotated[
    AuthContext,
    Depends(
        require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.PLATFORM_ADMIN)
    ),
]

_llm_provider: LLMProvider | None = None


def _llm() -> LLMProvider:
    """Swapped out in tests."""
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = get_llm_provider()
    return _llm_provider


class SuggestRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=5)
    category: Optional[TrainingCategory] = None
    difficulty: Optional[DifficultyLevel] = None
    metrics: list[str] = Field(
        default=[],
        max_length=20,
        description="Metric keys the scenarios should test; empty = let the AI "
        "pick from all your metrics",
    )
    focus: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional topic, e.g. 'refund requests for late deliveries'",
    )
    similarity_threshold: Optional[float] = Field(
        default=None,
        ge=0.5,
        le=0.99,
        description="Drop suggestions at least this similar (0-1) to an existing "
        f"scenario or another suggestion. Default "
        f"{settings.SCENARIO_SIMILARITY_THRESHOLD}",
    )


class SuggestResponse(BaseModel):
    suggestions: list[ScenarioWrite] = Field(
        description="Drafts; create one with POST /scenarios/ (edit it first if "
        "you like)"
    )
    skipped_similar: int = Field(
        description="Suggestions dropped for being too similar"
    )


_SYSTEM = """
You design customer-service training role-plays for a company. Each scenario
is played by a trainee (the company's agent) against an AI customer.

Base the scenarios on the company's own documents: their policies,
products and procedures. Each scenario must test something the documents
cover, so the trainee can be judged against them. Make the scenarios clearly
different from each other and from the company's existing scenarios.

Return ONLY a JSON object: {"scenarios": [ ... ]}. Each scenario:
{
  "name": "Short title, 3-80 characters",
  "description": "One or two sentences",
  "category": one of __CATEGORIES__,
  "difficulty": one of "beginner", "intermediate", "advanced",
  "persona": one of "friendly", "frustrated", "angry",
  "skills": up to 3 of __SKILLS__,
  "metrics": the keys of the metrics this scenario should be scored on,
  "estimated_minutes": 5-20,
  "customer_name": "First name",
  "customer_personality": "A few words",
  "customer_emotion": "A few words",
  "customer_background": "Who the customer is",
  "situation": "What happened, in detail",
  "customer_goal": "What the customer wants",
  "trainee_objective": "What the trainee must do",
  "important_information": [{"label": "...", "content": "A policy or fact
    from the documents the trainee may use"}],
  "escalation_behavior": "How the customer reacts to poor handling",
  "success_criteria": "What good handling looks like, per the documents"
}
""".strip()


def _system_prompt() -> str:
    return _SYSTEM.replace(
        "__CATEGORIES__", ", ".join(f'"{c.value}"' for c in TrainingCategory)
    ).replace("__SKILLS__", ", ".join(f'"{s.value}"' for s in SkillDimension))


def _user_prompt(
    tenant: Tenant,
    body: SuggestRequest,
    asked: int,
    passages: list[str],
    metric_lines: list[str],
    existing: list[str],
) -> str:
    wanted = [f"Write {asked} scenarios."]
    if body.category:
        wanted.append(
            f"Category: {body.category.value} ({CATEGORY_INFO[body.category][0]})."
        )
    if body.difficulty:
        wanted.append(f"Difficulty: {body.difficulty.value}.")
    if body.focus:
        wanted.append(f"Focus on: {body.focus}")
    company = tenant.name + (f" ({tenant.company_type})" if tenant.company_type else "")
    return "\n\n".join(
        [
            f"COMPANY: {company}",
            " ".join(wanted),
            "METRICS (key: what it measures)\n" + "\n".join(metric_lines),
            "EXISTING SCENARIOS (do not repeat these)\n"
            + ("\n".join(f"- {name}" for name in existing) or "(none)"),
            "COMPANY DOCUMENTS (excerpts)\n"
            + "\n\n".join(f"--- excerpt ---\n{p}" for p in passages),
        ]
    )


def _similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def _summary(name: str, description: str, situation: str | None) -> str:
    return f"{name}. {description} {situation or ''}".strip()


def _drafts(
    raw: str, body: SuggestRequest, metric_keys: set[str]
) -> list[ScenarioWrite]:
    try:
        items = _extract_json(raw).get("scenarios") or []
    except ValueError:
        logger.warning("Scenario suggestions were not JSON")
        return []
    drafts = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        if body.category:
            item["category"] = body.category.value
        if body.difficulty:
            item["difficulty"] = body.difficulty.value
        item["skills"] = [
            s
            for s in item.get("skills") or []
            if s in SkillDimension._value2member_map_
        ][:3]
        chosen = body.metrics or item.get("metrics") or []
        item["metrics"] = [k for k in dict.fromkeys(chosen) if k in metric_keys]
        item["important_information"] = [
            info
            for info in item.get("important_information") or []
            if isinstance(info, dict)
            and isinstance(info.get("label"), str)
            and isinstance(info.get("content"), str)
        ]
        item.pop("voice_id", None)
        item.pop("system_prompt", None)
        if item.get("persona") not in CustomerPersona._value2member_map_:
            item["persona"] = CustomerPersona.FRUSTRATED.value
        try:
            minutes = int(item.get("estimated_minutes") or 10)
        except (TypeError, ValueError):
            minutes = 10
        item["estimated_minutes"] = min(max(minutes, 1), 120)
        try:
            drafts.append(ScenarioWrite.model_validate(item))
        except ValidationError as exc:
            logger.info("Dropped an invalid scenario suggestion: %s", exc)
    return drafts


@router.post(
    "/suggestions",
    response_model=SuggestResponse,
    summary="Suggest scenarios from your knowledge base",
    description=(
        "**Company admin / manager only.** The AI writes scenario drafts from "
        "your knowledge base documents and metrics. Needs at least one ready "
        "document (`/knowledge-base/documents`).\n\n"
        "Nothing is saved: show the drafts, let the user edit them, and create "
        "the ones they keep with `POST /scenarios/`. Drafts too similar to an "
        "existing scenario or to each other are dropped (`skipped_similar`), so "
        "fewer than `count` may come back."
    ),
    responses={
        400: {"description": "No ready knowledge base document yet"},
        422: {"description": "Unknown metric key"},
        502: {"description": "The AI did not return usable suggestions"},
    },
)
async def suggest_scenarios(
    body: SuggestRequest,
    ctx: _Editor,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuggestResponse:
    if ctx.tenant_id is None:
        raise HTTPException(status_code=401, detail="Tenant context required")
    tenant_id: UUID = ctx.tenant_id
    if not await knowledge.ready_count(db, tenant_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload a document to your knowledge base first",
        )
    try:
        body.metrics = await metrics_service.check_keys(db, tenant_id, body.metrics)
    except metrics_service.UnknownMetricError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    tenant = await db.get(Tenant, tenant_id)
    specs = await metrics_service.all_specs(db, tenant_id)
    if body.metrics:
        specs = [m for m in specs if m.key in body.metrics]
    existing = (
        await db.execute(
            select(Scenario.name, Scenario.description, Scenario.situation).where(
                Scenario.tenant_id == tenant_id, Scenario.is_archived.is_(False)
            )
        )
    ).all()

    if body.focus:
        passages = await knowledge.search(db, tenant_id, body.focus, limit=_PASSAGES)
    else:
        passages = await knowledge.sample_passages(db, tenant_id, _PASSAGES)

    asked = body.count + _EXTRA
    try:
        raw = await _llm().generate_response(
            system_prompt=_system_prompt(),
            messages=[
                {
                    "role": "user",
                    "content": _user_prompt(
                        tenant,
                        body,
                        asked,
                        passages,
                        [f"{m.key}: {m.name} - {m.description}" for m in specs],
                        [name for name, _, _ in existing],
                    ),
                }
            ],
            temperature=0.8,
            max_tokens=6000,
            json_mode=True,
        )
    except Exception:
        logger.exception("Scenario suggestions failed")
        raise HTTPException(status_code=502, detail="Could not suggest scenarios")

    drafts = _drafts(raw, body, {m.key for m in specs})
    if not drafts:
        raise HTTPException(status_code=502, detail="Could not suggest scenarios")

    threshold = body.similarity_threshold or settings.SCENARIO_SIMILARITY_THRESHOLD
    names = {name.lower() for name, _, _ in existing}
    try:
        vectors = await knowledge.embedder.embed(
            [_summary(*row) for row in existing]
            + [_summary(d.name, d.description, d.situation) for d in drafts]
        )
    except Exception:
        # Still useful without it; only exact names are caught then
        logger.exception("Embedding scenario suggestions failed")
        vectors = [[] for _ in range(len(existing) + len(drafts))]
    kept_vectors = vectors[: len(existing)]
    kept: list[ScenarioWrite] = []
    skipped = 0
    for draft, vector in zip(drafts, vectors[len(existing) :]):
        too_close = draft.name.lower() in names or any(
            _similarity(vector, other) >= threshold for other in kept_vectors
        )
        if too_close:
            skipped += 1
            continue
        if len(kept) < body.count:
            kept.append(draft)
            kept_vectors.append(vector)
            names.add(draft.name.lower())
    return SuggestResponse(suggestions=kept, skipped_similar=skipped)
