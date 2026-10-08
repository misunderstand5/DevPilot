import asyncio

from sqlalchemy import text

import _bootstrap  # noqa: F401
from app.db import engine, session_scope
from app.services.rbac import ROLE_INHERITANCE, ROLE_PERMISSIONS, permissions_for_roles


ROLE_NAMES = {
    "end_user": "终端用户",
    "developer": "开发者",
    "tenant_admin": "租户管理员",
    "system_admin": "系统管理员",
}


async def main() -> None:
    async with session_scope() as db:
        await db.execute(text("""CREATE TABLE IF NOT EXISTS rbac_role (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,code VARCHAR(64) NOT NULL UNIQUE,name VARCHAR(100) NOT NULL,
          description VARCHAR(500) NULL,system_role TINYINT(1) NOT NULL DEFAULT 1,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB"""))
        await db.execute(text("""CREATE TABLE IF NOT EXISTS rbac_permission (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,code VARCHAR(128) NOT NULL UNIQUE,
          description VARCHAR(500) NULL,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB"""))
        await db.execute(text("""CREATE TABLE IF NOT EXISTS rbac_role_permission (
          role_id BIGINT NOT NULL,permission_id BIGINT NOT NULL,PRIMARY KEY(role_id,permission_id),
          CONSTRAINT fk_rp_role FOREIGN KEY(role_id) REFERENCES rbac_role(id) ON DELETE CASCADE,
          CONSTRAINT fk_rp_permission FOREIGN KEY(permission_id) REFERENCES rbac_permission(id) ON DELETE CASCADE
        ) ENGINE=InnoDB"""))
        await db.execute(text("""CREATE TABLE IF NOT EXISTS rbac_user_role (
          user_id CHAR(36) NOT NULL,role_id BIGINT NOT NULL,assigned_by CHAR(36) NULL,
          expires_at DATETIME NULL,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY(user_id,role_id),
          CONSTRAINT fk_ur_user FOREIGN KEY(user_id) REFERENCES app_user(id) ON DELETE CASCADE,
          CONSTRAINT fk_ur_role FOREIGN KEY(role_id) REFERENCES rbac_role(id) ON DELETE CASCADE
        ) ENGINE=InnoDB"""))
        await db.execute(text("""CREATE TABLE IF NOT EXISTS rbac_resource_scope (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,user_id CHAR(36) NOT NULL,permission_code VARCHAR(128) NOT NULL,
          resource_type VARCHAR(32) NOT NULL,resource_key VARCHAR(255) NOT NULL,expires_at DATETIME NULL,
          created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE KEY uk_user_scope(user_id,permission_code,resource_type,resource_key),
          CONSTRAINT fk_scope_user FOREIGN KEY(user_id) REFERENCES app_user(id) ON DELETE CASCADE
        ) ENGINE=InnoDB"""))
        await db.execute(text("""CREATE TABLE IF NOT EXISTS rbac_audit_log (
          id BIGINT AUTO_INCREMENT PRIMARY KEY,tenant_id CHAR(36) NULL,actor_user_id CHAR(36) NULL,
          action VARCHAR(100) NOT NULL,target_type VARCHAR(64) NOT NULL,target_id VARCHAR(255) NULL,
          detail_json JSON NULL,created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
          INDEX idx_rbac_audit_tenant_time(tenant_id,created_at)
        ) ENGINE=InnoDB"""))

        for role, name in ROLE_NAMES.items():
            await db.execute(text("""INSERT INTO rbac_role(code,name,description,system_role)
              VALUES(:code,:name,:description,1)
              ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description)"""), {
                "code": role, "name": name,
                "description": "inherits: " + (", ".join(ROLE_INHERITANCE[role]) or "none"),
            })
        all_permissions = sorted(set().union(*ROLE_PERMISSIONS.values()))
        for permission in all_permissions:
            await db.execute(text("""INSERT INTO rbac_permission(code,description)
              VALUES(:code,:description) ON DUPLICATE KEY UPDATE description=VALUES(description)"""),
                             {"code": permission, "description": permission})
        for role in ROLE_NAMES:
            for permission in sorted(permissions_for_roles((role,))):
                await db.execute(text("""INSERT IGNORE INTO rbac_role_permission(role_id,permission_id)
                  SELECT r.id,p.id FROM rbac_role r,rbac_permission p WHERE r.code=:role AND p.code=:permission"""),
                                 {"role": role, "permission": permission})

        # Idempotent legacy mapping. The demo engineer is a developer; other
        # historical members remain end users.
        await db.execute(text("""INSERT IGNORE INTO rbac_user_role(user_id,role_id)
          SELECT u.id,r.id FROM app_user u JOIN rbac_role r ON r.code=
          CASE WHEN u.role='ADMIN' THEN 'tenant_admin'
               WHEN u.username='engineer' THEN 'developer' ELSE 'end_user' END"""))
        await db.execute(text("""INSERT IGNORE INTO rbac_resource_scope(user_id,permission_code,resource_type,resource_key)
          SELECT id,'*','SERVICE','*' FROM app_user WHERE username='engineer'"""))
        await db.execute(text("""INSERT IGNORE INTO rbac_resource_scope(user_id,permission_code,resource_type,resource_key)
          SELECT id,'*','REPOSITORY','*' FROM app_user WHERE username='engineer'"""))
    await engine.dispose()
    print("rbac_migration=ok roles=4 resource_scopes=enabled")


if __name__ == "__main__":
    asyncio.run(main())
