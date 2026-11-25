"""
Knowledge base API: upload PDF / Word documents and choose whether the
evaluator uses them.

The original file is kept in R2 (when it is set up) so a failed document can
be retried without uploading it again.
"""

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import AsyncSessionLocal, get_db
from src.core.dependencies import AuthContext, UserRole, require_roles
from src.domains.knowledge import service
from src.domains.knowledge.extract import file_type
from src.domains.knowledge.models import Document, DocumentChunk, DocumentStatus
from src.domains.tenants.models import Tenant
from src.infrastructure.storage.r2 import R2Storage, StorageError

logger = logging.getLogger("usus.knowledge")

router = APIRouter(prefix="/api/v1/knowledge-base", tags=["Knowledge base"])

# Session factory for the background processing (swapped out in tests)
_session_factory = AsyncSessionLocal
_storage = R2Storage()

MAX_FILE_BYTES = 20_000_000
MAX_DOCUMENTS = 100

_Staff = Annotated[
    AuthContext,
    Depends(
        require_roles(UserRole.COMPANY_ADMIN, UserRole.MANAGER, UserRole.PLATFORM_ADMIN)
    ),
]
_Admin = Annotated[
    AuthContext,
    Depends(require_roles(UserRole.COMPANY_ADMIN, UserRole.PLATFORM_ADMIN)),
]
_ERRORS: dict[int | str, dict] = {
    401: {"description": "Missing/invalid token, or no organization in the token"},
    403: {"description": "Not allowed for your role"},
}


class DocumentRead(BaseModel):
    id: UUID
    filename: str
    file_type: str = Field(description="pdf or docx")
    size_bytes: int
    status: str = Field(description="processing, ready or failed")
    error: str | None = Field(description="Why it failed")
    char_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeSettings(BaseModel):
    use_for_evaluation: bool = Field(
        description="The evaluator checks trainees against your documents"
    )
    documents_ready: int


class KnowledgeSettingsUpdate(BaseModel):
    use_for_evaluation: bool


def _tenant_of(ctx: AuthContext) -> UUID:
    if ctx.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required",
        )
    return ctx.tenant_id


def _file_key(document: Document) -> str:
    return f"knowledge/{document.tenant_id}/{document.id}.{document.file_type}"


async def _document(db: AsyncSession, ctx: AuthContext, document_id: UUID) -> Document:
    document = await db.get(Document, document_id)
    if document is None or document.tenant_id != _tenant_of(ctx):
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get(
    "/documents",
    response_model=list[DocumentRead],
    summary="List documents",
    responses=_ERRORS,
)
async def list_documents(ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]):
    result = await db.execute(
        select(Document)
        .where(Document.tenant_id == _tenant_of(ctx))
        .order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.post(
    "/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
    description=(
        "**Company admin / manager only.** A PDF or Word (.docx) file up to "
        f"{MAX_FILE_BYTES // 1_000_000} MB, sent as multipart field `file`. It is "
        "read in the background: `status` is `processing`, then `ready` or "
        "`failed` (with `error`). Poll `GET /knowledge-base/documents/{id}`.\n\n"
        "Scanned PDFs (images only) are not supported yet."
    ),
    responses={
        **_ERRORS,
        400: {"description": "Not a PDF or .docx, or too many documents"},
        413: {"description": "File too large"},
    },
)
async def upload_document(
    ctx: _Staff,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File(description="A .pdf or .docx file")],
):
    tenant_id = _tenant_of(ctx)
    data = await file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The file must be {MAX_FILE_BYTES // 1_000_000} MB or smaller",
        )
    kind = file_type(data)
    if kind is None:
        raise HTTPException(status_code=400, detail="Upload a PDF or Word (.docx) file")
    count = await db.execute(
        select(func.count(Document.id)).where(Document.tenant_id == tenant_id)
    )
    if count.scalar_one() >= MAX_DOCUMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"You can have up to {MAX_DOCUMENTS} documents. Delete one first.",
        )

    document = Document(
        tenant_id=tenant_id,
        filename=(file.filename or f"document.{kind}")[-255:],
        file_type=kind,
        size_bytes=len(data),
        uploaded_by=ctx.user_id,
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)
    if _storage.configured:
        try:
            await _storage.put(_file_key(document), data, "application/octet-stream")
        except StorageError:
            # Still processed; only retrying will need a new upload
            logger.exception("Keeping the original of document %s failed", document.id)
    background_tasks.add_task(
        service.process_document, document.id, data, _session_factory
    )
    return document


@router.get(
    "/documents/{document_id}",
    response_model=DocumentRead,
    summary="Get a document",
    responses={**_ERRORS, 404: {"description": "Document not found"}},
)
async def get_document(
    document_id: UUID, ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]
):
    return await _document(db, ctx, document_id)


@router.delete(
    "/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a document",
    description="**Company admin / manager only.** It is no longer used anywhere.",
    responses={**_ERRORS, 404: {"description": "Document not found"}},
)
async def delete_document(
    document_id: UUID, ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]
):
    document = await _document(db, ctx, document_id)
    await db.execute(
        delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )
    await db.delete(document)
    await db.commit()
    if _storage.configured:
        try:
            await _storage.delete(_file_key(document))
        except StorageError:
            logger.exception("Deleting the original of document %s failed", document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/documents/{document_id}/retry",
    response_model=DocumentRead,
    summary="Retry a failed document",
    description=(
        "**Company admin / manager only.** Processes a `failed` document again "
        "from the file uploaded earlier. `status` goes back to `processing`; "
        "poll `GET /knowledge-base/documents/{id}` as after an upload."
    ),
    responses={
        **_ERRORS,
        404: {"description": "Document not found"},
        409: {
            "description": "The document has not failed, or its file is no "
            "longer available (delete it and upload it again)"
        },
    },
)
async def retry_document(
    document_id: UUID,
    ctx: _Staff,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
):
    document = await _document(db, ctx, document_id)
    if document.status != DocumentStatus.FAILED.value:
        raise HTTPException(
            status_code=409, detail="Only failed documents can be retried"
        )
    try:
        data = await _storage.get(_file_key(document))
    except StorageError:
        raise HTTPException(
            status_code=409,
            detail="The file is no longer available. Delete it and upload it again.",
        )
    document.status = DocumentStatus.PROCESSING.value
    document.error = None
    await db.commit()
    await db.refresh(document)
    background_tasks.add_task(
        service.process_document, document.id, data, _session_factory
    )
    return document


async def _settings(db: AsyncSession, tenant_id: UUID) -> KnowledgeSettings:
    tenant = await db.get(Tenant, tenant_id)
    return KnowledgeSettings(
        use_for_evaluation=bool(tenant and tenant.use_kb_for_evaluation),
        documents_ready=await service.ready_count(db, tenant_id),
    )


@router.get(
    "/settings",
    response_model=KnowledgeSettings,
    summary="Knowledge base settings",
    responses=_ERRORS,
)
async def get_settings(ctx: _Staff, db: Annotated[AsyncSession, Depends(get_db)]):
    return await _settings(db, _tenant_of(ctx))


@router.patch(
    "/settings",
    response_model=KnowledgeSettings,
    summary="Change knowledge base settings",
    description=(
        "**Company admin only.** With `use_for_evaluation` on, the evaluator "
        "also checks what trainees say against the most relevant parts of your "
        "documents (e.g. policies). Applies to sessions evaluated from now on."
    ),
    responses=_ERRORS,
)
async def update_settings(
    body: KnowledgeSettingsUpdate,
    ctx: _Admin,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    tenant_id = _tenant_of(ctx)
    tenant = await db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Organization not found")
    tenant.use_kb_for_evaluation = body.use_for_evaluation
    await db.commit()
    return await _settings(db, tenant_id)
