-- DevPilot four-role RBAC schema. Permission seeding and legacy-user mapping
-- are performed idempotently by scripts/migrate_rbac.py.
CREATE TABLE IF NOT EXISTS rbac_role (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(64) NOT NULL UNIQUE,
  name VARCHAR(100) NOT NULL,
  description VARCHAR(500) NULL,
  system_role TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rbac_permission (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  code VARCHAR(128) NOT NULL UNIQUE,
  description VARCHAR(500) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rbac_role_permission (
  role_id BIGINT NOT NULL,
  permission_id BIGINT NOT NULL,
  PRIMARY KEY(role_id, permission_id),
  CONSTRAINT fk_rp_role FOREIGN KEY(role_id) REFERENCES rbac_role(id) ON DELETE CASCADE,
  CONSTRAINT fk_rp_permission FOREIGN KEY(permission_id) REFERENCES rbac_permission(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rbac_user_role (
  user_id CHAR(36) NOT NULL,
  role_id BIGINT NOT NULL,
  assigned_by CHAR(36) NULL,
  expires_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(user_id, role_id),
  CONSTRAINT fk_ur_user FOREIGN KEY(user_id) REFERENCES app_user(id) ON DELETE CASCADE,
  CONSTRAINT fk_ur_role FOREIGN KEY(role_id) REFERENCES rbac_role(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rbac_resource_scope (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id CHAR(36) NOT NULL,
  permission_code VARCHAR(128) NOT NULL,
  resource_type VARCHAR(32) NOT NULL,
  resource_key VARCHAR(255) NOT NULL,
  expires_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_user_scope(user_id, permission_code, resource_type, resource_key),
  CONSTRAINT fk_scope_user FOREIGN KEY(user_id) REFERENCES app_user(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS rbac_audit_log (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  tenant_id CHAR(36) NULL,
  actor_user_id CHAR(36) NULL,
  action VARCHAR(100) NOT NULL,
  target_type VARCHAR(64) NOT NULL,
  target_id VARCHAR(255) NULL,
  detail_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_rbac_audit_tenant_time(tenant_id, created_at)
) ENGINE=InnoDB;
