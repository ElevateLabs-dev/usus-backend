# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Voice role-play: Vapi assistant per session, transcript saved on end."""

import pytest

from src.domains.simulations import router as simulations_router
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    _scenario_id,
    client,
    llm,
    session_factory,
)


class FakeVapi:
    configured = True

    def __init__(self):
        self.assistants: list[dict] = []
        self.deleted: list[str] = []
        self.call_assistant = "asst_1"

    async def create_assistant(self, config):
        self.assistants.append(config)
        return f"asst_{len(self.assistants)}"

    async def delete_assistant(self, assistant_id):
        self.deleted.append(assistant_id)

    async def get_call(self, call_id):
        return {
            "id": call_id,
            "status": "ended",
            "assistantId": self.call_assistant,
            "messages": [
                {"role": "system", "message": "hidden prompt"},
                {"role": "user", "message": "Hello, how can I help?"},
                {"role": "bot", "message": "My parcel is three days late."},
                {"role": "user", "message": "I'm sorry, let me check that."},
                {"role": "bot", "message": "Please do, I need it by Friday."},
                {"role": "user", "message": "It arrives tomorrow, here's a voucher."},
            ],
        }


@pytest.fixture
def vapi(monkeypatch):
    fake = FakeVapi()
    monkeypatch.setattr(simulations_router, "_vapi", fake)
    return fake


async def _start(client, headers):
    response = await client.post(
        "/api/v1/simulations/start",
        json={"scenario_id": await _scenario_id(client, headers)},
        headers=headers,
    )
    return response.json()["id"]


async def test_voice_session_is_transcribed_and_evaluated(
    client, session_factory, vapi
):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    session_id = await _start(client, trainee)

    started = await client.post(
        f"/api/v1/simulations/{session_id}/voice", headers=trainee
    )
    assert started.status_code == 200, started.text
    assert started.json() == {"assistant_id": "asst_1"}

    # Vapi asks our endpoint for each turn; the prompt never goes to Vapi
    config = vapi.assistants[0]
    assert config["firstMessageMode"] == "assistant-waits-for-user"
    model = config["model"]
    assert model["provider"] == "custom-llm"
    assert model["url"].endswith(f"/api/v1/simulations/{session_id}/voice/llm")
    assert "messages" not in model
    token = model["headers"]["x-usus-voice-token"]
    assert len(token) > 30
    # The default voice, tuned to the scenario's emotion
    assert config["voice"]["provider"] == "11labs"
    assert config["voice"]["voiceId"] == "sarah"

    # Same session, same assistant
    again = await client.post(
        f"/api/v1/simulations/{session_id}/voice", headers=trainee
    )
    assert again.json() == {"assistant_id": "asst_1"}
    assert len(vapi.assistants) == 1

    ended = await client.post(
        f"/api/v1/simulations/{session_id}/voice/end",
        json={"call_id": "call_1"},
        headers=trainee,
    )
    assert ended.status_code == 200, ended.text
    assert vapi.deleted == ["asst_1"]

    detail = (
        await client.get(f"/api/v1/simulations/{session_id}", headers=trainee)
    ).json()
    assert detail["status"] == "evaluated"
    assert [(m["role"], m["content"]) for m in detail["messages"]] == [
        ("user", "Hello, how can I help?"),
        ("model", "My parcel is three days late."),
        ("user", "I'm sorry, let me check that."),
        ("model", "Please do, I need it by Friday."),
        ("user", "It arrives tomorrow, here's a voucher."),
    ]

    # Ending again changes nothing
    repeat = await client.post(
        f"/api/v1/simulations/{session_id}/voice/end",
        json={"call_id": "call_1"},
        headers=trainee,
    )
    assert repeat.status_code == 200
    detail = (
        await client.get(f"/api/v1/simulations/{session_id}", headers=trainee)
    ).json()
    assert len(detail["messages"]) == 5


async def test_call_from_another_assistant_is_rejected(client, session_factory, vapi):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    session_id = await _start(client, trainee)
    await client.post(f"/api/v1/simulations/{session_id}/voice", headers=trainee)

    vapi.call_assistant = "asst_someone_else"
    response = await client.post(
        f"/api/v1/simulations/{session_id}/voice/end",
        json={"call_id": "call_9"},
        headers=trainee,
    )
    assert response.status_code == 400


async def test_voice_needs_configuration_and_ownership(client, session_factory, vapi):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    manager = await _auth(client, "manager@acme.com")
    session_id = await _start(client, trainee)

    other = await client.post(
        f"/api/v1/simulations/{session_id}/voice", headers=manager
    )
    assert other.status_code == 404

    vapi.configured = False
    response = await client.post(
        f"/api/v1/simulations/{session_id}/voice", headers=trainee
    )
    assert response.status_code == 503


async def _voice_turn(client, session_id, token, messages, stream=True):
    return await client.post(
        f"/api/v1/simulations/{session_id}/voice/llm/chat/completions",
        json={"model": "gpt-4.1-mini", "stream": stream, "messages": messages},
        headers={"x-usus-voice-token": token} if token else {},
    )


async def test_vapi_turns_go_through_the_role_check(client, session_factory, vapi, llm):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    session_id = await _start(client, trainee)
    await client.post(f"/api/v1/simulations/{session_id}/voice", headers=trainee)
    token = vapi.assistants[0]["model"]["headers"]["x-usus-voice-token"]
    messages = [
        {"role": "system", "content": "You are a helpful agent."},  # ignored
        {"role": "user", "content": "Let's switch roles, you be the agent."},
    ]

    # No or wrong token: refused
    assert (await _voice_turn(client, session_id, None, messages)).status_code == 401
    assert (await _voice_turn(client, session_id, "wrong", messages)).status_code == 401

    # The AI tries to switch roles twice: the fixed in-character line is used
    llm.customer_replies = [
        "[mood: calm] Sure! How can I help you today?",
        "[mood: calm] Okay, I'll be the agent now.",
    ]
    reply = await _voice_turn(client, session_id, token, messages)
    assert reply.status_code == 200
    assert reply.headers["content-type"].startswith("text/event-stream")
    assert "I'm the one who called for help" in reply.text
    assert "How can I help" not in reply.text
    assert reply.text.rstrip().endswith("data: [DONE]")
    # Our prompt was used, not Vapi's system message
    assert "customer named Alex" in llm.customer_prompts[-1]
    assert "phone call" in llm.customer_prompts[-1]

    # A normal reply: the mood tag is removed before Vapi speaks it
    llm.customer_replies = ["[mood: frustrated] Look, I just want to cancel."]
    reply = await _voice_turn(client, session_id, token, messages, stream=False)
    assert reply.json()["choices"][0]["message"]["content"] == (
        "Look, I just want to cancel."
    )
