USE devpilot;

CREATE TABLE IF NOT EXISTS agent_session_snapshot (
  session_id CHAR(36) PRIMARY KEY,
  user_id CHAR(36) NOT NULL,
  summary MEDIUMTEXT,
  summary_through_seq BIGINT NOT NULL DEFAULT 0,
  memory_json JSON NOT NULL,
  context_json JSON,
  version INT NOT NULL DEFAULT 1,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_snapshot_session FOREIGN KEY(session_id) REFERENCES agent_session(id) ON DELETE CASCADE,
  INDEX idx_snapshot_user(user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS user_memory (
  id CHAR(36) PRIMARY KEY,
  tenant_id CHAR(36) NOT NULL,
  user_id CHAR(36) NOT NULL,
  memory_type ENUM('identity','preference','project','constraint') NOT NULL,
  content VARCHAR(1000) NOT NULL,
  fingerprint CHAR(64) NOT NULL,
  source_session_id CHAR(36),
  confidence DECIMAL(4,3) NOT NULL DEFAULT 1.000,
  status ENUM('ACTIVE','SUPERSEDED','DELETED') NOT NULL DEFAULT 'ACTIVE',
  superseded_by CHAR(36),
  valid_from DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at DATETIME,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  last_accessed_at DATETIME,
  UNIQUE KEY uk_user_memory_fingerprint(tenant_id,user_id,fingerprint),
  INDEX idx_user_memory_lookup(tenant_id,user_id,status,updated_at),
  CONSTRAINT fk_memory_user FOREIGN KEY(user_id) REFERENCES app_user(id) ON DELETE CASCADE,
  CONSTRAINT fk_memory_session FOREIGN KEY(source_session_id) REFERENCES agent_session(id) ON DELETE SET NULL
) ENGINE=InnoDB;

ALTER TABLE user_memory ADD COLUMN IF NOT EXISTS superseded_by CHAR(36) NULL AFTER status;
ALTER TABLE user_memory ADD COLUMN IF NOT EXISTS valid_from DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER superseded_by;
ALTER TABLE user_memory ADD COLUMN IF NOT EXISTS expires_at DATETIME NULL AFTER valid_from;
ALTER TABLE user_memory MODIFY COLUMN status ENUM('ACTIVE','SUPERSEDED','DELETED') NOT NULL DEFAULT 'ACTIVE';
