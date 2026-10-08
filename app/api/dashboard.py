from fastapi import APIRouter, Depends
from sqlalchemy import bindparam, text

from app.db import session_scope
from app.security import AuthUser, current_user
from app.services.acl import accessible_document_ids

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


async def _rows(db, sql: str):
    result = await db.execute(text(sql))
    return [dict(row._mapping) for row in result]


@router.get("")
async def dashboard(user: AuthUser = Depends(current_user)):
    """Return the compact read-only operations view used by the web console."""
    async with session_scope() as db:
        services = await _rows(db, """
            SELECT id,name,owner_team,environment,status,description,updated_at
            FROM service ORDER BY FIELD(status,'DOWN','DEGRADED','UNKNOWN','UP'),name
        """)
        deployments = await _rows(db, """
            SELECT d.id,s.name AS service_name,d.version,d.environment,d.status,
                   d.started_at,d.finished_at,d.operator_name,d.commit_sha,d.notes
            FROM deployment d JOIN service s ON s.id=d.service_id
            ORDER BY d.started_at DESC LIMIT 12
        """)
        incidents = await _rows(db, """
            SELECT i.id,s.name AS service_name,i.severity,i.title,i.status,
                   i.started_at,i.root_cause,i.resolution
            FROM incident i JOIN service s ON s.id=i.service_id
            ORDER BY FIELD(i.status,'OPEN','INVESTIGATING','MITIGATED','RESOLVED'),
                     FIELD(i.severity,'P1','P2','P3','P4'),i.started_at DESC LIMIT 12
        """)
        tickets = await _rows(db, """
            SELECT t.id,s.name AS service_name,t.title,t.status,t.priority,t.assignee,t.created_at
            FROM ticket t LEFT JOIN service s ON s.id=t.service_id
            ORDER BY FIELD(t.status,'OPEN','IN_PROGRESS','DONE','CLOSED'),
                     FIELD(t.priority,'P1','P2','P3','P4'),t.created_at DESC LIMIT 12
        """)
        allowed = await accessible_document_ids(user)
        documents = []
        if allowed:
            statement = text("""
                SELECT id,title,doc_type,source_uri,version,status,chunk_count,visibility,created_at,updated_at
                FROM kb_document WHERE id IN :ids ORDER BY updated_at DESC LIMIT 200
            """).bindparams(bindparam("ids", expanding=True))
            result = await db.execute(statement, {"ids": sorted(allowed)})
            documents = [dict(row._mapping) for row in result]

    return {
        "summary": {
            "services": len(services),
            "healthy_services": sum(x["status"] == "UP" for x in services),
            "open_incidents": sum(x["status"] != "RESOLVED" for x in incidents),
            "open_tickets": sum(x["status"] in {"OPEN", "IN_PROGRESS"} for x in tickets),
        },
        "services": services,
        "deployments": deployments,
        "incidents": incidents,
        "tickets": tickets,
        "documents": documents,
    }
