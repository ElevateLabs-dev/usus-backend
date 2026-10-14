"""
Platform admin APIs: status, activity, alerts, maintenance mode, platform
admins, and managing an organization's company admins.

Reuses the in-memory app setup from test_management.
"""

# ruff: noqa: F811  (fixtures imported from test_management)

from datetime import datetime, timedelta, timezone

import pytest_asyncio
from sqlalchemy import update

from src.domains.platform import router as platform_router
from src.domains.users.models import User
from tests.test_management import (  # noqa: F401  (client, outbox, ... are fixtures)
    ROOT,
    _activate,
    _auth,
    _onboard,
    client,
    llm,
    outbox,
    session_factory,
)


@pytest_asyncio.fixture
async def api(client, session_factory, monkeypatch):
    monkeypatch.setattr(platform_router, "_session_factory", session_factory)
    return client


async def test_status_activity_and_admin_only_access(api, outbox):
    org, admin = await _onboard(api, outbox)
    root = await _auth(api, ROOT)

    status = await api.get("/api/v1/platform/status", headers=root)
    assert status.status_code == 200, status.text
    body = status.json()
    checks = {check["name"]: check["state"] for check in body["checks"]}
    assert checks["api"] == "ok" and checks["database"] == "ok"
    assert set(checks) == {"api", "database", "email", "ai"}
    assert body["maintenance_mode"] is False
    assert body["overall"] in {"operational", "degraded"}

    activity = (await api.get("/api/v1/platform/activity", headers=root)).json()
    types = {item["type"] for item in activity}
    assert {"organization_created", "user_added"} <= types
    onboarded = next(i for i in activity if i["type"] == "organization_created")
    assert onboarded["organization_name"] == "Acme"

    for path in ("status", "activity", "alerts", "settings", "admins"):
        response = await api.get(f"/api/v1/platform/{path}", headers=admin)
        assert response.status_code == 403, path


async def test_undelivered_invites_are_reported(api, outbox, session_factory):
    root = await _auth(api, ROOT)
    org = await api.post(
        "/api/v1/organizations/",
        json={"name": "Acme", "admin_email": "admin@acme.com"},
        headers=root,
    )
    assert (await api.get("/api/v1/platform/alerts", headers=root)).json() == []

    # The invite email "failed" a while ago
    async with session_factory() as db:
        await db.execute(
            update(User)
            .where(User.email == "admin@acme.com")
            .values(
                invite_sent_at=None,
                created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        )
        await db.commit()

    alerts = (await api.get("/api/v1/platform/alerts", headers=root)).json()
    assert [(a["type"], a["organization_name"]) for a in alerts] == [
        ("invite_not_delivered", "Acme")
    ]

    # Resending it clears the alert
    user_id = org.json()["staff"][0]["id"]
    resent = await api.post(
        f"/api/v1/organizations/{org.json()['id']}/users/{user_id}/resend-invite",
        headers=root,
    )
    assert resent.status_code == 202
    assert (await api.get("/api/v1/platform/alerts", headers=root)).json() == []


async def test_maintenance_mode_locks_out_everyone_but_platform_admins(api, outbox):
    org, admin = await _onboard(api, outbox)
    root = await _auth(api, ROOT)

    on = await api.patch(
        "/api/v1/platform/settings", json={"maintenance_mode": True}, headers=root
    )
    assert on.status_code == 200 and on.json()["maintenance_mode"] is True

    assert (await api.get("/api/v1/scenarios/", headers=admin)).status_code == 503
    login = await api.post(
        "/api/v1/auth/token",
        data={"username": "admin@acme.com", "password": "password-123"},
    )
    assert login.status_code == 503
    # Platform admins keep working
    assert (await api.get("/api/v1/organizations/", headers=root)).status_code == 200
    status = (await api.get("/api/v1/platform/status", headers=root)).json()
    assert status["overall"] == "maintenance"

    await api.patch(
        "/api/v1/platform/settings", json={"maintenance_mode": False}, headers=root
    )
    assert (await api.get("/api/v1/scenarios/", headers=admin)).status_code == 200


async def test_platform_admins_can_be_added_and_deactivated(api, outbox):
    root = await _auth(api, ROOT)

    added = await api.post(
        "/api/v1/platform/admins",
        json={"email": "Ops@Usus.com", "full_name": "Chidi"},
        headers=root,
    )
    assert added.status_code == 201, added.text
    ops_id = added.json()["id"]
    assert added.json()["role"] == "platform_admin"
    assert outbox[-1]["to"] == "ops@usus.com"
    assert "The Usus team" in outbox[-1]["body"]

    duplicate = await api.post(
        "/api/v1/platform/admins", json={"email": "ops@usus.com"}, headers=root
    )
    assert duplicate.status_code == 409

    ops = await _activate(api, outbox, "ops@usus.com")
    listed = (await api.get("/api/v1/platform/admins", headers=ops)).json()
    assert {a["email"] for a in listed} == {ROOT, "ops@usus.com"}

    root_id = next(a["id"] for a in listed if a["email"] == ROOT)
    self_off = await api.patch(
        f"/api/v1/platform/admins/{root_id}", json={"is_active": False}, headers=root
    )
    assert self_off.status_code == 400

    off = await api.patch(
        f"/api/v1/platform/admins/{ops_id}", json={"is_active": False}, headers=root
    )
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert (await api.get("/api/v1/platform/admins", headers=ops)).status_code == 401

    resent = await api.post(
        f"/api/v1/platform/admins/{ops_id}/resend-invite", headers=root
    )
    assert resent.status_code == 202


async def test_platform_admin_manages_company_admins(api, outbox):
    org, admin = await _onboard(api, outbox)
    root = await _auth(api, ROOT)
    base = f"/api/v1/organizations/{org['id']}"
    first_admin_id = org["staff"][0]["id"]

    # The only company admin cannot be deactivated
    last = await api.patch(
        f"{base}/users/{first_admin_id}", json={"is_active": False}, headers=root
    )
    assert last.status_code == 409

    second = await api.post(
        f"{base}/admins",
        json={"email": "second@acme.com", "full_name": "Bola"},
        headers=root,
    )
    assert second.status_code == 201 and second.json()["role"] == "company_admin"
    assert outbox[-1]["to"] == "second@acme.com"
    taken = await api.post(
        f"{base}/admins", json={"email": "second@acme.com"}, headers=root
    )
    assert taken.status_code == 409

    off = await api.patch(
        f"{base}/users/{first_admin_id}", json={"is_active": False}, headers=root
    )
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert (await api.get("/api/v1/scenarios/", headers=admin)).status_code == 401

    # Users of another organization are not reachable through this one
    other, _ = await _onboard(api, outbox, name="Beta", admin_email="admin@beta.com")
    stranger = other["staff"][0]["id"]
    assert (
        await api.post(f"{base}/users/{stranger}/resend-invite", headers=root)
    ).status_code == 404
