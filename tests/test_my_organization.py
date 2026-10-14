"""
Company admins and managers see their own organization; company admins can
rename it. Reuses the in-memory app setup from test_management.
"""

# ruff: noqa: F811  (fixtures imported from test_management)

from tests.test_management import (  # noqa: F401  (client, outbox, ... are fixtures)
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


async def test_staff_see_their_own_organization(client, outbox):
    org, admin = await _onboard(client, outbox)
    await _invite(client, admin, "lead@acme.com", "manager")
    manager = await _activate(client, outbox, "lead@acme.com")

    for headers in (admin, manager):
        mine = await client.get("/api/v1/organizations/me", headers=headers)
        assert mine.status_code == 200, mine.text
        body = mine.json()
        assert body["id"] == org["id"] and body["name"] == "Acme"
        assert body["scenarios_count"] == 5 and body["users_count"] == 2
        assert {u["role"] for u in body["staff"]} == {"company_admin", "manager"}

    # Trainees and platform admins have no "my organization" view
    await _invite(client, admin, "trainee@acme.com", "trainee")
    trainee = await _activate(client, outbox, "trainee@acme.com")
    assert (
        await client.get("/api/v1/organizations/me", headers=trainee)
    ).status_code == 403
    root = await _auth(client, ROOT)
    assert (
        await client.get("/api/v1/organizations/me", headers=root)
    ).status_code == 403


async def test_company_admin_renames_their_organization(client, outbox):
    org, admin = await _onboard(client, outbox)
    await _onboard(client, outbox, name="Beta", admin_email="admin@beta.com")

    renamed = await client.patch(
        "/api/v1/organizations/me", json={"name": "Acme Retail"}, headers=admin
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Acme Retail"

    taken = await client.patch(
        "/api/v1/organizations/me", json={"name": "beta"}, headers=admin
    )
    assert taken.status_code == 409

    await _invite(client, admin, "lead@acme.com", "manager")
    manager = await _activate(client, outbox, "lead@acme.com")
    assert (
        await client.patch(
            "/api/v1/organizations/me", json={"name": "Nope"}, headers=manager
        )
    ).status_code == 403
