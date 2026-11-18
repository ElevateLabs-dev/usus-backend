# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Sessions the trainee left are ended after a while."""

from datetime import datetime, timedelta, timezone

from src.domains.simulations.idle import end_idle_sessions
from src.domains.usage.models import UsageRecord
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    _play,
    _scenario_id,
    client,
    llm,
    session_factory,
)
from tests.test_voice import FakeVapi, vapi  # noqa: F401


def _later(minutes):
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


async def _status(client, headers, session_id):
    detail = await client.get(f"/api/v1/simulations/{session_id}", headers=headers)
    return detail.json()


async def test_left_text_session_is_ended_and_evaluated(
    client, session_factory, llm, vapi
):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    scenario_id = await _scenario_id(client, trainee)
    talked = await _play(client, trainee, scenario_id)
    silent = await _play(client, trainee, scenario_id, messages=())

    # Not idle long enough yet
    assert await end_idle_sessions(session_factory, vapi, llm, _later(10)) == []
    assert (await _status(client, trainee, talked))["status"] == "in_progress"

    ended = await end_idle_sessions(session_factory, vapi, llm, _later(31))
    assert {str(i) for i in ended} == {talked, silent}

    talked_detail = await _status(client, trainee, talked)
    assert talked_detail["status"] == "evaluated"
    assert talked_detail["ended_at"] is not None
    # Nothing to score when the trainee never spoke
    assert (await _status(client, trainee, silent))["status"] == "completed"
    assert llm.evaluation_calls == 1

    # Already ended: nothing more to do
    assert await end_idle_sessions(session_factory, vapi, llm, _later(60)) == []


async def test_left_voice_call_keeps_its_transcript(client, session_factory, llm, vapi):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    scenario_id = await _scenario_id(client, trainee)
    session_id = await _play(client, trainee, scenario_id, messages=())
    await client.post(f"/api/v1/simulations/{session_id}/voice", headers=trainee)

    get_call = vapi.get_call

    async def priced_call(call_id):
        return {**await get_call(call_id), "cost": 0.12}

    async def latest_call(assistant_id):
        return await priced_call("call_7")

    vapi.get_call = priced_call
    vapi.latest_call = latest_call

    # A call can last up to 15 minutes, so 20 minutes is not idle yet
    assert await end_idle_sessions(session_factory, vapi, llm, _later(20)) == []

    assert len(await end_idle_sessions(session_factory, vapi, llm, _later(31))) == 1
    detail = await _status(client, trainee, session_id)
    assert detail["status"] == "evaluated"
    assert len(detail["messages"]) == 5
    assert vapi.deleted == ["asst_1"]

    async with session_factory() as db:
        record = (await db.execute(UsageRecord.__table__.select())).one()
        assert record.kind == "voice"
        assert float(record.cost_usd) == 0.12


async def test_voice_session_without_a_call(client, session_factory, llm, vapi):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    scenario_id = await _scenario_id(client, trainee)
    session_id = await _play(client, trainee, scenario_id, messages=())
    await client.post(f"/api/v1/simulations/{session_id}/voice", headers=trainee)

    async def no_call(assistant_id):
        return None

    vapi.latest_call = no_call
    assert len(await end_idle_sessions(session_factory, vapi, llm, _later(31))) == 1
    assert (await _status(client, trainee, session_id))["status"] == "completed"
    assert vapi.deleted == ["asst_1"]
    assert llm.evaluation_calls == 0
