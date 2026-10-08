from dataclasses import dataclass
from enum import StrEnum


class ModelRole(StrEnum):
    LOCAL = "LOCAL"
    STRONG = "STRONG"


class PrivacyMode(StrEnum):
    LOCAL_ONLY = "LOCAL_ONLY"
    CLOUD_ALLOWED = "CLOUD_ALLOWED"


@dataclass(frozen=True)
class AgentDefinition:
    name: str
    responsibility: str
    model_role: ModelRole
    tools: tuple[str, ...] = ()


AGENT_REGISTRY = {
    "direct_agent": AgentDefinition("direct_agent", "简单对话与快速响应", ModelRole.LOCAL),
    "knowledge_agent": AgentDefinition("knowledge_agent", "企业文档、SOP 与 RAG", ModelRole.LOCAL, ("rag_search",)),
    "ops_agent": AgentDefinition(
        "ops_agent",
        "服务、发布、故障与工单事实",
        ModelRole.LOCAL,
        ("get_service_status", "recent_deployments", "open_incidents", "open_tickets", "mcp.github.get_commit"),
    ),
    "diagnosis_agent": AgentDefinition("diagnosis_agent", "多来源诊断与修复建议", ModelRole.STRONG),
    "supervisor_agent": AgentDefinition("supervisor_agent", "复杂任务协调与最终综合", ModelRole.STRONG),
}


def get_agent(name: str) -> AgentDefinition:
    return AGENT_REGISTRY[name]
