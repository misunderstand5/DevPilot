"""Small deterministic smoke evaluation for the Online Boutique binding."""
import asyncio
import json

from sqlalchemy import text

import _bootstrap  # noqa: F401
from app.db import engine, session_scope
from app.services.rag import get_rag_service


async def main() -> int:
    query = "Online Boutique order-service checkoutservice 依赖哪些下游"
    results = await get_rag_service().search(query)
    matching = [row for row in results if "online-boutique-v0.10.7" in row.get("title", "")]
    async with session_scope() as db:
        row = (await db.execute(text("""
            SELECT d.version,d.environment,d.commit_sha,d.notes
            FROM deployment d JOIN service s ON s.id=d.service_id
            WHERE s.name='order-service' AND d.version='v0.10.7' AND d.environment='reference'
            LIMIT 1
        """))).mappings().first()
    report = {
        "rag_query": query,
        "rag_reference_hit": bool(matching),
        "top_titles": [item.get("title") for item in results[:5]],
        "ops_reference_release": dict(row) if row else None,
        "passed": bool(matching and row and row["commit_sha"] == "5b608cb"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    await engine.dispose()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
