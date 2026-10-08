from langgraph.graph import END, StateGraph

from app.agent.router import needs_github_evidence, semantic_router
from app.agent.specialists import (
    diagnosis_agent,
    direct_agent,
    knowledge_agent,
    ops_agent,
    single_agent_baseline,
    supervisor_agent,
)
from app.agent.state import AgentState
from app.services.model_gateway import model_gateway


async def route_node(state: AgentState) -> dict:
    decision, calls = await semantic_router.route(
        state.get("resolved_query", state["query"]), state.get("current_service"), model_gateway, state["trace_id"],
        state.get("conversation_summary", ""), state.get("recent_messages", []),
    )
    if state.get("execution_mode") == "single":
        path, agents = "single", ["single_agent_baseline"]
    elif decision.intent == "direct":
        path, agents = "fast_direct", ["direct_agent"]
    elif decision.intent == "knowledge" and decision.complexity == "simple":
        path, agents = "fast_knowledge", ["knowledge_agent"]
    elif decision.intent in {"database", "ops_tool"} and decision.complexity == "simple":
        path, agents = "fast_ops", ["ops_agent"]
    else:
        path, agents = "complex", ["ops_agent", "knowledge_agent", "diagnosis_agent", "supervisor_agent"]
    return {
        "intent": decision.intent,
        "route_reason": decision.reason,
        "route_confidence": decision.confidence,
        "current_service": decision.service_name,
        "canonical_entities": {"service_name": decision.service_name},
        "task_complexity": decision.complexity,
        "task_risk": decision.risk,
        "ops_action": decision.ops_action,
        "needs_github_evidence": needs_github_evidence(state.get("resolved_query", state["query"])),
        "selected_path": path,
        "selected_agents": agents,
        "model_calls": list(state.get("model_calls", [])) + calls,
        "model_route_log": [{"path": path, "agents": agents, "reason": decision.reason}],
        "current_topic": decision.intent,
    }


def route_edge(state: AgentState) -> str:
    return state["selected_path"]


async def complex_node(state: AgentState) -> dict:
    working = dict(state)
    for specialist in (
        lambda value: ops_agent(value, synthesize=False),
        lambda value: knowledge_agent(value, synthesize=False),
        diagnosis_agent,
        supervisor_agent,
    ):
        update = await specialist(working)
        working.update(update)
    return {key: value for key, value in working.items() if state.get(key) != value}


builder = StateGraph(AgentState)
builder.add_node("route", route_node)
builder.add_node("direct", direct_agent)
builder.add_node("knowledge", knowledge_agent)
builder.add_node("ops", ops_agent)
builder.add_node("complex", complex_node)
builder.add_node("single", single_agent_baseline)
builder.set_entry_point("route")
builder.add_conditional_edges("route", route_edge, {
    "fast_direct": "direct",
    "fast_knowledge": "knowledge",
    "fast_ops": "ops",
    "complex": "complex",
    "single": "single",
})
for node in ("direct", "knowledge", "ops", "complex", "single"):
    builder.add_edge(node, END)

agent_graph = builder.compile()
