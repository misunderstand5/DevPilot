import asyncio
from pathlib import Path

from sqlalchemy import text

import _bootstrap  # noqa: F401
from app.db import engine, session_scope


async def main():
    sql_path = Path(__file__).resolve().parents[1] / "sql" / "005_memory_v2.sql"
    statements = [part.strip() for part in sql_path.read_text(encoding="utf-8").split(";") if part.strip()]
    try:
        async with session_scope() as db:
            for statement in statements:
                if statement.upper().startswith("USE "):
                    continue
                marker = "ALTER TABLE user_memory ADD COLUMN IF NOT EXISTS "
                if statement.startswith(marker):
                    column = statement[len(marker):].split(None, 1)[0]
                    exists = await db.execute(text("""
                        SELECT 1 FROM information_schema.columns
                        WHERE table_schema=DATABASE() AND table_name='user_memory' AND column_name=:column
                    """), {"column": column})
                    if exists.first():
                        continue
                    statement = statement.replace(" ADD COLUMN IF NOT EXISTS ", " ADD COLUMN ", 1)
                await db.execute(text(statement))
    finally:
        await engine.dispose()
    print("memory v2 migration complete")


if __name__ == "__main__":
    asyncio.run(main())
