CREATE TABLE IF NOT EXISTS model_call_log (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  session_id CHAR(36),
  trace_id CHAR(36) NOT NULL,
  agent_name VARCHAR(100) NOT NULL,
  requested_model_role VARCHAR(20) NOT NULL,
  served_model_role VARCHAR(20) NOT NULL,
  model_name VARCHAR(255) NOT NULL,
  provider VARCHAR(100) NOT NULL,
  fallback BOOLEAN NOT NULL DEFAULT FALSE,
  fallback_reason VARCHAR(255),
  latency_ms INT,
  prompt_tokens INT,
  completion_tokens INT,
  error VARCHAR(500),
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_model_trace(trace_id),
  INDEX idx_model_agent_time(agent_name,created_at)
) ENGINE=InnoDB;
