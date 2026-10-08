CREATE DATABASE IF NOT EXISTS devpilot CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE devpilot;

CREATE TABLE IF NOT EXISTS service (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(100) NOT NULL UNIQUE,
  owner_team VARCHAR(100) NOT NULL,
  repo_url VARCHAR(500),
  environment VARCHAR(32) NOT NULL DEFAULT 'prod',
  status ENUM('UP','DEGRADED','DOWN','UNKNOWN') NOT NULL DEFAULT 'UNKNOWN',
  description TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_service_status(status), INDEX idx_service_team(owner_team)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS deployment (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  service_id BIGINT NOT NULL,
  version VARCHAR(100) NOT NULL,
  environment VARCHAR(32) NOT NULL,
  status ENUM('RUNNING','SUCCESS','FAILED','ROLLED_BACK') NOT NULL,
  started_at DATETIME NOT NULL,
  finished_at DATETIME,
  operator_name VARCHAR(100),
  commit_sha VARCHAR(64),
  notes TEXT,
  CONSTRAINT fk_deploy_service FOREIGN KEY(service_id) REFERENCES service(id),
  INDEX idx_deploy_service_time(service_id, started_at),
  INDEX idx_deploy_status_time(status, started_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS incident (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  service_id BIGINT NOT NULL,
  severity ENUM('P0','P1','P2','P3') NOT NULL,
  title VARCHAR(255) NOT NULL,
  status ENUM('OPEN','MITIGATING','RESOLVED') NOT NULL DEFAULT 'OPEN',
  started_at DATETIME NOT NULL,
  resolved_at DATETIME,
  root_cause TEXT,
  resolution TEXT,
  CONSTRAINT fk_incident_service FOREIGN KEY(service_id) REFERENCES service(id),
  INDEX idx_incident_service_status(service_id,status),
  INDEX idx_incident_severity_status(severity,status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ticket (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  incident_id BIGINT NULL,
  service_id BIGINT NULL,
  title VARCHAR(255) NOT NULL,
  description TEXT,
  status ENUM('OPEN','IN_PROGRESS','DONE','CLOSED') NOT NULL DEFAULT 'OPEN',
  priority ENUM('P0','P1','P2','P3') NOT NULL DEFAULT 'P2',
  assignee VARCHAR(100),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT fk_ticket_incident FOREIGN KEY(incident_id) REFERENCES incident(id),
  CONSTRAINT fk_ticket_service FOREIGN KEY(service_id) REFERENCES service(id),
  INDEX idx_ticket_status_priority(status,priority)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS kb_document (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  source_uri VARCHAR(1000) NOT NULL,
  title VARCHAR(255) NOT NULL,
  doc_type VARCHAR(32) NOT NULL,
  checksum CHAR(64) NOT NULL UNIQUE,
  version INT NOT NULL DEFAULT 1,
  status ENUM('PENDING','INDEXED','FAILED') NOT NULL DEFAULT 'PENDING',
  chunk_count INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_doc_status(status),
  INDEX idx_doc_source_uri(source_uri(191))
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS kb_chunk (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  document_id BIGINT NOT NULL,
  vector_point_id VARCHAR(64) NOT NULL UNIQUE,
  chunk_index INT NOT NULL,
  heading VARCHAR(255),
  content MEDIUMTEXT NOT NULL,
  char_count INT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_chunk_document FOREIGN KEY(document_id) REFERENCES kb_document(id) ON DELETE CASCADE,
  UNIQUE KEY uk_document_chunk(document_id,chunk_index),
  FULLTEXT KEY ft_chunk_content(content)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_session (
  id CHAR(36) PRIMARY KEY,
  user_id VARCHAR(100) NOT NULL,
  title VARCHAR(255),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_active_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_session_user_time(user_id,last_active_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS agent_message (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id CHAR(36) NOT NULL,
  role ENUM('user','assistant','system','tool') NOT NULL,
  content MEDIUMTEXT NOT NULL,
  trace_id CHAR(36),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_message_session FOREIGN KEY(session_id) REFERENCES agent_session(id) ON DELETE CASCADE,
  INDEX idx_message_session_time(session_id,created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS tool_call_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id CHAR(36),
  trace_id CHAR(36) NOT NULL,
  tool_name VARCHAR(100) NOT NULL,
  args_json JSON,
  result_json JSON,
  status ENUM('SUCCESS','FAILED','DENIED') NOT NULL,
  latency_ms INT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_tool_trace(trace_id), INDEX idx_tool_name_time(tool_name,created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS model_call_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id CHAR(36), trace_id CHAR(36) NOT NULL,
  agent_name VARCHAR(100) NOT NULL,
  requested_model_role VARCHAR(20) NOT NULL,
  served_model_role VARCHAR(20) NOT NULL,
  model_name VARCHAR(255) NOT NULL, provider VARCHAR(100) NOT NULL,
  fallback BOOLEAN NOT NULL DEFAULT FALSE,
  fallback_reason VARCHAR(255), latency_ms INT,
  prompt_tokens INT, completion_tokens INT, error VARCHAR(500),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_model_trace(trace_id), INDEX idx_model_agent_time(agent_name,created_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS feedback (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  message_id BIGINT NOT NULL,
  rating TINYINT NOT NULL,
  comment VARCHAR(1000),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_feedback_message FOREIGN KEY(message_id) REFERENCES agent_message(id),
  CHECK (rating BETWEEN 1 AND 5)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS eval_case (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  case_key VARCHAR(64) NOT NULL UNIQUE,
  category VARCHAR(50) NOT NULL,
  question TEXT NOT NULL,
  expected_answer TEXT,
  expected_doc_title VARCHAR(255),
  expected_tool VARCHAR(100),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_eval_category(category,enabled)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS eval_run (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_name VARCHAR(255) NOT NULL,
  config_json JSON,
  status ENUM('RUNNING','SUCCESS','FAILED') NOT NULL DEFAULT 'RUNNING',
  started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS eval_result (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  run_id BIGINT NOT NULL,
  case_id BIGINT NOT NULL,
  answer MEDIUMTEXT,
  intent VARCHAR(50),
  tool_name VARCHAR(100),
  citations_json JSON,
  metrics_json JSON,
  latency_ms INT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT fk_eval_run FOREIGN KEY(run_id) REFERENCES eval_run(id) ON DELETE CASCADE,
  CONSTRAINT fk_eval_case FOREIGN KEY(case_id) REFERENCES eval_case(id),
  INDEX idx_eval_result_run(run_id)
) ENGINE=InnoDB;
