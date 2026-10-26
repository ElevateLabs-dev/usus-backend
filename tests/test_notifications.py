# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Notifications: evaluation ready, session completed, new scenario."""

from src.domains.scenarios import router as scenarios_router
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    _play,
    _scenario_id,
    client,
    llm,
    session_factory,
)


async def _notifications(client, headers):
    response = await client.get("/api/v1/notifications/", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_evaluation_notifies_trainee_and_manager(client, session_factory):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    manager = await _auth(client, "manager@acme.com")

    session_id = await _play(client, trainee, await _scenario_id(client, trainee))
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)

    mine = await _notifications(client, trainee)
    assert mine["unread_count"] == 1
    assert mine["items"][0]["kind"] == "evaluation_ready"
    assert mine["items"][0]["link"] == f"/history/{session_id}"
    assert "SaaS Subscription Cancellation" in mine["items"][0]["body"]

    team = await _notifications(client, manager)
    assert team["unread_count"] == 1
    assert team["items"][0]["kind"] == "session_completed"
    assert team["items"][0]["link"].startswith("/manager/performance/")


async def test_new_scenario_notifies_trainees(client, session_factory):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    manager = await _auth(client, "manager@acme.com")

    created = await client.post(
        "/api/v1/scenarios/",
        json={
            "name": "Lost Parcel",
            "description": "A parcel never arrived.",
            "category": "problem_resolution",
            "difficulty": "beginner",
            "persona": "frustrated",
            "situation": "The tracking says delivered.",
            "trainee_objective": "Find a fair resolution.",
        },
        headers=manager,
    )
    assert created.status_code == 201, created.text

    mine = await _notifications(client, trainee)
    assert [n["kind"] for n in mine["items"]] == ["scenario_added"]
    assert mine["items"][0]["link"] == f"/scenarios/{created.json()['id']}"
    assert (await _notifications(client, manager))["unread_count"] == 0


async def test_mark_read(client, session_factory):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    manager = await _auth(client, "manager@acme.com")

    for _ in range(2):
        session_id = await _play(client, trainee, await _scenario_id(client, trainee))
        await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)

    items = (await _notifications(client, trainee))["items"]
    first = items[0]["id"]

    # Someone else's notification is not found
    other = await client.post(f"/api/v1/notifications/{first}/read", headers=manager)
    assert other.status_code == 404

    read = await client.post(f"/api/v1/notifications/{first}/read", headers=trainee)
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    assert (await _notifications(client, trainee))["unread_count"] == 1

    response = await client.post("/api/v1/notifications/read-all", headers=trainee)
    assert response.status_code == 204
    assert (await _notifications(client, trainee))["unread_count"] == 0


async def test_scenario_is_created_even_if_notifying_fails(
    client, session_factory, monkeypatch
):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")

    def broken_factory():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(scenarios_router, "_session_factory", broken_factory)
    created = await client.post(
        "/api/v1/scenarios/",
        json={
            "name": "Lost Parcel",
            "description": "A parcel never arrived.",
            "category": "problem_resolution",
            "difficulty": "beginner",
            "persona": "frustrated",
            "situation": "The tracking says delivered.",
            "trainee_objective": "Find a fair resolution.",
        },
        headers=manager,
    )
    assert created.status_code == 201, created.text
    assert created.json()["name"] == "Lost Parcel"
