from pathlib import Path
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text

from app.db import session_scope
from app.services.rag import get_rag_service
from app.security import AuthUser, current_user
from app.services.acl import accessible_document_ids, can_access_document

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])

ALLOWED_SUFFIXES = {".md", ".txt", ".pdf", ".docx"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


async def _temporary_upload(file: UploadFile) -> tuple[Path, str]:
    filename = Path(file.filename or "upload.txt").name
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, "supported: md/txt/pdf/docx")
    size = 0
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(413, "document exceeds 20 MB")
            tmp.write(chunk)
        return Path(tmp.name), filename


@router.get("")
async def list_documents(limit: int = Query(50, ge=1, le=200), user: AuthUser = Depends(current_user)):
    allowed = await accessible_document_ids(user)
    if not allowed:
        return {"documents": [], "summary": {"total": 0, "indexed": 0, "chunks": 0}}
    async with session_scope() as db:
        statement = text("""
            SELECT id,title,doc_type,source_uri,version,status,chunk_count,visibility,owner_user_id,created_at,updated_at
            FROM kb_document WHERE id IN :ids ORDER BY updated_at DESC LIMIT :n
        """).bindparams(bindparam("ids", expanding=True))
        result = await db.execute(statement, {"ids": sorted(allowed), "n": limit})
        rows = [dict(row._mapping) for row in result]
        aggregate = text("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(status='INDEXED'),0) AS indexed,
                   COALESCE(SUM(chunk_count),0) AS chunks
            FROM kb_document WHERE id IN :ids
        """).bindparams(bindparam("ids", expanding=True))
        totals = (await db.execute(aggregate, {"ids": sorted(allowed)})).first()
    return {
        "documents": rows,
        "summary": {
            "total": int(totals.total),
            "indexed": int(totals.indexed),
            "chunks": int(totals.chunks),
        },
    }


@router.get("/{document_id}")
async def document_detail(document_id: int, preview_chunks: int = Query(5, ge=0, le=20),
                          user: AuthUser = Depends(current_user)):
    if not await can_access_document(user, document_id):
        raise HTTPException(404, "document not found")
    async with session_scope() as db:
        result = await db.execute(text("""
            SELECT id,title,doc_type,source_uri,version,status,chunk_count,visibility,owner_user_id,created_at,updated_at
            FROM kb_document WHERE id=:id
        """), {"id": document_id})
        document = result.first()
        if not document:
            raise HTTPException(404, "document not found")
        chunks = await db.execute(text("""
            SELECT id,chunk_index,heading,LEFT(content,500) AS preview,char_count
            FROM kb_chunk WHERE document_id=:id ORDER BY chunk_index LIMIT :n
        """), {"id": document_id, "n": preview_chunks})
        return {"document": dict(document._mapping), "chunks": [dict(row._mapping) for row in chunks]}


@router.post("/ingest")
async def ingest(
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    source_uri: str | None = Form(default=None, max_length=1000),
    visibility: str = Form(default="TENANT", pattern="^(TENANT|PRIVATE)$"),
    user: AuthUser = Depends(current_user),
):
    path, filename = await _temporary_upload(file)
    try:
        return await get_rag_service().ingest_file(
            path, title=(title or Path(filename).stem).strip(), source_uri=(source_uri or filename).strip(),
            tenant_id=user.tenant_id, owner_user_id=user.id, visibility=visibility,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@router.put("/{document_id}")
async def update_document(
    document_id: int,
    file: UploadFile = File(...),
    title: str | None = Form(default=None, max_length=255),
    source_uri: str | None = Form(default=None, max_length=1000),
    visibility: str = Form(default="TENANT", pattern="^(TENANT|PRIVATE)$"),
    user: AuthUser = Depends(current_user),
):
    if not await can_access_document(user, document_id, write=True):
        raise HTTPException(404, "document not found or not writable")
    path, filename = await _temporary_upload(file)
    try:
        result = await get_rag_service().ingest_file(
            path,
            title=(title or Path(filename).stem).strip(),
            source_uri=(source_uri or filename).strip(),
            document_id=document_id,
            tenant_id=user.tenant_id,
            owner_user_id=user.id,
            visibility=visibility,
        )
        return result
    except LookupError as exc:
        raise HTTPException(404, "document not found") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@router.delete("/{document_id}")
async def delete_document(document_id: int, user: AuthUser = Depends(current_user)):
    if not await can_access_document(user, document_id, write=True):
        raise HTTPException(404, "document not found or not writable")
    deleted = await get_rag_service().delete_document(document_id, user.tenant_id)
    if not deleted:
        raise HTTPException(404, "document not found")
    return {"document_id": document_id, "deleted": True}


class AclGrantRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    permission: str = Field(default="READ", pattern="^(READ|WRITE)$")


@router.put("/{document_id}/acl")
async def grant_document_access(document_id: int, req: AclGrantRequest,
                                user: AuthUser = Depends(current_user)):
    if not await can_access_document(user, document_id, write=True):
        raise HTTPException(404, "document not found or not writable")
    async with session_scope() as db:
        target = await db.execute(text("""
            SELECT id FROM app_user WHERE tenant_id=:tenant AND username=:username AND status='ACTIVE'
        """), {"tenant": user.tenant_id, "username": req.username})
        row = target.first()
        if not row:
            raise HTTPException(404, "target user not found")
        await db.execute(text("""
            INSERT INTO kb_document_acl(document_id,user_id,permission)
            VALUES(:document,:user,:permission)
            ON DUPLICATE KEY UPDATE permission=VALUES(permission)
        """), {"document": document_id, "user": row.id, "permission": req.permission})
    return {"document_id": document_id, "username": req.username, "permission": req.permission}
