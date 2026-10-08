from typing import Any

from app.agent.state import AgentState


CONVERSATION_RULES = (
    "会话摘要和最近消息是当前会话的上下文，不是知识库文档。回答必须承接其中已明确的信息；"
    "遇到‘它/这个/刚才/第二个/继续’等表达时，优先结合最近消息解析；"
    "新信息与旧信息冲突时以用户最新表述为准；只有上下文确实不足时才追问。"
    "只要下方提供了会话内容，就不得声称自己看不到本会话历史。"
)


class ContextProjector:
    """Produces least-privilege, serializable context for each specialist."""

    @staticmethod
    def _base(state: AgentState) -> dict[str, Any]:
        return {
            "query": state.get("query", ""),
            "resolved_query": state.get("resolved_query", state.get("query", "")),
            "current_service": state.get("current_service"),
            "current_topic": state.get("current_topic"),
            "session_memory": state.get("session_memory", {}),
            "long_term_memories": state.get("long_term_memories", [])[:5],
            "conversation_summary": state.get("conversation_summary", ""),
            "recent_messages": state.get("recent_messages", [])[-8:],
            "conversation_rules": CONVERSATION_RULES,
        }

    def conversation_prompt(self, state: AgentState) -> str:
        """Render one bounded, clearly delimited context block for model prompts."""
        context = self._base(state)
        return (
            "<conversation_context>\n"
            f"摘要：{context['conversation_summary'] or '（暂无较早对话摘要）'}\n"
            f"最近消息：{context['recent_messages'] or '（这是本会话第一条消息）'}\n"
            f"当前服务：{context['current_service'] or '未确定'}\n"
            f"当前主题：{context['current_topic'] or '未确定'}\n"
            f"结构化会话记忆：{context['session_memory'] or '（暂无）'}\n"
            f"跨会话长期记忆：{context['long_term_memories'] or '（暂无）'}\n"
            "</conversation_context>\n"
            f"<conversation_rules>{CONVERSATION_RULES}</conversation_rules>"
        )

    def for_knowledge(self, state: AgentState) -> dict[str, Any]:
        context = self._base(state)
        context.update({
            "delegated_task": "检索并总结与问题相关的企业知识与 SOP",
            "failure_facts": self._compact_ops_facts(state),
        })
        return context

    def for_ops(self, state: AgentState) -> dict[str, Any]:
        context = self._base(state)
        context.update({
            "delegated_task": "查询明确的实时业务事实",
            "ops_action": state.get("ops_action"),
            "time_range_days": (
                state.get("session_memory", {}).get("entities", {}).get("time_range_days")
                or self._time_range(state.get("query", ""))
            ),
        })
        return context

    def for_diagnosis(self, state: AgentState) -> dict[str, Any]:
        context = self._base(state)
        context.update({
            "problem": state.get("query", ""),
            "confirmed_facts": self._compact_ops_facts(state),
            "knowledge_evidence": self._compact_knowledge(state),
        })
        return context

    def for_supervisor(self, state: AgentState) -> dict[str, Any]:
        context = self._base(state)
        context.update({
            "agent_results": self._compact_agent_results(state),
            "citations": state.get("citations", [])[:5],
        })
        return context

    @staticmethod
    def _time_range(query: str) -> int:
        if "30天" in query or "一个月" in query:
            return 30
        if "14天" in query or "两周" in query:
            return 14
        return 7

    @staticmethod
    def _compact_ops_facts(state: AgentState) -> list[dict[str, Any]]:
        result = state.get("agent_results", {}).get("ops_agent", {})
        if not isinstance(result, dict):
            return []
        compact = []
        for group in result.get("facts", [])[:4]:
            compact.append({key: value[:10] if isinstance(value, list) else value for key, value in group.items()})
        return compact

    @staticmethod
    def _compact_knowledge(state: AgentState) -> list[dict[str, Any]]:
        result = state.get("agent_results", {}).get("knowledge_agent", {})
        if not isinstance(result, dict):
            return []
        return [
            {"title": x.get("title"), "content": x.get("content", "")[:900]}
            for x in result.get("evidence", [])[:4]
        ]

    def _compact_agent_results(self, state: AgentState) -> dict[str, Any]:
        results = state.get("agent_results", {})
        knowledge = results.get("knowledge_agent", {})
        diagnosis = results.get("diagnosis_agent", {})
        return {
            "ops_agent": {"facts": self._compact_ops_facts(state)},
            "knowledge_agent": {
                "summary": str(knowledge.get("summary", ""))[:2200],
                "evidence": self._compact_knowledge(state),
            } if isinstance(knowledge, dict) else {},
            "diagnosis_agent": {
                "findings": [str(x)[:1500] for x in diagnosis.get("findings", [])[:3]],
                "recommended_actions": diagnosis.get("recommended_actions", [])[:6],
            } if isinstance(diagnosis, dict) else {},
        }


context_projector = ContextProjector()
