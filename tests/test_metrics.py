# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Company metrics, and scenarios scored on the metrics they pick."""

import json

from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    _play,
    _scenario_id,
    client,
    llm,
    session_factory,
)

UPSELL = {
    "name": "Upselling",
    "description": "Offers a relevant upgrade once the problem is solved.",
}


async def test_defaults_and_own_metrics(client, session_factory):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    trainee = await _auth(client, "trainee@acme.com")

    metrics = (await client.get("/api/v1/metrics/", headers=trainee)).json()
    assert len(metrics) == 7 and all(m["is_default"] for m in metrics)

    assert (
        await client.post("/api/v1/metrics/", json=UPSELL, headers=trainee)
    ).status_code == 403
    created = await client.post("/api/v1/metrics/", json=UPSELL, headers=manager)
    assert created.status_code == 201, created.text
    assert created.json()["key"] == "upselling"

    again = await client.post("/api/v1/metrics/", json=UPSELL, headers=manager)
    assert again.status_code == 409
    default_name = await client.post(
        "/api/v1/metrics/",
        json={**UPSELL, "name": "Empathy"},
        headers=manager,
    )
    assert default_name.status_code == 409

    renamed = await client.patch(
        f"/api/v1/metrics/{created.json()['id']}",
        json={"name": "Upsell"},
        headers=manager,
    )
    assert renamed.json() == {**created.json(), "name": "Upsell"}

    other_org = await _make_org(session_factory, name="Other")  # noqa: F841
    other = await _auth(client, "manager@other.com")
    names = [
        m["name"] for m in (await client.get("/api/v1/metrics/", headers=other)).json()
    ]
    assert "Upsell" not in names
    assert (
        await client.delete(f"/api/v1/metrics/{created.json()['id']}", headers=other)
    ).status_code == 404


async def test_scenario_is_scored_on_its_metrics(client, session_factory, llm):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    trainee = await _auth(client, "trainee@acme.com")
    upsell = (
        await client.post("/api/v1/metrics/", json=UPSELL, headers=manager)
    ).json()
    scenario_id = await _scenario_id(client, trainee)

    unknown = await client.patch(
        f"/api/v1/scenarios/{scenario_id}",
        json={"metrics": ["empathy", "nope"]},
        headers=manager,
    )
    assert unknown.status_code == 422

    patched = await client.patch(
        f"/api/v1/scenarios/{scenario_id}",
        json={"metrics": ["empathy", "upselling", "empathy"]},
        headers=manager,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["metrics"] == ["empathy", "upselling"]

    brief = (
        await client.get(f"/api/v1/scenarios/{scenario_id}", headers=trainee)
    ).json()
    assert brief["metrics"] == [
        {"id": "empathy", "name": "Empathy"},
        {"id": "upselling", "name": "Upselling"},
    ]

    session_id = await _play(client, trainee, scenario_id)
    llm.evaluations.append(
        json.dumps(
            {
                "summary": "Good.",
                "dimensions": {
                    "empathy": {"score": 90, "rationale": "Kind"},
                    "upselling": {"score": 50, "rationale": "Late"},
                },
            }
        )
    )
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)
    evaluation = (
        await client.get(
            f"/api/v1/simulations/{session_id}/evaluation", headers=trainee
        )
    ).json()
    assert [
        (d["dimension_key"], d["score"]) for d in evaluation["dimension_scores"]
    ] == [
        ("empathy", 90),
        ("upselling", 50),
    ]
    assert evaluation["overall_score"] == 70

    progress = (await client.get("/api/v1/progress/me", headers=trainee)).json()
    assert [(d["id"], d["name"]) for d in progress["dimensions"]] == [
        ("empathy", "Empathy"),
        ("upselling", "Upselling"),
    ]

    # Deleting the metric takes it off the scenario
    await client.delete(f"/api/v1/metrics/{upsell['id']}", headers=manager)
    manage = (
        await client.get(f"/api/v1/scenarios/{scenario_id}/manage", headers=manager)
    ).json()
    assert manage["metrics"] == ["empathy"]


async def test_scenario_without_metrics_uses_the_defaults(client, session_factory):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    scenarios = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    assert len(scenarios[0]["metrics"]) == 7
