import json
import re
from openai import AsyncOpenAI
from app.config import get_settings
from app.schemas import RouterDecision
import httpx


class LLMUnavailableError(RuntimeError):
    """Raised when the optional local inference endpoint cannot be reached."""

class LLMService:
    def __init__(self):
        self.settings = get_settings()
        import httpx
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            base_url=self.settings.llm_base_url,
            api_key=self.settings.llm_api_key,
            http_client=httpx.AsyncClient(trust_env=False),
        )

    @property
    def is_mock(self) -> bool:
        return self.settings.llm_mode.lower() == "mock"

    async def chat(self, messages: list[dict], temperature: float = 0.2, max_tokens: int = 800) -> str:
        if self.is_mock:
            raise LLMUnavailableError("LLM_MODE=mock")
        try:
            r = await self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return r.choices[0].message.content or ""
        except Exception as exc:
            # Keep the RAG/database workflow usable while the optional local
            # vLLM process is restarting or unavailable.
            if isinstance(exc, (httpx.HTTPError, ConnectionError)) or exc.__class__.__module__.startswith("openai"):
                raise LLMUnavailableError("local LLM endpoint unavailable") from exc
            raise

    def _keyword_route(self, query: str) -> RouterDecision:
        q = query.lower()
        has_doc = any(k in q for k in ["文档", "手册", "sop", "规范", "接口", "api", "错误码", "怎么部署", "部署流程", "排查步骤"])
        has_db = any(k in q for k in ["最近", "几次", "记录", "失败了", "未解决", "故障", "工单", "状态", "incident", "ticket", "deployment"])
        service = None
        for s in ["order-service", "user-service", "payment-service"]:
            if s in q:
                service = s
                break
        if has_doc and has_db:
            return RouterDecision(intent="mixed", reason="keyword mixed route", service_name=service)
        if has_db:
            return RouterDecision(intent="database", reason="keyword database route", service_name=service)
        if has_doc:
            return RouterDecision(intent="knowledge", reason="keyword knowledge route", service_name=service)
        return RouterDecision(intent="direct", reason="keyword direct route", service_name=service)

    async def route(self, query: str) -> RouterDecision:
        # The supported enterprise intents have explicit vocabulary. Prefer the
        # deterministic route for those queries so a small local model cannot
        # turn an SOP question into an unrelated database lookup.
        keyword_decision = self._keyword_route(query)
        if self.is_mock or keyword_decision.intent != "direct":
            return keyword_decision
        prompt = f"""
你是企业研发 Agent 的意图路由器。只输出 JSON，不要输出 Markdown。
intent 只能是：
- knowledge：文档、SOP、API、架构、规范类知识问题
- database：部署次数、工单、服务状态、故障记录等结构化查询
- ops_tool：明确要求调用业务工具
- mixed：同时需要知识文档和结构化业务数据
- direct：普通聊天，不需要企业数据

返回：
{{"intent":"...","reason":"...","service_name":null或服务名}}

用户问题：{query}
"""
        try:
            text = await self.chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=120)
            m = re.search(r"\{.*\}", text, re.S)
            data = json.loads(m.group(0) if m else text)
            return RouterDecision(**data)
        except Exception:
            return self._keyword_route(query)


llm_service = LLMService()
