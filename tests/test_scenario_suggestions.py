# ruff: noqa: F811  (pytest fixtures shared with other tests)
"""AI-suggested scenarios from the knowledge base."""

import json

import pytest

from src.domains.scenarios import suggestions
from tests.test_knowledge_base import _upload, kb, make_docx  # noqa: F401
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    client,
    llm,
    session_factory,
)


def draft(name, situation, **extra):
    return {
        "name": name,
        "description": f"A customer asks about {name.lower()}.",
        "category": "policy_compliance",
        "difficulty": "beginner",
        "persona": "frustrated",
        "skills": ["policy", "not-a-skill"],
        "metrics": ["policy", "made_up"],
        "estimated_minutes": 10,
        "situation": situation,
        "trainee_objective": "Explain the policy and help the customer.",
        "important_information": [{"label": "Rule", "content": "30 days"}, "junk"],
        **extra,
    }


class FakeWriter:
    def __init__(self, scenarios):
        self.reply = json.dumps({"scenarios": scenarios})
        self.prompts = []

    async def generate_response(self, system_prompt, messages, **kwargs):
        self.prompts.append(messages[0]["content"])
        return self.reply


@pytest.fixture
def writer(monkeypatch):
    fake = FakeWriter(
        [
            draft(
                "Late refund request",
                "The customer wants a refund 40 days after buying a kettle.",
            ),
            draft(
                "Late refund request again",
                "The customer wants a refund 40 days after buying a kettle.",
            ),
            draft(
                "Password reset by phone",
                "A caller asks the agent to read out the account password.",
            ),
            {"name": "x"},  # invalid, dropped
        ]
    )
    monkeypatch.setattr(suggestions, "_llm_provider", fake)
    return fake


async def test_needs_a_knowledge_base(client, session_factory, writer):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    response = await client.post(
        "/api/v1/scenarios/suggestions", json={"count": 2}, headers=manager
    )
    assert response.status_code == 400
    assert "knowledge base" in response.json()["detail"]


async def test_suggestions_are_valid_and_not_duplicates(
    client, session_factory, writer
):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    trainee = await _auth(client, "trainee@acme.com")
    await _upload(
        client,
        manager,
        "policy.docx",
        make_docx("Refunds within 30 days only.", "Never read out passwords."),
    )

    assert (
        await client.post("/api/v1/scenarios/suggestions", json={}, headers=trainee)
    ).status_code == 403

    response = await client.post(
        "/api/v1/scenarios/suggestions", json={"count": 3}, headers=manager
    )
    assert response.status_code == 200, response.text
    result = response.json()
    names = [s["name"] for s in result["suggestions"]]
    assert names == ["Late refund request", "Password reset by phone"]
    assert result["skipped_similar"] == 1
    first = result["suggestions"][0]
    assert first["skills"] == ["policy"]
    assert first["metrics"] == ["policy"]
    assert first["important_information"] == [{"label": "Rule", "content": "30 days"}]

    prompt = writer.prompts[-1]
    assert "Never read out passwords." in prompt
    assert "SaaS Subscription Cancellation" in prompt  # existing scenarios listed

    # A draft can be saved as is
    created = await client.post("/api/v1/scenarios/", json=first, headers=manager)
    assert created.status_code == 201, created.text

    # Now the saved one counts as existing
    again = (
        await client.post(
            "/api/v1/scenarios/suggestions", json={"count": 3}, headers=manager
        )
    ).json()
    assert [s["name"] for s in again["suggestions"]] == ["Password reset by phone"]


async def test_requested_category_and_metrics_win(client, session_factory, writer):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    await _upload(client, manager, "p.docx", make_docx("Refunds within 30 days."))

    response = await client.post(
        "/api/v1/scenarios/suggestions",
        json={"count": 1, "category": "empathy", "metrics": ["empathy", "clarity"]},
        headers=manager,
    )
    [only] = response.json()["suggestions"]
    assert only["category"] == "empathy"
    assert only["metrics"] == ["empathy", "clarity"]

    unknown = await client.post(
        "/api/v1/scenarios/suggestions", json={"metrics": ["nope"]}, headers=manager
    )
    assert unknown.status_code == 422
