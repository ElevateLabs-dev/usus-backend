# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Short sessions score 0; levels unlock by passing the level before."""

from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    _play,
    _scenario_id,
    client,
    evaluation_json,
    llm,
    session_factory,
)

BEGINNER = ("SaaS Subscription Cancellation", "Elderly Customer Locked Out")


async def _start(client, headers, name):
    return await client.post(
        "/api/v1/simulations/start",
        json={"scenario_id": await _scenario_id(client, headers, name)},
        headers=headers,
    )


async def _finish(client, headers, name):
    session_id = await _play(client, headers, await _scenario_id(client, headers, name))
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=headers)
    return session_id


async def test_saying_hi_and_ending_scores_zero(client, session_factory, llm):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    scenario_id = await _scenario_id(client, trainee)

    session_id = await _play(client, trainee, scenario_id, ["hi"])
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)

    evaluation = (
        await client.get(
            f"/api/v1/simulations/{session_id}/evaluation", headers=trainee
        )
    ).json()
    assert evaluation["overall_score"] == 0
    assert "too short" in evaluation["dimension_scores"][0]["rationale"]
    assert llm.evaluation_calls == 0  # no LLM call needed


async def test_levels_unlock_by_passing_the_level_before(client, session_factory, llm):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")

    scenarios = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    locked = {s["name"]: s["locked"] for s in scenarios}
    assert locked["SaaS Subscription Cancellation"] is False
    assert locked["Late Delivery Complaint"] is True
    assert locked["Double Billing Dispute"] is True
    intermediate = next(s for s in scenarios if s["difficulty"] == "intermediate")
    assert "Beginner" in intermediate["locked_reason"]

    refused = await _start(client, trainee, "Late Delivery Complaint")
    assert refused.status_code == 403
    assert "Beginner" in refused.json()["detail"]

    # A low score does not pass
    llm.evaluations.append(
        evaluation_json(
            {
                k: 40
                for k in (
                    "accuracy",
                    "empathy",
                    "clarity",
                    "policy",
                    "resolution",
                    "de_escalation",
                    "efficiency",
                )
            }
        )
    )
    await _finish(client, trainee, BEGINNER[0])
    await _finish(client, trainee, BEGINNER[1])
    scenarios = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    saas = next(s for s in scenarios if s["name"] == BEGINNER[0])
    assert saas["progress"]["status"] == "in_progress"  # tried, not passed
    assert (await _start(client, trainee, "Late Delivery Complaint")).status_code == 403

    # Passing every Beginner scenario unlocks Intermediate, not Advanced
    await _finish(client, trainee, BEGINNER[0])
    scenarios = (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    by_name = {s["name"]: s for s in scenarios}
    assert by_name[BEGINNER[0]]["progress"]["status"] == "completed"
    assert by_name["Late Delivery Complaint"]["locked"] is False
    assert by_name["Double Billing Dispute"]["locked"] is True
    assert (await _start(client, trainee, "Late Delivery Complaint")).status_code == 201


async def test_staff_are_never_locked(client, session_factory):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    scenarios = (await client.get("/api/v1/scenarios/", headers=manager)).json()
    assert not any(s["locked"] for s in scenarios)
    assert (await _start(client, manager, "Double Billing Dispute")).status_code == 201
