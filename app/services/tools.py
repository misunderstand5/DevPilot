from sqlalchemy import text
from app.db import session_scope


async def get_service_status(service_name: str):
    async with session_scope() as db:
        r = await db.execute(
            text("SELECT id,name,owner_team,environment,status,description,updated_at FROM service WHERE name=:name LIMIT 1"),
            {"name": service_name},
        )
        row = r.first()
        return dict(row._mapping) if row else {"error": "service_not_found", "service_name": service_name}


async def recent_deployments(service_name: str, days: int = 7):
    days = max(1, min(int(days), 90))
    # days 已被转为受限整数，因此这里只插值 SQL 关键字要求的 INTERVAL 数字。
    sql = text(f"""
        SELECT d.id,s.name AS service_name,d.version,d.environment,d.status,
               d.started_at,d.finished_at,d.operator_name,d.commit_sha,d.notes
        FROM deployment d JOIN service s ON s.id=d.service_id
        WHERE s.name=:name AND d.started_at >= DATE_SUB(NOW(), INTERVAL {days} DAY)
        ORDER BY d.started_at DESC LIMIT 50
    """)
    async with session_scope() as db:
        r = await db.execute(sql, {"name": service_name})
        return [dict(x._mapping) for x in r]


async def open_incidents(service_name: str | None = None):
    async with session_scope() as db:
        sql = """
            SELECT i.id,s.name AS service_name,i.severity,i.title,i.status,
                   i.started_at,i.root_cause,i.resolution
            FROM incident i JOIN service s ON s.id=i.service_id
            WHERE i.status <> 'RESOLVED'
        """
        params = {}
        if service_name:
            sql += " AND s.name=:name"
            params["name"] = service_name
        sql += " ORDER BY i.started_at DESC LIMIT 50"
        r = await db.execute(text(sql), params)
        return [dict(x._mapping) for x in r]


async def open_tickets(service_name: str | None = None):
    async with session_scope() as db:
        sql = """
            SELECT t.id,s.name AS service_name,t.title,t.status,t.priority,t.assignee,t.created_at
            FROM ticket t LEFT JOIN service s ON s.id=t.service_id
            WHERE t.status IN ('OPEN','IN_PROGRESS')
        """
        params = {}
        if service_name:
            sql += " AND s.name=:name"
            params["name"] = service_name
        sql += " ORDER BY t.created_at DESC LIMIT 50"
        r = await db.execute(text(sql), params)
        return [dict(x._mapping) for x in r]
