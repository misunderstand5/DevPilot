from functools import lru_cache
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DevPilot"
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8001

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3307
    mysql_user: str = "devpilot"
    mysql_password: str = "devpilot123"
    mysql_database: str = "devpilot"

    redis_url: str = "redis://127.0.0.1:6379/0"
    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "devpilot_kb_v1"
    qdrant_memory_collection: str = "devpilot_user_memory_v1"

    llm_mode: str = "mock"  # mock | openai_compatible
    llm_base_url: str = "http://127.0.0.1:8000/v1"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen3-4B-Instruct-2507"

    # V2 model roles. LOCAL falls back to the legacy LLM_* settings above.
    local_model_base_url: str | None = None
    local_model_api_key: str | None = None
    local_model_name: str | None = None
    local_model_provider: str = "local_vllm"
    strong_model_base_url: str | None = None
    strong_model_api_key: str | None = None
    strong_model_name: str | None = None
    strong_model_provider: str = "modelscope"
    allow_cloud_internal_data: bool = False
    model_timeout_seconds: float = 60.0
    model_max_attempts: int = 2

    # Optional outbound MCP integration. Internal MySQL tools remain direct
    # Python calls; MCP is reserved for external systems such as GitHub.
    github_mcp_enabled: bool = False
    github_mcp_url: str = ""
    github_mcp_token: SecretStr | None = None
    github_mcp_tool_allowlist: list[str] = Field(default_factory=lambda: ["get_commit"])
    github_mcp_repositories: dict[str, str] = Field(default_factory=dict)
    github_mcp_timeout_seconds: float = 8.0
    github_mcp_max_attempts: int = 2
    github_mcp_max_result_chars: int = 12000

    embed_model: str = "intfloat/multilingual-e5-small"
    embed_device: str = "cpu"
    rerank_enabled: bool = False
    rerank_model: str = "BAAI/bge-reranker-v2-m3"

    rag_dense_top_k: int = 20
    rag_bm25_top_k: int = 20
    rag_fused_top_k: int = 10
    rag_final_top_k: int = 5
    rag_min_dense_score: float = 0.25

    session_ttl_seconds: int = 86400
    cache_ttl_seconds: int = 600
    rate_limit_per_minute: int = 60

    # Local authentication. Production deployments must override the secret and
    # bootstrap passwords through environment variables or a secret manager.
    auth_secret_key: str = "devpilot-dev-secret-change-before-production"
    auth_token_minutes: int = 480
    auth_default_tenant: str = "devpilot"
    auth_admin_password: str = ""
    auth_engineer_password: str = ""

    # Context engineering budgets. Token counts are conservative estimates and
    # deliberately stay below the local model's 8k context window.
    context_max_input_tokens: int = 6000
    context_recent_tokens: int = 2800
    context_summary_tokens: int = 900
    context_message_tokens: int = 900
    context_history_message_limit: int = 100
    context_llm_summary_enabled: bool = True
    long_term_memory_enabled: bool = True
    long_term_memory_top_k: int = 5
    long_term_memory_min_score: float = 0.42

    # .env.local is intended for machine-local connector credentials and is
    # ignored by Git. Values there override the shared local .env file.
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    @property
    def sqlalchemy_url(self) -> str:
        return (
            f"mysql+aiomysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def resolved_local_model_base_url(self) -> str:
        return self.local_model_base_url or self.llm_base_url

    @property
    def resolved_local_model_api_key(self) -> str:
        return self.local_model_api_key or self.llm_api_key

    @property
    def resolved_local_model_name(self) -> str:
        return self.local_model_name or self.llm_model

    @property
    def strong_model_configured(self) -> bool:
        return bool(
            self.strong_model_base_url
            and self.strong_model_api_key
            and self.strong_model_name
        )

    @property
    def insecure_production_auth(self) -> bool:
        if self.app_env.lower() not in {"prod", "production"}:
            return False
        defaults = {
            "devpilot-dev-secret-change-before-production",
            "ChangeMe-DevPilot-2026!",
            "Engineer-DevPilot-2026!",
        }
        return (
            not self.auth_admin_password
            or not self.auth_engineer_password
            or self.auth_secret_key in defaults
            or self.auth_admin_password in defaults
            or self.auth_engineer_password in defaults
            or len(self.auth_secret_key) < 32
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
