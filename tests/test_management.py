"""
Management APIs:
- platform admins onboard and (de)activate organizations
- company admins / managers manage their organization's users
- company admins / managers create, edit and archive scenarios

Runs on in-memory SQLite; emails are captured and the LLM is faked.
"""

import re

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.domains.evaluations.models  # noqa: F401  (register all tables)
from src.core.base_model import Base
from src.core.database import get_db
from src.core.security import hash_password
from src.domains.scenarios import router as scenarios_router
from src.domains.simulations import router as simulations_router
from src.domains.tenants import router as organizations_router
from src.domains.users import router as users_router
from src.domains.users import service as users_service
from src.domains.users.models import User
from src.infrastructure.llm.base import LLMProvider
from src.main import app

PASSWORD = "password-123"
ROOT = "root@usus.com"


class FakeLLM(LLMProvider):
    def __init__(self):
        self.customer_prompts: list[str] = []

    async def generate_response(
        self, system_prompt, messages, temperature=0.7, max_tokens=1024, json_mode=False
    ):
        self.customer_prompts.append(system_prompt)
        return "I'm not happy about this."


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        db.add(
            User(
                email=ROOT,
                hashed_password=hash_password(PASSWORD),
                role="platform_admin",
                tenant_id=None,
            )
        )
        await db.commit()
    yield factory
    await engine.dispose()


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(
        users_service,
        "send_email",
        lambda to, subject, body: sent.append({"to": to, "body": body}),
    )
    return sent


@pytest.fixture
def llm(monkeypatch):
    fake = FakeLLM()
    monkeypatch.setattr(simulations_router._simulation_service, "llm_provider", fake)
    return fake


@pytest_asyncio.fixture
async def client(session_factory, outbox, llm, monkeypatch):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    for module in (
        users_router,
        organizations_router,
        simulations_router,
        scenarios_router,
    ):
        monkeypatch.setattr(module, "_session_factory", session_factory)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


async def _login(client, email, password=PASSWORD):
    return await client.post(
        "/api/v1/auth/token", data={"username": email, "password": password}
    )


async def _auth(client, email, password=PASSWORD):
    response = await _login(client, email, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _activate(client, outbox, email):
    """Sign an invited user in with their emailed temporary password and set
    PASSWORD as their real one. Returns their auth headers."""
    body = next(m["body"] for m in reversed(outbox) if m["to"] == email)
    temporary = re.search(r"Temporary password: (\S+)", body).group(1)
    changed = await client.post(
        "/api/v1/auth/change-password",
        json={"current_password": temporary, "new_password": PASSWORD},
        headers=await _auth(client, email, temporary),
    )
    assert changed.status_code == 200, changed.text
    return {"Authorization": f"Bearer {changed.json()['access_token']}"}


async def _onboard(client, outbox, name="Acme", admin_email="admin@acme.com"):
    """Platform admin onboards an organization; returns (org, admin headers)."""
    root = await _auth(client, ROOT)
    created = await client.post(
        "/api/v1/organizations/",
        json={"name": name, "admin_email": admin_email, "admin_full_name": "Ada Obi"},
        headers=root,
    )
    assert created.status_code == 201, created.text
    return created.json(), await _activate(client, outbox, admin_email)


async def _invite(client, headers, email, role):
    return await client.post(
        "/api/v1/users/", json={"email": email, "role": role}, headers=headers
    )


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------


async def test_platform_admin_onboards_an_organization(client, outbox):
    org, admin = await _onboard(client, outbox)

    assert org["name"] == "Acme" and org["is_active"] is True
    assert org["scenarios_count"] == 5 and org["users_count"] == 1
    assert [(u["email"], u["role"]) for u in org["staff"]] == [
        ("admin@acme.com", "company_admin")
    ]
    # The company admin was invited by email and can now work in their org
    assert outbox[0]["to"] == "admin@acme.com" and "Acme" in outbox[0]["body"]
    scenarios = await client.get("/api/v1/scenarios/", headers=admin)
    assert len(scenarios.json()) == 5

    root = await _auth(client, ROOT)
    same_name = await client.post(
        "/api/v1/organizations/",
        json={"name": "acme", "admin_email": "other@acme.com"},
        headers=root,
    )
    assert same_name.status_code == 409
    same_email = await client.post(
        "/api/v1/organizations/",
        json={"name": "Beta", "admin_email": "ADMIN@acme.com"},
        headers=root,
    )
    assert same_email.status_code == 409

    listed = (await client.get("/api/v1/organizations/", headers=root)).json()
    assert [(o["name"], o["users_count"]) for o in listed] == [("Acme", 1)]
    detail = await client.get(f"/api/v1/organizations/{org['id']}", headers=root)
    assert detail.json()["staff"][0]["must_change_password"] is False

    # Only platform admins can use these endpoints
    assert (
        await client.get("/api/v1/organizations/", headers=admin)
    ).status_code == 403


async def test_deactivating_an_organization_blocks_its_users_immediately(
    client, outbox
):
    org, admin = await _onboard(client, outbox)
    root = await _auth(client, ROOT)
    url = f"/api/v1/organizations/{org['id']}"

    off = await client.patch(url, json={"is_active": False}, headers=root)
    assert off.status_code == 200 and off.json()["is_active"] is False

    # The token issued before deactivation stops working at once
    blocked = await client.get("/api/v1/scenarios/", headers=admin)
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Your organization has been deactivated"
    assert (await _login(client, "admin@acme.com")).status_code == 403

    renamed = await client.patch(
        url, json={"is_active": True, "name": "Acme Retail"}, headers=root
    )
    assert renamed.json()["name"] == "Acme Retail"
    assert (await client.get("/api/v1/scenarios/", headers=admin)).status_code == 200


# ---------------------------------------------------------------------------
# Users inside an organization
# ---------------------------------------------------------------------------


async def test_roles_decide_who_can_invite_whom(client, outbox):
    _, admin = await _onboard(client, outbox)

    invited = await _invite(client, admin, "Lead@Acme.com", "manager")
    assert invited.status_code == 201
    assert invited.json()["email"] == "lead@acme.com"
    assert invited.json()["role"] == "manager"
    manager = await _activate(client, outbox, "lead@acme.com")

    assert (await _invite(client, manager, "t1@acme.com", "trainee")).status_code == 201
    refused = await _invite(client, manager, "boss@acme.com", "company_admin")
    assert refused.status_code == 403
    assert (await _invite(client, admin, "t1@acme.com", "trainee")).status_code == 409

    trainee = await _activate(client, outbox, "t1@acme.com")
    assert (await _invite(client, trainee, "t2@acme.com", "trainee")).status_code == 403

    renamed = await client.patch(
        "/api/v1/users/me", json={"full_name": "Tee One"}, headers=trainee
    )
    assert renamed.json()["full_name"] == "Tee One"


async def test_deactivating_and_changing_roles_apply_immediately(client, outbox):
    _, admin = await _onboard(client, outbox)
    trainee_id = (await _invite(client, admin, "t@acme.com", "trainee")).json()["id"]
    trainee = await _activate(client, outbox, "t@acme.com")
    url = f"/api/v1/users/{trainee_id}"

    off = await client.patch(url, json={"is_active": False}, headers=admin)
    assert off.json()["is_active"] is False
    assert (await client.get("/api/v1/users/me", headers=trainee)).status_code == 401
    assert (await _login(client, "t@acme.com")).status_code == 401

    await client.patch(url, json={"is_active": True}, headers=admin)
    assert (await client.get("/api/v1/users/me", headers=trainee)).status_code == 200

    # Promoted to manager: the same token now has manager rights
    assert (await client.get("/api/v1/users/", headers=trainee)).status_code == 403
    promoted = await client.patch(url, json={"role": "manager"}, headers=admin)
    assert promoted.json()["role"] == "manager"
    assert (await client.get("/api/v1/users/", headers=trainee)).status_code == 200


async def test_user_management_guards(client, outbox):
    org, admin = await _onboard(client, outbox)
    admin_id = org["staff"][0]["id"]
    manager_id = (await _invite(client, admin, "m@acme.com", "manager")).json()["id"]
    manager = await _activate(client, outbox, "m@acme.com")
    trainee_id = (await _invite(client, admin, "t@acme.com", "trainee")).json()["id"]

    me = f"/api/v1/users/{admin_id}"
    assert (
        await client.patch(me, json={"is_active": False}, headers=admin)
    ).status_code == 400
    assert (
        await client.patch(me, json={"role": "trainee"}, headers=admin)
    ).status_code == 400

    # Managers: trainees only, and never roles
    assert (
        await client.patch(
            f"/api/v1/users/{trainee_id}", json={"role": "manager"}, headers=manager
        )
    ).status_code == 403
    assert (
        await client.patch(me, json={"full_name": "x"}, headers=manager)
    ).status_code == 404
    assert (
        await client.patch(
            f"/api/v1/users/{trainee_id}", json={"full_name": "Tee"}, headers=manager
        )
    ).json()["full_name"] == "Tee"

    # Other organizations cannot see or manage these users
    _, other_admin = await _onboard(client, outbox, "Other Co", "admin@other.com")
    assert (
        await client.patch(
            f"/api/v1/users/{manager_id}",
            json={"is_active": False},
            headers=other_admin,
        )
    ).status_code == 404
    assert (
        await client.post(
            f"/api/v1/users/{manager_id}/resend-invite", headers=other_admin
        )
    ).status_code == 404


async def test_last_company_admin_cannot_be_removed(client, outbox):
    org, admin = await _onboard(client, outbox)
    second = (await _invite(client, admin, "a2@acme.com", "company_admin")).json()
    second_admin = await _activate(client, outbox, "a2@acme.com")
    first_id = org["staff"][0]["id"]

    # Second admin deactivates the first: fine, one admin remains
    off = await client.patch(
        f"/api/v1/users/{first_id}", json={"is_active": False}, headers=second_admin
    )
    assert off.status_code == 200

    # Platform admin acting in the org tries to demote the only one left
    root_login = await client.post(
        f"/api/v1/auth/token?tenant_id={org['id']}",
        data={"username": ROOT, "password": PASSWORD},
    )
    root_in_org = {"Authorization": f"Bearer {root_login.json()['access_token']}"}
    last = await client.patch(
        f"/api/v1/users/{second['id']}", json={"role": "manager"}, headers=root_in_org
    )
    assert last.status_code == 409


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

NEW_SCENARIO = {
    "name": "Failed Payment at Checkout",
    "description": "A customer's card was declined twice but shows a pending charge.",
    "category": "problem_resolution",
    "difficulty": "beginner",
    "persona": "frustrated",
    "skills": ["resolution", "accuracy"],
    "customer_name": "Chidi",
    "situation": "Checkout failed twice but the bank shows a pending charge.",
    "trainee_objective": "Reassure the customer and explain pending charges.",
    "important_information": [
        {"label": "Pending charges", "content": "Released within 3-5 business days."}
    ],
    "escalation_behavior": "Threatens to dispute the charge if answers are vague.",
    "success_criteria": "Explains the pending charge and gives a timeframe.",
}


async def test_scenario_create_edit_archive_and_restore(client, outbox, llm):
    _, admin = await _onboard(client, outbox)
    await _invite(client, admin, "t@acme.com", "trainee")
    trainee = await _activate(client, outbox, "t@acme.com")

    assert (
        await client.post("/api/v1/scenarios/", json=NEW_SCENARIO, headers=trainee)
    ).status_code == 403

    created = await client.post("/api/v1/scenarios/", json=NEW_SCENARIO, headers=admin)
    assert created.status_code == 201, created.text
    scenario = created.json()
    assert scenario["is_archived"] is False
    assert scenario["success_criteria"].startswith("Explains")
    url = f"/api/v1/scenarios/{scenario['id']}"
    assert (
        await client.post("/api/v1/scenarios/", json=NEW_SCENARIO, headers=admin)
    ).status_code == 409

    # Trainees see the brief without the hidden fields; editors see everything
    brief = (await client.get(url, headers=trainee)).json()
    assert brief["customer"]["name"] == "Chidi"
    assert brief["category"]["id"] == "problem_resolution"
    assert "success_criteria" not in brief and "escalation_behavior" not in brief
    assert (await client.get(f"{url}/manage", headers=trainee)).status_code == 403
    managed = (await client.get(f"{url}/manage", headers=admin)).json()
    assert managed["escalation_behavior"].startswith("Threatens")

    # The AI customer is built from the new scenario's brief
    session = await client.post(
        "/api/v1/simulations/start",
        json={"scenario_id": scenario["id"]},
        headers=trainee,
    )
    session_id = session.json()["id"]
    await client.post(
        f"/api/v1/simulations/{session_id}/message",
        json={"content": "Hello"},
        headers=trainee,
    )
    assert "customer named Chidi" in llm.customer_prompts[-1]

    edited = await client.patch(
        url, json={"difficulty": "advanced", "customer_goal": None}, headers=admin
    )
    assert edited.json()["difficulty"] == "advanced"
    assert edited.json()["name"] == NEW_SCENARIO["name"]  # untouched fields stay

    # Archive: hidden from trainees, no new sessions, history kept
    assert (await client.delete(url, headers=admin)).status_code == 204
    names = [
        s["name"]
        for s in (await client.get("/api/v1/scenarios/", headers=trainee)).json()
    ]
    assert NEW_SCENARIO["name"] not in names and len(names) == 5
    assert (await client.get(url, headers=trainee)).status_code == 404
    refused = await client.post(
        "/api/v1/simulations/start",
        json={"scenario_id": scenario["id"]},
        headers=trainee,
    )
    assert refused.status_code == 404
    history = (await client.get("/api/v1/simulations/", headers=trainee)).json()
    assert history["items"][0]["scenario"]["name"] == NEW_SCENARIO["name"]
    everything = (await client.get("/api/v1/scenarios/manage", headers=admin)).json()
    assert len(everything) == 6
    assert [s["name"] for s in everything if s["is_archived"]] == [NEW_SCENARIO["name"]]

    restored = await client.patch(url, json={"is_archived": False}, headers=admin)
    assert restored.json()["is_archived"] is False
    assert (await client.get(url, headers=trainee)).status_code == 200


async def test_scenarios_are_private_to_their_organization(client, outbox):
    _, admin = await _onboard(client, outbox)
    _, other_admin = await _onboard(client, outbox, "Other Co", "admin@other.com")
    created = await client.post("/api/v1/scenarios/", json=NEW_SCENARIO, headers=admin)
    url = f"/api/v1/scenarios/{created.json()['id']}"

    assert (await client.get(f"{url}/manage", headers=other_admin)).status_code == 404
    assert (
        await client.patch(url, json={"name": "Hijacked"}, headers=other_admin)
    ).status_code == 404
    assert (await client.delete(url, headers=other_admin)).status_code == 404
    # The same name is fine in a different organization
    assert (
        await client.post("/api/v1/scenarios/", json=NEW_SCENARIO, headers=other_admin)
    ).status_code == 201
