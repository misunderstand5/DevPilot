import json
import re

from app.agent.context import CONVERSATION_RULES
from app.schemas import RouteDecisionV2


SERVICE_ALIASES = {
    "order-service": "order-service",
    "订单服务": "order-service",
    "订单": "order-service",
    "user-service": "user-service",
    "用户服务": "user-service",
    "用户": "user-service",
    "payment-service": "payment-service",
    "支付服务": "payment-service",
    "支付": "payment-service",
    "api-gateway": "api-gateway",
    "inventory-service": "inventory-service",
    "notification-service": "notification-service",
    "pricing-service": "pricing-service",
    "promotion-service": "promotion-service",
    "risk-service": "risk-service",
    "search-service": "search-service",
    "settlement-service": "settlement-service",
    "shipping-service": "shipping-service",
}

CONVERSATION_QUERY_MARKERS = (
    "请记住", "记住：", "帮我记", "我叫", "我的名字", "刚才说", "前面说", "之前说", "还记得", "记得我", "我叫什么",
    "上下文记忆", "会话记忆", "对话记忆", "我们的对话", "当前会话",
)

GITHUB_EVIDENCE_MARKERS = (
    "commit", "pull request", " pr ", "代码变更", "改了什么", "提交记录",
    "workflow", "github actions", "ci 失败", "ci失败", "流水线失败",
)


def is_conversation_query(query: str) -> bool:
    return any(marker in query.lower() for marker in CONVERSATION_QUERY_MARKERS)


def needs_github_evidence(query: str) -> bool:
    normalized = f" {query.lower()} "
    return any(marker in normalized for marker in GITHUB_EVIDENCE_MARKERS)


def normalize_service(query: str, previous: str | None = None) -> str | None:
    lowered = query.lower()
    for alias, canonical in sorted(SERVICE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias.lower() in lowered:
            return canonical
    return previous


class SemanticRouter:
    """Hard semantic distinctions first; bounded LLM parsing only for ambiguity."""

    def deterministic(self, query: str, previous_service: str | None = None) -> RouteDecisionV2 | None:
        q = query.lower().strip()
        service = normalize_service(q, previous_service)
        greeting = q in {"你好", "您好", "hello", "hi", "嗨", "谢谢", "感谢"}
        conversation_question = is_conversation_query(q)
        procedure = any(x in q for x in (
            "怎么部署", "如何部署", "部署流程", "发布流程", "关键步骤", "操作步骤",
            "回滚条件", "发布条件", "知识库", "文档", "指南", "sop", "手册", "规范", "错误码", "接口文档",
            "先检查", "禁止执行", "高风险命令", "连接超时", "runbook", "止损",
            "灰度", "停止条件", "前置条件", "回滚步骤", "恢复后验证", "复盘",
            "主要依赖", "维护团队", "阈值", "证据保全", "安全处置", "数据不一致",
            "验证顺序", "长尾", "p99", "p95", "不能只", "依据现有证据",
        ))
        deployment_facts = any(x in q for x in (
            "最近部署", "最近发布", "部署记录", "发布记录", "部署了什么", "发布了什么", "部署失败了吗", "几次部署"
        ))
        failure_context = any(x in q for x in (
            "失败", "异常", "故障", "原因", "为什么", "排查", "超时", "不一致", "飙升"
        ))
        asks_sop = any(x in q for x in ("sop", "手册", "按照", "怎么排查", "如何排查"))
        live_context = deployment_facts or any(x in q for x in (
            "当前", "最近", "昨天", "刚刚", "刚才", "未解决", "是否有", "有故障吗", "正在发生",
        ))
        github_context = needs_github_evidence(q)

        if greeting or conversation_question:
            return RouteDecisionV2(intent="direct", reason="明确的简单对话", confidence=1.0, service_name=service)
        if github_context:
            return RouteDecisionV2(
                intent="mixed", complexity="complex", risk="low", service_name=service,
                reason="需要关联发布事实与 GitHub 代码/CI 证据", confidence=0.99,
                ops_action="deployments",
            )
        if previous_service and any(x in q for x in ("为什么失败", "为什么", "那按照", "接下来")):
            if asks_sop or "按照" in q:
                return RouteDecisionV2(intent="mixed", complexity="complex", risk="medium", service_name=service,
                                       reason="承接会话中的服务和失败上下文", confidence=0.9, ops_action="deployments")
            return RouteDecisionV2(intent="database", service_name=service, reason="承接会话的事实追问", confidence=0.86,
                                   ops_action="deployments")
        if (deployment_facts or "最近一次" in q) and (procedure or asks_sop):
            return RouteDecisionV2(intent="mixed", complexity="complex", risk="medium", service_name=service,
                                   reason="同时需要实时发布事实和 SOP 证据", confidence=0.99, ops_action="deployments")
        if failure_context and procedure and live_context:
            action = "incidents" if any(x in q for x in ("故障", "incident", "事故")) else "deployments"
            return RouteDecisionV2(intent="mixed", complexity="complex", risk="medium", service_name=service,
                                   reason="故障诊断需要 Ops 与 Knowledge 协同", confidence=0.96, ops_action=action)
        if procedure:
            return RouteDecisionV2(intent="knowledge", service_name=service, reason="流程/文档型知识问题", confidence=0.99)
        if deployment_facts or ("最近" in q and any(x in q for x in ("部署", "发布"))):
            return RouteDecisionV2(intent="database", service_name=service, reason="发布记录事实查询", confidence=0.99,
                                   ops_action="deployments")
        if any(x in q for x in ("当前状态", "现在什么状态", "服务状态", "健康状态", "health")):
            return RouteDecisionV2(intent="database", service_name=service, reason="服务实时状态查询", confidence=0.99,
                                   ops_action="service_status")
        if any(x in q for x in ("未解决故障", "故障列表", "incident", "事故")):
            return RouteDecisionV2(intent="database", service_name=service, reason="故障事实查询", confidence=0.98,
                                   ops_action="incidents")
        if any(x in q for x in ("工单", "ticket")):
            return RouteDecisionV2(intent="database", service_name=service, reason="工单事实查询", confidence=0.98,
                                   ops_action="tickets")
        return None

    async def route(
        self, query: str, previous_service: str | None, gateway, trace_id: str,
        conversation_summary: str = "", recent_messages: list[dict] | None = None,
    ) -> tuple[RouteDecisionV2, list[dict]]:
        fixed = self.deterministic(query, previous_service)
        if fixed:
            return fixed, []
        prompt = (
            "将用户请求分类为 direct/knowledge/database/mixed/diagnosis。只输出 JSON，字段为 "
            "intent,complexity,risk,reason,confidence,ops_action。database 的 ops_action 只能是 "
            "service_status/deployments/incidents/tickets。关于当前对话、用户刚才说过什么或 Agent "
            "会话能力的问题必须分类为 direct，不要分类为 knowledge。结合会话上下文解析指代，"
            "不要输出思考过程。\n"
            f"会话规则：{CONVERSATION_RULES}\n"
            f"会话摘要：{conversation_summary or '无'}\n"
            f"最近消息：{json.dumps((recent_messages or [])[-6:], ensure_ascii=False)}\n"
            "当前用户请求：" + query
        )
        try:
            response = await gateway.call(
                requested_role="LOCAL", agent_name="router", trace_id=trace_id,
                messages=[{"role": "user", "content": prompt}], max_tokens=180,
            )
            match = re.search(r"\{.*\}", response.content, re.S)
            data = json.loads(match.group(0) if match else response.content)
            data["service_name"] = normalize_service(query, previous_service)
            return RouteDecisionV2(**data), [response.record.model_dump()]
        except Exception:
            service = normalize_service(query, previous_service)
            enterprise_hint = service or any(x in query.lower() for x in (
                "部署", "发布", "故障", "工单", "服务", "接口", "sop", "知识库", "文档"
            ))
            intent = "knowledge" if enterprise_hint else "direct"
            return RouteDecisionV2(
                intent=intent,
                reason=f"语义路由不可用，安全降级为 {intent}",
                confidence=0.4,
                service_name=service,
            ), []


semantic_router = SemanticRouter()
