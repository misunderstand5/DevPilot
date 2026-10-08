from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # Canonical request identity
    session_id: str
    user_id: str
    tenant_id: str
    user_role: str
    user_roles: list[str]
    user_permissions: list[str]
    resource_scopes: list[dict[str, str]]
    trace_id: str
    query: str
    resolved_query: str
    execution_mode: str

    # Routing and normalized entities
    intent: str
    route_reason: str
    route_confidence: float
    current_service: str | None
    canonical_entities: dict[str, Any]
    task_complexity: str
    task_risk: str
    ops_action: str | None
    needs_github_evidence: bool
    selected_path: str
    selected_agents: list[str]

    # Conversation projection (not specialist scratch space)
    conversation_summary: str
    recent_messages: list[dict[str, Any]]
    current_topic: str | None
    session_memory: dict[str, Any]
    long_term_memories: list[dict[str, Any]]

    # Current workflow only
    rag_results: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    external_evidence: list[dict[str, Any]]
    agent_results: dict[str, Any]
    citations: list[dict[str, Any]]
    tools_used: list[str]
    model_calls: list[dict[str, Any]]
    model_route_log: list[dict[str, Any]]
    final_answer: str
    error_state: dict[str, Any] | None
