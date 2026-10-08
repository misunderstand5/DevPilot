import asyncio

from sqlalchemy import text

import _bootstrap  # noqa: F401
from app.config import get_settings
from app.db import engine, session_scope
from app.security import hash_password


TENANT_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_ID = "00000000-0000-0000-0000-000000000011"
ENGINEER_ID = "00000000-0000-0000-0000-000000000012"


async def has_column(db, table_name: str, column_name: str) -> bool:
    result = await db.execute(text("""
        SELECT COUNT(*) FROM information_schema.columns
        WHERE table_schema=DATABASE() AND table_name=:table AND column_name=:column
    """), {"table": table_name, "column": column_name})
    return bool(result.scalar())


async def main():
    settings = get_settings()
    if not settings.auth_admin_password or not settings.auth_engineer_password:
        raise RuntimeError("AUTH_ADMIN_PASSWORD and AUTH_ENGINEER_PASSWORD must be set")
    async with session_scope() as db:
        await db.execute(text("""CREATE TABLE IF NOT EXISTS tenant (
          id CHAR(36) PRIMARY KEY,slug VARCHAR(64) NOT NULL UNIQUE,name VARCHAR(255) NOT NULL,
          status ENUM('ACTIVE','DISABLED') NOT NULL DEFAULT 'ACTIVE',created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB"""))
        await db.execute(text("""CREATE TABLE IF NOT EXISTS app_user (
          id CHAR(36) PRIMARY KEY,tenant_id CHAR(36) NOT NULL,username VARCHAR(100) NOT NULL,
          password_hash VARCHAR(255) NOT NULL,role ENUM('ADMIN','MEMBER') NOT NULL DEFAULT 'MEMBER',
          status ENUM('ACTIVE','DISABLED') NOT NULL DEFAULT 'ACTIVE',created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          CONSTRAINT fk_user_tenant FOREIGN KEY(tenant_id) REFERENCES tenant(id),
          UNIQUE KEY uk_tenant_username(tenant_id,username)
        ) ENGINE=InnoDB"""))
        await db.execute(text("""
          INSERT INTO tenant(id,slug,name,status) VALUES(:id,:slug,'DevPilot Demo Enterprise','ACTIVE')
          ON DUPLICATE KEY UPDATE name=VALUES(name),status='ACTIVE'
        """), {"id": TENANT_ID, "slug": settings.auth_default_tenant})
        for user_id, username, password, role in (
            (ADMIN_ID, "admin", settings.auth_admin_password, "ADMIN"),
            (ENGINEER_ID, "engineer", settings.auth_engineer_password, "MEMBER"),
        ):
            existing = await db.execute(text(
                "SELECT id FROM app_user WHERE tenant_id=:tenant AND username=:username"
            ), {"tenant": TENANT_ID, "username": username})
            if not existing.first():
                await db.execute(text("""
                    INSERT INTO app_user(id,tenant_id,username,password_hash,role,status)
                    VALUES(:id,:tenant,:username,:password,:role,'ACTIVE')
                """), {"id": user_id, "tenant": TENANT_ID, "username": username,
                        "password": hash_password(password), "role": role})

        if not await has_column(db, "kb_document", "tenant_id"):
            await db.execute(text("ALTER TABLE kb_document ADD COLUMN tenant_id CHAR(36) NULL AFTER id"))
        if not await has_column(db, "kb_document", "owner_user_id"):
            await db.execute(text("ALTER TABLE kb_document ADD COLUMN owner_user_id CHAR(36) NULL AFTER tenant_id"))
        if not await has_column(db, "kb_document", "visibility"):
            await db.execute(text("ALTER TABLE kb_document ADD COLUMN visibility ENUM('TENANT','PRIVATE') NOT NULL DEFAULT 'TENANT' AFTER owner_user_id"))
        await db.execute(text("UPDATE kb_document SET tenant_id=:tenant WHERE tenant_id IS NULL"), {"tenant": TENANT_ID})
        await db.execute(text("UPDATE kb_document SET owner_user_id=:admin WHERE owner_user_id IS NULL"), {"admin": ADMIN_ID})
        if await has_index(db, "kb_document", "checksum"):
            await db.execute(text("ALTER TABLE kb_document DROP INDEX checksum"))
        if not await has_index(db, "kb_document", "uk_doc_tenant_checksum"):
            await db.execute(text("ALTER TABLE kb_document ADD UNIQUE KEY uk_doc_tenant_checksum(tenant_id,checksum)"))
        await db.execute(text("""CREATE TABLE IF NOT EXISTS kb_document_acl (
          document_id BIGINT NOT NULL,user_id CHAR(36) NOT NULL,
          permission ENUM('READ','WRITE') NOT NULL DEFAULT 'READ',created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(document_id,user_id),
          CONSTRAINT fk_acl_document FOREIGN KEY(document_id) REFERENCES kb_document(id) ON DELETE CASCADE,
          CONSTRAINT fk_acl_user FOREIGN KEY(user_id) REFERENCES app_user(id) ON DELETE CASCADE
        ) ENGINE=InnoDB"""))
        if not await has_index(db, "kb_document", "idx_doc_tenant_visibility"):
            await db.execute(text("CREATE INDEX idx_doc_tenant_visibility ON kb_document(tenant_id,visibility)"))
    await engine.dispose()
    print("auth_acl_migration=ok users=admin,engineer tenant=" + settings.auth_default_tenant)


async def has_index(db, table_name: str, index_name: str) -> bool:
    result = await db.execute(text("""
        SELECT COUNT(*) FROM information_schema.statistics
        WHERE table_schema=DATABASE() AND table_name=:table AND index_name=:name
    """), {"table": table_name, "name": index_name})
    return bool(result.scalar())


if __name__ == "__main__":
    asyncio.run(main())
