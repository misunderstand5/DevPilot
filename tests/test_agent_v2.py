import pytest
from types import SimpleNamespace

from app.agent.context import ContextProjector
from app.agent.graph import route_node
from app.agent.registry import AGENT_REGISTRY, ModelRole
from app.agent.router import SemanticRouter, is_conversation_query, needs_github_evidence, normalize_service
from app.agent.specialists import direct_agent


@pytest.mark.parametrize(("query", "intent", "action"), [
    ("订单服务怎么部署？", "knowledge", None),
    ("订单服务最近部署了什么？", "database", "deployments"),
    ("订单服务最近部署为什么失败，按照 SOP 怎么排查？", "mixed", "deployments"),
    ("支付服务当前状态", "database", "service_status"),
    ("用户服务未解决故障", "database", "incidents"),
    ("请依据知识库概括 order-service 发布关键步骤和回滚条件", "knowledge", None),
    ("你好", "direct", None),
    ("order-service 这次发布的 commit 改了什么？", "mixed", "deployments"),
])
def test_semantic_routing(query, intent, action):
    decision = SemanticRouter().deterministic(query)
    assert decision.intent == intent
    assert decision.ops_action == action


def test_chinese_service_aliases_are_canonical():
    assert normalize_service("看看订单服务") == "order-service"
    assert normalize_service("支付怎么样") == "payment-service"
    assert normalize_service("它呢", "user-service") == "user-service"


def test_multi_turn_inherits_service_and_selects_complex_path():
    decision = SemanticRouter().deterministic("那按照 SOP 接下来怎么排查？", "order-service")
    assert decision.service_name == "order-service"
    assert decision.intent == "mixed"
    assert decision.complexity == "complex"


@pytest.mark.parametrize("query", [
    "请记住：我叫小林", "我刚才说了什么？", "你还记得我吗？", "你有上下文记忆吗？", "我叫什么？",
])
def test_conversation_memory_questions_never_route_to_rag(query):
    decision = SemanticRouter().deterministic(query)
    assert decision.intent == "direct"
    assert is_conversation_query(query)


@pytest.mark.asyncio
async def test_fast_path_model_binding_is_local():
    state = await route_node({
        "query": "订单服务怎么部署？", "trace_id": "trace", "current_service": None,
        "model_calls": [],
    })
    assert state["selected_path"] == "fast_knowledge"
    assert state["selected_agents"] == ["knowledge_agent"]
    assert AGENT_REGISTRY["knowledge_agent"].model_role == ModelRole.LOCAL


def test_complex_agent_model_roles():
    assert AGENT_REGISTRY["ops_agent"].model_role == ModelRole.LOCAL
    assert AGENT_REGISTRY["diagnosis_agent"].model_role == ModelRole.STRONG
    assert AGENT_REGISTRY["supervisor_agent"].model_role == ModelRole.STRONG


def test_github_evidence_is_requested_only_for_code_or_ci_questions():
    assert needs_github_evidence("order-service 这次 commit 改了什么？")
    assert needs_github_evidence("为什么 GitHub Actions CI 失败？")
    assert not needs_github_evidence("order-service 最近发布是否成功？")


def test_context_projection_is_least_privilege():
    state = {
        "query": "为什么失败", "current_service": "order-service", "current_topic": "mixed",
        "recent_messages": [{"role": "user", "content": "x"}],
        "agent_results": {"ops_agent": {"facts": [{"deployments": [{"status": "FAILED"}]}]}},
        "sql_debug": "SELECT secret", "raw_tool_log": [{"token": "secret"}],
    }
    projected = ContextProjector().for_knowledge(state)
    assert projected["current_service"] == "order-service"
    assert "sql_debug" not in projected
    assert "raw_tool_log" not in projected


def test_every_reasoning_projection_contains_conversation_context():
    state = {
        "query": "第二个呢？", "current_service": "order-service", "current_topic": "knowledge",
        "conversation_summary": "用户正在检查两次发布。",
        "recent_messages": [{"role": "user", "content": "列出两次发布"}],
        "agent_results": {},
    }
    projector = ContextProjector()
    for projected in (
        projector.for_knowledge(state), projector.for_diagnosis(state), projector.for_supervisor(state)
    ):
        assert projected["conversation_summary"] == "用户正在检查两次发布。"
        assert projected["recent_messages"][-1]["content"] == "列出两次发布"


@pytest.mark.asyncio
async def test_direct_agent_receives_summary_and_recent_messages(monkeypatch):
    captured = {}

    async def fake_call(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            content="你刚才说要检查 order-service。",
            record=SimpleNamespace(model_dump=lambda: {"agent_name": "direct_agent"}),
        )

    monkeypatch.setattr("app.agent.specialists.model_gateway.call", fake_call)
    result = await direct_agent({
        "query": "我刚才说了什么？", "trace_id": "trace", "current_service": "order-service",
        "current_topic": "database", "conversation_summary": "用户正在检查订单服务。",
        "recent_messages": [{"role": "user", "content": "帮我检查 order-service"}],
        "agent_results": {}, "model_calls": [],
    })
    prompt = captured["messages"][-1]["content"]
    assert "用户正在检查订单服务" in prompt
    assert "帮我检查 order-service" in prompt
    assert "我刚才说了什么" in prompt
    assert result["final_answer"] == "你刚才说要检查 order-service。"


def test_registry_tools_are_allowlisted():
    assert set(AGENT_REGISTRY["ops_agent"].tools) == {
        "get_service_status", "recent_deployments", "open_incidents", "open_tickets", "mcp.github.get_commit"
    }
