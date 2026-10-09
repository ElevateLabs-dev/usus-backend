"""
End-to-end API tests for the training loop:
categories -> scenarios -> brief -> role-play -> 7-dimension evaluation
-> history -> progress (and the manager team view).

Runs on in-memory SQLite with a scripted fake LLM.
"""

import json

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.domains.evaluations.models  # noqa: F401  (register all tables)
from src.core.base_model import Base
from src.core.database import get_db
from src.core.security import hash_password
from src.core.training import SkillDimension
from src.domains.evaluations import router as evaluations_router
from src.domains.scenarios.crud import scenario as scenario_repo
from src.domains.scenarios.service import ScenarioService
from src.domains.simulations import router as simulations_router
from src.domains.tenants.models import Tenant
from src.domains.users.models import User
from src.infrastructure.llm.base import LLMProvider
from src.main import app

PASSWORD = "password-123"


def evaluation_json(scores: dict[str, int] | None = None, **extra) -> str:
    scores = scores or {}
    return json.dumps(
        {
            "summary": "Solid handling overall.",
            "dimensions": {
                d.value: {"score": scores.get(d.value, 80), "rationale": "Because"}
                for d in SkillDimension
            },
            "strengths": ["Apologised sincerely"],
            "improvements": ["Took too long to offer a remedy"],
            "missed_opportunities": ["Could have offered the voucher earlier"],
            "recommendations": ["Lead with the concrete remedy"],
            "red_flags": [],
            **extra,
        }
    )


class FakeLLM(LLMProvider):
    """Customer replies are fixed; evaluator replies come from a queue."""

    def __init__(self):
        self.evaluations: list[str] = []
        self.evaluation_calls = 0
        self.customer_prompts: list[str] = []

    async def generate_response(
        self, system_prompt, messages, temperature=0.7, max_tokens=1024, json_mode=False
    ):
        if json_mode:
            self.evaluation_calls += 1
            return self.evaluations.pop(0) if self.evaluations else evaluation_json()
        self.customer_prompts.append(system_prompt)
        return "I'm still upset about this."


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(simulations_router._simulation_service, "llm_provider", fake)
    return fake


@pytest_asyncio.fixture
async def client(session_factory, llm, monkeypatch):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Background evaluations use the test database too
    monkeypatch.setattr(simulations_router, "_session_factory", session_factory)
    monkeypatch.setattr(evaluations_router, "_session_factory", session_factory)
    monkeypatch.setattr(evaluations_router, "_llm_provider", llm)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _make_org(session_factory, name="Acme"):
    """Organization with seeded scenarios, a manager and a trainee."""
    async with session_factory() as db:
        tenant = Tenant(name=name)
        db.add(tenant)
        await db.flush()
        slug = name.lower().replace(" ", "")
        for email, role in (
            (f"manager@{slug}.com", "manager"),
            (f"trainee@{slug}.com", "trainee"),
        ):
            db.add(
                User(
                    email=email,
                    full_name=role.title(),
                    hashed_password=hash_password(PASSWORD),
                    role=role,
                    tenant_id=tenant.id,
                )
            )
        await db.commit()
        await ScenarioService(scenario_repo).seed_defaults(db, tenant.id)
        return tenant.id


async def _auth(client, email):
    response = await client.post(
        "/api/v1/auth/token", data={"username": email, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _scenario_id(client, headers, name="Late Delivery Complaint"):
    scenarios = (await client.get("/api/v1/scenarios/", headers=headers)).json()
    return next(s["id"] for s in scenarios if s["name"] == name)


async def _play(client, headers, scenario_id, messages=("Sorry about that!",)):
    session = await client.post(
        "/api/v1/simulations/start", json={"scenario_id": scenario_id}, headers=headers
    )
    session_id = session.json()["id"]
    for text in messages:
        await client.post(
            f"/api/v1/simulations/{session_id}/message",
            json={"content": text},
            headers=headers,
        )
    return session_id


async def test_categories_scenarios_and_brief(client, session_factory):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")

    categories = (
        await client.get("/api/v1/scenarios/categories", headers=trainee)
    ).json()
    assert [c["id"] for c in categories] == [
        "de_escalation",
        "communication",
        "problem_resolution",
        "empathy",
        "policy_compliance",
    ]
    assert all(c["scenario_count"] == 1 for c in categories)
    assert categories[0]["name"] == "De-escalation"

    scenarios = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    assert len(scenarios) == 5
    first = scenarios[0]
    assert first["progress"] == {
        "status": "new",
        "attempts": 0,
        "best_score": None,
        "last_score": None,
    }
    assert {"id", "name"} <= set(first["skills"][0])
    assert "system_prompt" not in first

    filtered = await client.get(
        "/api/v1/scenarios/?category=empathy&difficulty=beginner", headers=trainee
    )
    assert [s["name"] for s in filtered.json()] == ["Elderly Customer Locked Out"]

    brief = (
        await client.get(
            f"/api/v1/scenarios/{await _scenario_id(client, trainee)}", headers=trainee
        )
    ).json()
    assert brief["customer"]["name"] == "Jordan"
    assert brief["trainee_objective"]
    assert brief["important_information"][0]["label"] == "Delivery delays"
    assert brief["category"] == {"id": "de_escalation", "name": "De-escalation"}
    for hidden in ("system_prompt", "escalation_behavior", "success_criteria"):
        assert hidden not in brief


async def test_role_play_evaluation_history_and_progress(client, session_factory, llm):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    scenario_id = await _scenario_id(client, trainee)

    session_id = await _play(client, trainee, scenario_id, ["Hello", "Refunding now"])

    # Ending responds first; the evaluation then runs as a background task
    llm.evaluations.append(
        evaluation_json({"accuracy": 100, "empathy": 30, "efficiency": 60})
    )
    ended = await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)
    assert ended.status_code == 200, ended.text
    assert ended.json()["status"] == "completed"
    assert ended.json()["ended_at"] is not None
    response = await client.get(
        f"/api/v1/simulations/{session_id}/evaluation", headers=trainee
    )
    assert response.status_code == 200
    evaluation = response.json()
    assert [d["dimension_key"] for d in evaluation["dimension_scores"]] == [
        d.value for d in SkillDimension
    ]
    scores = [d["score"] for d in evaluation["dimension_scores"]]
    assert evaluation["overall_score"] == round(sum(scores) / 7)  # = 73
    assert evaluation["strengths"] == ["Apologised sincerely"]
    assert evaluation["missed_opportunities"] == [
        "Could have offered the voucher earlier"
    ]

    # Ending an evaluated session again changes nothing
    again = await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)
    assert again.json()["status"] == "evaluated"
    assert llm.evaluation_calls == 1

    # History list + detail
    page = (await client.get("/api/v1/simulations/", headers=trainee)).json()
    assert page["total"] == 1
    item = page["items"][0]
    assert item["overall_score"] == 73
    assert item["message_count"] == 4
    assert item["scenario"]["category"]["id"] == "de_escalation"
    assert item["duration_seconds"] is not None

    detail = (
        await client.get(f"/api/v1/simulations/{session_id}", headers=trainee)
    ).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "model", "user", "model"]
    assert detail["evaluation"]["overall_score"] == 73

    # Scenario list now shows progress
    scenarios = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    played = next(s for s in scenarios if s["id"] == scenario_id)
    assert played["progress"] == {
        "status": "completed",
        "attempts": 1,
        "best_score": 73,
        "last_score": 73,
    }

    # A second, better session -> progress shows improvement
    second = await _play(client, trainee, scenario_id)
    llm.evaluations.append(evaluation_json({d.value: 90 for d in SkillDimension}))
    await client.post(f"/api/v1/simulations/{second}/end", headers=trainee)

    progress = (await client.get("/api/v1/progress/me", headers=trainee)).json()
    assert progress["sessions_completed"] == 2
    assert progress["average_score"] == 82  # (73 + 90) / 2
    assert progress["latest_score"] == 90
    assert progress["score_change"] == 17 and progress["improving"] is True
    assert [p["overall_score"] for p in progress["score_history"]] == [73, 90]
    empathy = next(d for d in progress["dimensions"] if d["id"] == "empathy")
    assert empathy == {
        "id": "empathy",
        "name": "Empathy",
        "average": 60,
        "latest": 90,
        "change": 60,
    }
    de_escalation = next(
        c for c in progress["categories"] if c["id"] == "de_escalation"
    )
    assert de_escalation["sessions_completed"] == 2

    # Manager views
    manager = await _auth(client, "manager@acme.com")
    team = (await client.get("/api/v1/progress/team", headers=manager)).json()
    assert len(team) == 1
    assert team[0]["email"] == "trainee@acme.com"
    assert team[0]["sessions_completed"] == 2 and team[0]["latest_score"] == 90
    report = await client.get(
        f"/api/v1/progress/users/{progress['user_id']}", headers=manager
    )
    assert report.json()["average_score"] == 82


async def test_failed_evaluation_can_be_retried(client, session_factory, llm):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    session_id = await _play(client, trainee, await _scenario_id(client, trainee))

    # Bad output twice -> the background evaluation fails, nothing is saved
    llm.evaluations += ["not json", json.dumps({"summary": "missing dimensions"})]
    ended = await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)
    assert ended.status_code == 200
    detail = (
        await client.get(f"/api/v1/simulations/{session_id}", headers=trainee)
    ).json()
    assert detail["status"] == "completed" and detail["evaluation"] is None
    pending = await client.get(
        f"/api/v1/simulations/{session_id}/evaluation", headers=trainee
    )
    assert pending.status_code == 404
    assert pending.json()["detail"] == "Evaluation is still being generated."

    # Ending again retries; markdown-wrapped JSON is accepted
    llm.evaluations += ["```json\n" + evaluation_json() + "\n```"]
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)

    response = await client.get(
        f"/api/v1/simulations/{session_id}/evaluation", headers=trainee
    )
    assert response.status_code == 200
    assert response.json()["overall_score"] == 80
    assert llm.evaluation_calls == 3


async def test_manager_can_rerun_evaluation(client, session_factory, llm):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    manager = await _auth(client, "manager@acme.com")
    session_id = await _play(client, trainee, await _scenario_id(client, trainee))

    # Still in progress -> nothing to evaluate yet
    early = await client.post(
        f"/api/v1/evaluations/{session_id}/generate", headers=manager
    )
    assert early.status_code == 409

    llm.evaluations += ["not json", "still not json"]  # first evaluation fails
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)

    rerun = await client.post(
        f"/api/v1/evaluations/{session_id}/generate", headers=manager
    )
    assert rerun.status_code == 202
    evaluation = await client.get(
        f"/api/v1/simulations/{session_id}/evaluation", headers=trainee
    )
    assert evaluation.status_code == 200

    # Trainees cannot use the manager endpoint
    denied = await client.post(
        f"/api/v1/evaluations/{session_id}/generate", headers=trainee
    )
    assert denied.status_code == 403


async def test_session_without_trainee_messages_scores_zero(
    client, session_factory, llm
):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    session_id = await _play(client, trainee, await _scenario_id(client, trainee), [])

    ended = await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)
    assert ended.status_code == 200

    evaluation = await client.get(
        f"/api/v1/simulations/{session_id}/evaluation", headers=trainee
    )
    assert evaluation.json()["overall_score"] == 0
    assert llm.evaluation_calls == 0


async def test_customer_prompt_built_from_brief(client, session_factory, llm):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    # "Refund Outside Policy" has no hand-written system_prompt
    scenario_id = await _scenario_id(client, trainee, "Refund Outside Policy")
    await _play(client, trainee, scenario_id)

    prompt = llm.customer_prompts[-1]
    assert "customer named Sam" in prompt
    assert "45 days ago" in prompt
    assert "Stay in character" in prompt


async def test_progress_permissions(client, session_factory):
    await _make_org(session_factory)
    await _make_org(session_factory, name="Other Co")
    trainee = await _auth(client, "trainee@acme.com")
    other_manager = await _auth(client, "manager@otherco.com")

    assert (
        await client.get("/api/v1/progress/team", headers=trainee)
    ).status_code == 403

    me = (await client.get("/api/v1/users/me", headers=trainee)).json()
    cross_org = await client.get(
        f"/api/v1/progress/users/{me['id']}", headers=other_manager
    )
    assert cross_org.status_code == 404

    # Each organization only sees its own history
    other_trainee = await _auth(client, "trainee@otherco.com")
    session_id = await _play(client, trainee, await _scenario_id(client, trainee))
    assert (
        await client.get(f"/api/v1/simulations/{session_id}", headers=other_trainee)
    ).status_code == 404


async def test_trainees_cannot_touch_each_others_sessions(client, session_factory):
    tenant_id = await _make_org(session_factory)
    async with session_factory() as db:
        db.add(
            User(
                email="colleague@acme.com",
                hashed_password=hash_password(PASSWORD),
                role="trainee",
                tenant_id=tenant_id,
            )
        )
        await db.commit()
    owner = await _auth(client, "trainee@acme.com")
    colleague = await _auth(client, "colleague@acme.com")
    session_id = await _play(client, owner, await _scenario_id(client, owner))
    base = f"/api/v1/simulations/{session_id}"

    message = await client.post(
        f"{base}/message", json={"content": "hi"}, headers=colleague
    )
    assert message.status_code == 404
    assert (await client.post(f"{base}/end", headers=colleague)).status_code == 404
    assert (
        await client.get(f"{base}/evaluation", headers=colleague)
    ).status_code == 404
    assert (await client.get(base, headers=colleague)).status_code == 404
