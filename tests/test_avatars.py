# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Profile pictures stored in Cloudflare R2."""

import pytest

from src.core.config import settings
from src.domains.users import router as users_router
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    _auth,
    _make_org,
    client,
    llm,
    session_factory,
)

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"0" * 100


class FakeStorage:
    configured = True

    def __init__(self):
        self.files: dict[str, tuple[bytes, str]] = {}

    async def put(self, key, body, content_type):
        self.files[key] = (body, content_type)

    async def delete(self, key):
        self.files.pop(key, None)


@pytest.fixture
def storage(monkeypatch):
    fake = FakeStorage()
    monkeypatch.setattr(users_router, "_storage", fake)
    monkeypatch.setattr(settings, "R2_PUBLIC_URL", "https://files.example.com")
    return fake


async def _upload(client, headers, data, name="me.jpg"):
    return await client.put(
        "/api/v1/users/me/avatar",
        files={"file": (name, data, "image/jpeg")},
        headers=headers,
    )


async def test_upload_replace_and_remove(client, session_factory, storage):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")

    me = (await client.get("/api/v1/users/me", headers=trainee)).json()
    assert me["avatar_url"] is None
    assert "avatar_key" not in me

    first = await _upload(client, trainee, JPEG)
    assert first.status_code == 200, first.text
    url = first.json()["avatar_url"]
    assert url.startswith(f"https://files.example.com/avatars/{me['id']}/")
    assert url.endswith(".jpg")
    assert list(storage.files.values()) == [(JPEG, "image/jpeg")]

    # Replacing deletes the old file; the type comes from the bytes
    second = await _upload(client, trainee, WEBP, name="me.jpg")
    assert second.json()["avatar_url"].endswith(".webp")
    assert list(storage.files.values()) == [(WEBP, "image/webp")]

    removed = await client.delete("/api/v1/users/me/avatar", headers=trainee)
    assert removed.json()["avatar_url"] is None
    assert storage.files == {}


async def test_only_small_images_are_accepted(client, session_factory, storage):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")

    not_image = await _upload(client, trainee, b"<svg onload=alert(1)>")
    assert not_image.status_code == 400
    too_big = await _upload(client, trainee, JPEG + b"0" * (2 * 1024 * 1024))
    assert too_big.status_code == 400
    assert storage.files == {}


async def test_upload_needs_storage(client, session_factory, storage):
    await _make_org(session_factory)
    trainee = await _auth(client, "trainee@acme.com")
    storage.configured = False
    assert (await _upload(client, trainee, JPEG)).status_code == 503
