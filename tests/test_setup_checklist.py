# ruff: noqa: F811  (pytest fixtures shared with other tests)
"""Company setup checklist, company profile/logo and the walkthrough."""

from src.domains.tenants import router as tenants_router
from tests.test_knowledge_base import _admin, _upload, kb, make_docx  # noqa: F401
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    client,
    llm,
    session_factory,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


class FakeStorage:
    configured = True

    def __init__(self):
        self.files = {}

    async def put(self, key, body, content_type):
        self.files[key] = body

    async def delete(self, key):
        self.files.pop(key, None)


def _done(checklist):
    return {step["key"]: step["done"] for step in checklist["steps"]}


async def test_checklist_follows_the_organizations_data(
    client, session_factory, monkeypatch
):
    storage = FakeStorage()
    monkeypatch.setattr(tenants_router, "_storage", storage)
    tenant_id = await _make_org(session_factory)
    await _admin(session_factory, tenant_id)
    admin = await _auth(client, "admin@acme.com")
    manager = await _auth(client, "manager@acme.com")
    trainee = await _auth(client, "trainee@acme.com")

    checklist = (await client.get("/api/v1/onboarding/checklist", headers=admin)).json()
    # The org from the fixture already has a trainee; starter scenarios don't count
    assert _done(checklist) == {
        "knowledge_base": False,
        "scenarios": False,
        "company_profile": False,
        "team": True,
        "launch": False,
    }
    assert (checklist["completed"], checklist["total"]) == (1, 5)
    assert (
        await client.get("/api/v1/onboarding/checklist", headers=trainee)
    ).status_code == 403

    await _upload(client, manager, "p.docx", make_docx("Refunds within 30 days."))
    await client.post(
        "/api/v1/scenarios/",
        json={
            "name": "Our own scenario",
            "description": "A customer wants a refund.",
            "category": "empathy",
            "difficulty": "beginner",
            "persona": "angry",
            "situation": "The order arrived broken.",
            "trainee_objective": "Calm them down and refund.",
        },
        headers=manager,
    )

    profile = await client.patch(
        "/api/v1/organizations/me", json={"company_type": "Retail"}, headers=admin
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["name"] == "Acme"
    logo = await client.put(
        "/api/v1/organizations/me/logo",
        files={"file": ("logo.png", PNG, "image/png")},
        headers=admin,
    )
    assert logo.status_code == 200, logo.text
    assert logo.json()["company_type"] == "Retail"
    [key] = storage.files
    assert key.startswith(f"logos/{tenant_id}/")

    launched = await client.post("/api/v1/onboarding/launch", headers=admin)
    assert all(_done(launched.json()).values())
    assert launched.json()["completed"] == 5

    hidden = await client.patch(
        "/api/v1/onboarding/checklist", json={"dismissed": True}, headers=admin
    )
    assert hidden.json()["dismissed"] is True
    assert (
        await client.patch(
            "/api/v1/onboarding/checklist", json={"dismissed": False}, headers=manager
        )
    ).status_code == 403

    removed = await client.delete("/api/v1/organizations/me/logo", headers=admin)
    assert removed.json()["logo_url"] is None
    assert storage.files == {}


async def test_walkthrough_is_remembered(client, session_factory):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    me = (await client.get("/api/v1/users/me", headers=trainee)).json()
    assert me["walkthrough_done_at"] is None

    done = await client.post("/api/v1/onboarding/walkthrough", headers=trainee)
    assert done.status_code == 200
    me = (await client.get("/api/v1/users/me", headers=trainee)).json()
    assert me["walkthrough_done_at"] is not None
