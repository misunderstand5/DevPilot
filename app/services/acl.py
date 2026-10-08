from sqlalchemy import text

from app.db import session_scope
from app.security import AuthUser


async def accessible_document_ids(user: AuthUser, *, write: bool = False) -> set[int]:
    permission = "WRITE" if write else "READ"
    async with session_scope() as db:
        if user.has_permission("kb.document.manage_all"):
            result = await db.execute(
                text("SELECT id FROM kb_document WHERE tenant_id=:tenant"), {"tenant": user.tenant_id}
            )
        else:
            result = await db.execute(text("""
                SELECT DISTINCT d.id FROM kb_document d
                LEFT JOIN kb_document_acl a ON a.document_id=d.id AND a.user_id=:user
                WHERE d.tenant_id=:tenant AND (
                  d.owner_user_id=:user
                  OR (:write=0 AND d.visibility='TENANT')
                  OR a.permission=:permission
                  OR (:write=0 AND a.permission='WRITE')
                )
            """), {"tenant": user.tenant_id, "user": user.id,
                    "write": int(write), "permission": permission})
        return {int(row[0]) for row in result}


async def can_access_document(user: AuthUser, document_id: int, *, write: bool = False) -> bool:
    return document_id in await accessible_document_ids(user, write=write)
