"""
Tests for POST /api/v1/evaluations/{simulation_id}/generate

Strategy:
- Authentication checks only; no database needed.
- We mint JWTs using the same SECRET_KEY as the app.
- The full re-run flow is covered in test_training_flow.py.
"""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt

from src.core.config import settings
from src.main import app

ALGORITHM = "HS256"
SIMULATION_ID = str(uuid.uuid4())
TENANT_ID = str(uuid.uuid4())


def make_token(payload: dict) -> str:
    """Mint a signed JWT with the app's SECRET_KEY."""
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


@pytest.mark.asyncio
async def test_trigger_evaluation_unauthorized():
    """Calling the endpoint with no token must return 401."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(f"/api/v1/evaluations/{SIMULATION_ID}/generate")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trigger_evaluation_invalid_token():
    """A tampered / wrongly-signed token must return 401."""
    bad_token = make_token({"tenant_id": TENANT_ID}) + "tampered"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/evaluations/{SIMULATION_ID}/generate",
            headers={"Authorization": f"Bearer {bad_token}"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_trigger_evaluation_missing_tenant_id_claim():
    """A valid JWT that has no tenant_id claim must return 401."""
    token = make_token({"sub": "some-user"})  # no tenant_id

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/v1/evaluations/{SIMULATION_ID}/generate",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
