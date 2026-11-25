"""Company self-signup: details -> emailed code -> verified company admin."""

import re
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import src.domains.evaluations.models  # noqa: F401  (register all tables)
import src.domains.scenarios.models  # noqa: F401
import src.domains.simulations.models  # noqa: F401
from src.core.base_model import Base
from src.core.database import get_db
from src.domains.auth import signup
from src.domains.auth.models import PendingSignup
from src.domains.scenarios.models import Scenario
from src.domains.tenants.models import Tenant
from src.domains.users.models import User
from src.main import app

DETAILS = {
    "company_name": "Acme Retail",
    "email": "Ada@Acme.com",
    "full_name": "Ada Obi",
    "password": "a-strong-password",
    "company_type": "Retail",
    "referral_source": "LinkedIn",
}


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def outbox(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(
        signup,
        "send_email",
        lambda to, subject, body: sent.append({"to": to, "body": body}),
    )
    return sent


@pytest_asyncio.fixture
async def client(session_factory, outbox):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)


def _code(outbox) -> str:
    return re.search(r"code is (\d{6})", outbox[-1]["body"]).group(1)


async def _allow_resend(session_factory):
    async with session_factory() as db:
        pending = (await db.execute(select(PendingSignup))).scalar_one()
        pending.last_sent_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        await db.commit()


async def test_signup_then_verify_creates_company_admin(
    client, outbox, session_factory
):
    response = await client.post("/api/v1/auth/signup", json=DETAILS)
    assert response.status_code == 201, response.text
    assert response.json()["email"] == "ada@acme.com"
    assert outbox[-1]["to"] == "ada@acme.com"

    # Nothing exists until the code is confirmed, so sign-in fails
    signin = await client.post(
        "/api/v1/auth/token",
        data={"username": "ada@acme.com", "password": DETAILS["password"]},
    )
    assert signin.status_code == 401

    response = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": "ada@acme.com", "code": _code(outbox)},
    )
    assert response.status_code == 200, response.text
    assert response.json()["must_change_password"] is False

    async with session_factory() as db:
        tenant = (await db.execute(select(Tenant))).scalar_one()
        assert (tenant.name, tenant.company_type, tenant.referral_source) == (
            "Acme Retail",
            "Retail",
            "LinkedIn",
        )
        user = (await db.execute(select(User))).scalar_one()
        assert (user.role, user.tenant_id, user.full_name) == (
            "company_admin",
            tenant.id,
            "Ada Obi",
        )
        assert (await db.execute(select(Scenario))).scalars().first() is not None
        assert (await db.execute(select(PendingSignup))).first() is None

    signin = await client.post(
        "/api/v1/auth/token",
        data={"username": "ada@acme.com", "password": DETAILS["password"]},
    )
    assert signin.status_code == 200


@pytest.mark.skip(reason="Company-email check is off for now")
@pytest.mark.parametrize(
    "email", ["ada@gmail.com", "ada@yahoo.co.uk", "ada@Outlook.com", "ada@icloud.com"]
)
async def test_personal_emails_are_refused(client, email):
    response = await client.post(
        "/api/v1/auth/signup", json={**DETAILS, "email": email}
    )
    assert response.status_code == 400
    assert "company email" in response.json()["detail"]


async def test_wrong_codes_are_limited(client, outbox):
    await client.post("/api/v1/auth/signup", json=DETAILS)
    right = _code(outbox)
    wrong = "000000" if right != "000000" else "111111"
    for _ in range(signup.MAX_ATTEMPTS):
        response = await client.post(
            "/api/v1/auth/verify-email", json={"email": DETAILS["email"], "code": wrong}
        )
        assert response.json()["detail"] == "Incorrect code"
    response = await client.post(
        "/api/v1/auth/verify-email", json={"email": DETAILS["email"], "code": right}
    )
    assert response.status_code == 400
    assert "Request a new code" in response.json()["detail"]


async def test_resend_waits_a_minute_and_replaces_the_code(
    client, outbox, session_factory
):
    await client.post("/api/v1/auth/signup", json=DETAILS)
    first = _code(outbox)

    response = await client.post(
        "/api/v1/auth/resend-code", json={"email": DETAILS["email"]}
    )
    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0

    await _allow_resend(session_factory)
    response = await client.post(
        "/api/v1/auth/resend-code", json={"email": DETAILS["email"]}
    )
    assert response.status_code == 200
    second = _code(outbox)
    assert len(outbox) == 2

    if first != second:
        old = await client.post(
            "/api/v1/auth/verify-email", json={"email": DETAILS["email"], "code": first}
        )
        assert old.status_code == 400
    new = await client.post(
        "/api/v1/auth/verify-email", json={"email": DETAILS["email"], "code": second}
    )
    assert new.status_code == 200


async def test_expired_code(client, outbox, session_factory):
    await client.post("/api/v1/auth/signup", json=DETAILS)
    async with session_factory() as db:
        pending = (await db.execute(select(PendingSignup))).scalar_one()
        pending.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()
    response = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": DETAILS["email"], "code": _code(outbox)},
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


async def test_taken_email_is_refused_but_names_can_repeat(
    client, outbox, session_factory
):
    async with session_factory() as db:
        tenant = Tenant(name="Acme Retail")
        db.add(tenant)
        await db.flush()
        db.add(
            User(
                email="boss@other.com",
                hashed_password="!",
                role="company_admin",
                tenant_id=tenant.id,
            )
        )
        await db.commit()

    taken_email = await client.post(
        "/api/v1/auth/signup",
        json={**DETAILS, "company_name": "Other Co", "email": "boss@other.com"},
    )
    assert taken_email.status_code == 409
    assert outbox == []

    # Another company with the same name is fine
    same_name = await client.post("/api/v1/auth/signup", json=DETAILS)
    assert same_name.status_code == 201
    verified = await client.post(
        "/api/v1/auth/verify-email",
        json={"email": DETAILS["email"], "code": _code(outbox)},
    )
    assert verified.status_code == 200, verified.text
    async with session_factory() as db:
        names = (await db.execute(select(Tenant.name))).scalars().all()
    assert names == ["Acme Retail", "Acme Retail"]


async def test_signing_up_again_updates_the_details(client, outbox, session_factory):
    await client.post("/api/v1/auth/signup", json=DETAILS)
    await _allow_resend(session_factory)
    response = await client.post(
        "/api/v1/auth/signup", json={**DETAILS, "company_name": "Acme Stores"}
    )
    assert response.status_code == 201
    await client.post(
        "/api/v1/auth/verify-email",
        json={"email": DETAILS["email"], "code": _code(outbox)},
    )
    async with session_factory() as db:
        tenant = (await db.execute(select(Tenant))).scalar_one()
        assert tenant.name == "Acme Stores"
