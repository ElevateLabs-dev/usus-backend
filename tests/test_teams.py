# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Teams: membership, team-only scenarios, and invites into a team."""

from src.core.config import settings
from src.domains.users import router as users_router
from src.domains.users import service as users_service
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    _scenario_id,
    client,
    llm,
    session_factory,
)


async def _ids(client, headers, path):
    return {
        item["email"]: item["id"]
        for item in (await client.get(path, headers=headers)).json()
    }


async def test_team_scenarios_are_only_shown_to_the_team(client, session_factory):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    trainee = await _auth(client, "trainee@acme.com")
    users = await _ids(client, manager, "/api/v1/users/")

    everyone = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    scenario_id = await _scenario_id(client, trainee)

    team = (
        await client.post("/api/v1/teams/", json={"name": "Billing"}, headers=manager)
    ).json()
    assert (
        await client.post("/api/v1/teams/", json={"name": "billing"}, headers=manager)
    ).status_code == 409
    assert (await client.get("/api/v1/teams/", headers=trainee)).status_code == 403

    # Assigned to a team the trainee is not in: hidden from them
    response = await client.put(
        f"/api/v1/teams/{team['id']}/scenarios",
        json={"scenario_ids": [scenario_id]},
        headers=manager,
    )
    assert response.json()["scenario_count"] == 1
    visible = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    assert len(visible) == len(everyone) - 1
    assert (
        await client.get(f"/api/v1/scenarios/{scenario_id}", headers=trainee)
    ).status_code == 404
    start = await client.post(
        "/api/v1/simulations/start", json={"scenario_id": scenario_id}, headers=trainee
    )
    assert start.status_code == 404
    # Staff still see everything
    assert len((await client.get("/api/v1/scenarios/", headers=manager)).json()) == len(
        everyone
    )

    # Join the team: visible again
    response = await client.post(
        f"/api/v1/teams/{team['id']}/members",
        json={"user_ids": [users["trainee@acme.com"]]},
        headers=manager,
    )
    assert [m["email"] for m in response.json()["members"]] == ["trainee@acme.com"]
    assert len((await client.get("/api/v1/scenarios/", headers=trainee)).json()) == len(
        everyone
    )
    assert (
        await client.get(f"/api/v1/scenarios/{scenario_id}", headers=trainee)
    ).status_code == 200

    # Removing the member hides it again; deleting the team shows it to everyone
    await client.delete(
        f"/api/v1/teams/{team['id']}/members/{users['trainee@acme.com']}",
        headers=manager,
    )
    assert len((await client.get("/api/v1/scenarios/", headers=trainee)).json()) == (
        len(everyone) - 1
    )
    await client.delete(f"/api/v1/teams/{team['id']}", headers=manager)
    assert len((await client.get("/api/v1/scenarios/", headers=trainee)).json()) == len(
        everyone
    )


async def test_teams_belong_to_one_organization(client, session_factory):
    await _make_org(session_factory)
    await _make_org(session_factory, name="Other")
    manager = await _auth(client, "manager@acme.com")
    other = await _auth(client, "manager@other.com")
    other_users = await _ids(client, other, "/api/v1/users/")

    team = (
        await client.post("/api/v1/teams/", json={"name": "Sales"}, headers=manager)
    ).json()
    assert (
        await client.get(f"/api/v1/teams/{team['id']}", headers=other)
    ).status_code == 404
    response = await client.post(
        f"/api/v1/teams/{team['id']}/members",
        json={"user_ids": [other_users["trainee@other.com"]]},
        headers=manager,
    )
    assert response.status_code == 422


async def test_invite_into_a_team_emails_team_and_video(
    client, session_factory, monkeypatch
):
    sent = []
    monkeypatch.setattr(
        users_service, "send_email", lambda to, subject, body: sent.append(body)
    )
    monkeypatch.setattr(users_router, "_session_factory", session_factory)
    monkeypatch.setattr(settings, "INTRO_VIDEO_URL", "https://youtu.be/intro")

    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    team = (
        await client.post("/api/v1/teams/", json={"name": "Billing"}, headers=manager)
    ).json()

    response = await client.post(
        "/api/v1/users/trainees",
        json={"email": "new@acme.com", "full_name": "New", "team_ids": [team["id"]]},
        headers=manager,
    )
    assert response.status_code == 201, response.text
    detail = (await client.get(f"/api/v1/teams/{team['id']}", headers=manager)).json()
    assert [m["email"] for m in detail["members"]] == ["new@acme.com"]

    body = sent[-1]
    assert "You are in the Billing team." in body
    assert "https://youtu.be/intro" in body
    assert "Temporary password:" in body

    bulk = await client.post(
        "/api/v1/users/trainees/bulk",
        json={"trainees": [{"email": "two@acme.com"}], "team_ids": [team["id"]]},
        headers=manager,
    )
    assert bulk.status_code == 201
    detail = (await client.get(f"/api/v1/teams/{team['id']}", headers=manager)).json()
    assert detail["member_count"] == 2

    unknown = await client.post(
        "/api/v1/users/",
        json={"email": "x@acme.com", "team_ids": [users_router.uuid.uuid4().hex]},
        headers=manager,
    )
    assert unknown.status_code == 422
