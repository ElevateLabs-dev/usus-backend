# ruff: noqa: F811  (fixtures imported from test_management)
"""
Usage and cost: AI requests and voice calls are recorded per session, and
platform admins (everything) and company admins (their organization) see them.
"""

import uuid
from decimal import Decimal

import pytest

from src.domains.simulations import router as simulations_router
from src.domains.simulations.models import Session, SessionStatus
from src.domains.usage import meter
from src.domains.usage.models import UsageRecord
from src.domains.usage.pricing import llm_cost
from src.infrastructure.llm.base import LLMProvider
from tests.test_management import (  # noqa: F401  (client, outbox, ... are fixtures)
    NEW_SCENARIO,
    ROOT,
    _activate,
    _auth,
    _invite,
    _onboard,
    client,
    llm,
    outbox,
    session_factory,
)


class MeteredLLM(LLMProvider):
    """Replies like the real provider would and reports its tokens."""

    async def generate_response(
        self, system_prompt, messages, temperature=0.7, max_tokens=1024, json_mode=False
    ):
        meter.record_llm("gpt-4.1-mini-2025-04-14", 1000, 200)
        return "I'm not happy about this."


@pytest.fixture
def metered(monkeypatch, session_factory):
    monkeypatch.setattr(meter, "_session_factory", session_factory)
    monkeypatch.setattr(
        simulations_router._simulation_service, "llm_provider", MeteredLLM()
    )


def test_llm_cost_uses_the_model_price():
    assert llm_cost("gpt-4.1-mini", 1_000_000, 0) == Decimal("0.40")
    # Dated names use their base model's price, not a shorter prefix's
    assert llm_cost("gpt-4.1-mini-2025-04-14", 1000, 200) == Decimal("0.00072")
    assert llm_cost("gpt-4.1", 0, 1_000_000) == Decimal("8.00")
    assert llm_cost("some-new-model", 10, 10) is None


async def test_requests_outside_a_session_are_not_recorded(
    session_factory, monkeypatch
):
    monkeypatch.setattr(meter, "_session_factory", session_factory)
    meter.record_llm("gpt-4.1-mini", 10, 10)
    await meter.drain()
    async with session_factory() as db:
        assert await db.get(UsageRecord, uuid.uuid4()) is None
        assert (await db.execute(UsageRecord.__table__.select())).first() is None


def test_voice_call_length_and_cost():
    added = []

    class FakeDb:
        def add(self, record):
            added.append(record)

    call = {
        "startedAt": "2026-11-18T10:00:00.000Z",
        "endedAt": "2026-11-18T10:02:30.500Z",
        "cost": 0.231,
    }
    meter.record_voice_call(FakeDb(), uuid.uuid4(), uuid.uuid4(), call)
    assert added[0].seconds == 150 or added[0].seconds == 151
    assert added[0].cost_usd == Decimal("0.231")
    assert added[0].kind == "voice"

    meter.record_voice_call(FakeDb(), uuid.uuid4(), uuid.uuid4(), {})
    assert added[1].seconds == 0 and added[1].cost_usd is None


async def test_admins_see_usage_and_cost(client, outbox, session_factory, metered):
    acme, acme_admin = await _onboard(client, outbox)
    await _invite(client, acme_admin, "t@acme.com", "trainee")
    trainee = await _activate(client, outbox, "t@acme.com")
    scenario = (
        await client.post("/api/v1/scenarios/", json=NEW_SCENARIO, headers=acme_admin)
    ).json()

    started = await client.post(
        "/api/v1/simulations/start",
        json={"scenario_id": scenario["id"]},
        headers=trainee,
    )
    session_id = started.json()["id"]
    for text in ("Hello", "Let me check that for you"):
        sent = await client.post(
            f"/api/v1/simulations/{session_id}/message",
            json={"content": text},
            headers=trainee,
        )
        assert sent.status_code == 200, sent.text
    await meter.drain()

    # A voice session in another organization
    beta, beta_admin = await _onboard(
        client, outbox, name="Beta", admin_email="admin@beta.com"
    )
    async with session_factory() as db:
        voice_session = Session(
            tenant_id=uuid.UUID(beta["id"]),
            scenario_id=uuid.uuid4(),
            status=SessionStatus.COMPLETED,
            voice_call_id="call_1",
        )
        db.add(voice_session)
        await db.flush()
        meter.record_voice_call(
            db,
            voice_session.tenant_id,
            voice_session.id,
            {
                "startedAt": "2026-11-18T10:00:00Z",
                "endedAt": "2026-11-18T10:03:00Z",
                "cost": 0.3,
            },
        )
        await db.commit()

    root = await _auth(client, ROOT)
    report = await client.get("/api/v1/platform/usage?days=7", headers=root)
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["days"] == 7
    totals = body["totals"]
    assert totals["sessions"] == 2
    assert (totals["text_sessions"], totals["voice_sessions"]) == (1, 1)
    assert totals["input_tokens"] == 2000 and totals["output_tokens"] == 400
    assert totals["ai_cost"] == pytest.approx(0.00144)
    assert totals["voice_cost"] == pytest.approx(0.3)
    assert totals["voice_minutes"] == 3.0
    assert [o["organization_name"] for o in body["organizations"]] == ["Beta", "Acme"]

    text_session = next(s for s in body["sessions"] if s["mode"] == "text")
    assert text_session["session_id"] == session_id
    assert text_session["trainee_email"] == "t@acme.com"
    assert text_session["scenario_name"] == NEW_SCENARIO["name"]
    assert text_session["conversation_cost"] == pytest.approx(0.00144)
    assert text_session["duration_seconds"] is None  # still in progress

    # Company admins only see their own organization
    own = (
        await client.get("/api/v1/organizations/me/usage", headers=acme_admin)
    ).json()
    assert [s["session_id"] for s in own["sessions"]] == [session_id]
    assert own["organizations"] == []
    assert own["totals"]["voice_cost"] == 0
    beta_own = (
        await client.get("/api/v1/organizations/me/usage", headers=beta_admin)
    ).json()
    assert beta_own["totals"]["voice_cost"] == pytest.approx(0.3)

    # Everyone else is refused
    assert (
        await client.get("/api/v1/platform/usage", headers=acme_admin)
    ).status_code == 403
    assert (
        await client.get("/api/v1/organizations/me/usage", headers=trainee)
    ).status_code == 403
    assert acme["id"] != beta["id"]
