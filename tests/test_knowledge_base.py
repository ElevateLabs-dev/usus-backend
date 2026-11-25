# ruff: noqa: F811  (pytest fixtures shared with test_training_flow)
"""Knowledge base: upload PDF / Word, search, and use in evaluations."""

import io
import zipfile

import httpx
import openai
import pytest
from sqlalchemy import func, select

from src.core.security import hash_password
from src.domains.knowledge import router as knowledge_router
from src.domains.knowledge import service as knowledge_service
from src.domains.knowledge.extract import chunk_text
from src.domains.knowledge.models import DocumentChunk
from src.domains.users.models import User
from src.infrastructure.llm.embeddings import EMBEDDING_DIMENSIONS
from src.infrastructure.storage.r2 import StorageError
from tests.test_training_flow import (  # noqa: F401  (fixtures)
    PASSWORD,
    _auth,
    _make_org,
    _play,
    _scenario_id,
    client,
    llm,
    session_factory,
)


class FakeEmbedder:
    """Bag of words: texts sharing words are close."""

    async def embed(self, texts):
        vectors = []
        for text in texts:
            vector = [0.0] * EMBEDDING_DIMENSIONS
            for word in text.lower().split():
                vector[sum(map(ord, word.strip(".,"))) % EMBEDDING_DIMENSIONS] += 1
            vector[0] += 0.01
            vectors.append(vector)
        return vectors


@pytest.fixture(autouse=True)
def kb(monkeypatch, session_factory):
    monkeypatch.setattr(knowledge_service, "embedder", FakeEmbedder())
    monkeypatch.setattr(knowledge_router, "_session_factory", session_factory)


def make_pdf(text: str) -> bytes:
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % number + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(
        b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, xref)
    )
    return out.getvalue()


def make_docx(*paragraphs: str) -> bytes:
    ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    xml = f'<w:document xmlns:w="{ns}"><w:body>{body}</w:body></w:document>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


async def _admin(session_factory, tenant_id):
    async with session_factory() as db:
        db.add(
            User(
                email="admin@acme.com",
                hashed_password=hash_password(PASSWORD),
                role="company_admin",
                tenant_id=tenant_id,
            )
        )
        await db.commit()


async def _upload(client, headers, name, data):
    return await client.post(
        "/api/v1/knowledge-base/documents",
        files={"file": (name, data, "application/octet-stream")},
        headers=headers,
    )


async def test_upload_pdf_and_word(client, session_factory):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    trainee = await _auth(client, "trainee@acme.com")

    pdf = await _upload(
        client, manager, "refunds.pdf", make_pdf("Refunds are allowed within 30 days.")
    )
    assert pdf.status_code == 201, pdf.text
    assert pdf.json()["file_type"] == "pdf"
    docx = await _upload(
        client,
        manager,
        "greeting.docx",
        make_docx("Always greet the customer by name.", "Never share passwords."),
    )
    assert docx.json()["file_type"] == "docx"

    documents = (
        await client.get("/api/v1/knowledge-base/documents", headers=manager)
    ).json()
    assert {d["filename"]: d["status"] for d in documents} == {
        "refunds.pdf": "ready",
        "greeting.docx": "ready",
    }

    async with session_factory() as db:
        texts = (await db.execute(select(DocumentChunk.content))).scalars().all()
    assert any("within 30 days" in t for t in texts)
    assert any("Never share passwords." in t for t in texts)

    assert (await _upload(client, manager, "notes.txt", b"hello")).status_code == 400
    assert (await _upload(client, trainee, "x.pdf", make_pdf("hi"))).status_code == 403

    await client.delete(
        f"/api/v1/knowledge-base/documents/{pdf.json()['id']}", headers=manager
    )
    async with session_factory() as db:
        left = (await db.execute(select(func.count(DocumentChunk.id)))).scalar_one()
    assert left == 1


async def test_unreadable_pdf_fails_with_a_reason(client, session_factory):
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    response = await _upload(client, manager, "broken.pdf", b"%PDF-1.4 nonsense")
    document = (
        await client.get(
            f"/api/v1/knowledge-base/documents/{response.json()['id']}",
            headers=manager,
        )
    ).json()
    assert document["status"] == "failed"
    assert document["error"]


async def test_evaluator_uses_the_knowledge_base_when_turned_on(
    client, session_factory, llm, monkeypatch
):
    tenant_id = await _make_org(session_factory)
    await _admin(session_factory, tenant_id)
    admin = await _auth(client, "admin@acme.com")
    manager = await _auth(client, "manager@acme.com")
    trainee = await _auth(client, "trainee@acme.com")

    await _upload(
        client,
        manager,
        "policy.docx",
        make_docx(
            "Subscription cancellation: offer one free month before cancelling.",
            "Office plants are watered on Fridays.",
        ),
    )

    prompts = []
    original = llm.generate_response

    async def capture(system_prompt, messages, *args, **kwargs):
        if kwargs.get("json_mode"):
            prompts.append(messages[0]["content"])
        return await original(system_prompt, messages, *args, **kwargs)

    monkeypatch.setattr(llm, "generate_response", capture)
    scenario_id = await _scenario_id(client, trainee)

    # Off by default
    session_id = await _play(client, trainee, scenario_id)
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)
    assert "company's own documents" not in prompts[-1]

    assert (
        await client.patch(
            "/api/v1/knowledge-base/settings",
            json={"use_for_evaluation": True},
            headers=manager,
        )
    ).status_code == 403
    settings = await client.patch(
        "/api/v1/knowledge-base/settings",
        json={"use_for_evaluation": True},
        headers=admin,
    )
    assert settings.json() == {"use_for_evaluation": True, "documents_ready": 1}

    session_id = await _play(client, trainee, scenario_id)
    await client.post(f"/api/v1/simulations/{session_id}/end", headers=trainee)
    assert "company's own documents" in prompts[-1]
    assert "offer one free month" in prompts[-1]


def test_chunks_overlap_and_keep_paragraphs():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10))
    chunks = chunk_text(text, size=500, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 600 for c in chunks)
    assert chunks[0].startswith("Paragraph 0")


class FakeStorage:
    configured = True

    def __init__(self):
        self.files = {}

    async def put(self, key, body, content_type):
        self.files[key] = body

    async def get(self, key):
        if key not in self.files:
            raise StorageError("missing")
        return self.files[key]

    async def delete(self, key):
        self.files.pop(key, None)


class DownEmbedder:
    async def embed(self, texts):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://x"))


async def test_failed_document_can_be_retried(client, session_factory, monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(knowledge_router, "_storage", storage)
    working = knowledge_service.embedder
    monkeypatch.setattr(knowledge_service, "embedder", DownEmbedder())
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")

    uploaded = await _upload(
        client, manager, "p.docx", make_docx("Refunds in 30 days.")
    )
    url = f"/api/v1/knowledge-base/documents/{uploaded.json()['id']}"
    failed = (await client.get(url, headers=manager)).json()
    assert failed["status"] == "failed"
    assert "AI service" in failed["error"]
    assert len(storage.files) == 1

    monkeypatch.setattr(knowledge_service, "embedder", working)
    retried = await client.post(f"{url}/retry", headers=manager)
    assert retried.status_code == 200, retried.text
    assert (await client.get(url, headers=manager)).json()["status"] == "ready"

    # Only failed documents
    assert (await client.post(f"{url}/retry", headers=manager)).status_code == 409

    await client.delete(url, headers=manager)
    assert storage.files == {}


async def test_retry_needs_the_kept_file(client, session_factory, monkeypatch):
    monkeypatch.setattr(knowledge_service, "embedder", DownEmbedder())
    await _make_org(session_factory)
    manager = await _auth(client, "manager@acme.com")
    uploaded = await _upload(client, manager, "p.docx", make_docx("Hi."))
    url = f"/api/v1/knowledge-base/documents/{uploaded.json()['id']}/retry"
    response = await client.post(url, headers=manager)
    assert response.status_code == 409
    assert "upload it again" in response.json()["detail"]
