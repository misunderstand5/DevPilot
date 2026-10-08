import time
from typing import Literal

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.agent.registry import ModelRole, PrivacyMode
from app.config import get_settings


class ModelGatewayError(RuntimeError):
    pass


class ModelCallRecord(BaseModel):
    trace_id: str
    agent_name: str
    requested_model_role: str
    served_model_role: str
    model_name: str
    provider: str
    fallback: bool = False
    fallback_reason: str | None = None
    latency_ms: int = 0
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None


class GatewayResponse(BaseModel):
    content: str
    record: ModelCallRecord


class ModelGateway:
    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        timeout = httpx.Timeout(self.settings.model_timeout_seconds)
        self.local_client = AsyncOpenAI(
            base_url=self.settings.resolved_local_model_base_url,
            api_key=self.settings.resolved_local_model_api_key,
            http_client=httpx.AsyncClient(timeout=timeout, trust_env=False),
        )
        self.strong_client = None
        self._circuit_open_until: dict[str, float] = {}
        if self.settings.strong_model_configured:
            self.strong_client = AsyncOpenAI(
                base_url=self.settings.strong_model_base_url,
                api_key=self.settings.strong_model_api_key,
                http_client=httpx.AsyncClient(timeout=timeout, trust_env=False),
            )

    async def call(
        self,
        *,
        requested_role: ModelRole | Literal["LOCAL", "STRONG"] | str,
        agent_name: str,
        trace_id: str,
        messages: list[dict],
        privacy: PrivacyMode = PrivacyMode.LOCAL_ONLY,
        temperature: float = 0.1,
        max_tokens: int = 1000,
    ) -> GatewayResponse:
        role = ModelRole(str(requested_role))
        fallback = False
        fallback_reason = None
        served_role = role
        client = self.local_client
        model = self.settings.resolved_local_model_name
        provider = self.settings.local_model_provider

        if role == ModelRole.STRONG:
            if not self.settings.strong_model_configured:
                fallback, fallback_reason, served_role = True, "strong_model_not_configured", ModelRole.LOCAL
            elif privacy == PrivacyMode.LOCAL_ONLY and not self.settings.allow_cloud_internal_data:
                fallback, fallback_reason, served_role = True, "cloud_internal_data_not_allowed", ModelRole.LOCAL
            else:
                client = self.strong_client
                model = self.settings.strong_model_name
                provider = self.settings.strong_model_provider

        started = time.perf_counter()
        circuit_key = f"{provider}:{model}"
        if self._circuit_open_until.get(circuit_key, 0) > started:
            raise ModelGatewayError(f"{provider} model temporarily unavailable (circuit open)")
        last_error = None
        attempts = max(1, min(self.settings.model_max_attempts, 2))
        for attempt in range(attempts):
            try:
                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                usage = response.usage
                record = ModelCallRecord(
                    trace_id=trace_id, agent_name=agent_name,
                    requested_model_role=role.value, served_model_role=served_role.value,
                    model_name=model, provider=provider, fallback=fallback,
                    fallback_reason=fallback_reason,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    prompt_tokens=getattr(usage, "prompt_tokens", None),
                    completion_tokens=getattr(usage, "completion_tokens", None),
                )
                self._circuit_open_until.pop(circuit_key, None)
                return GatewayResponse(content=response.choices[0].message.content or "", record=record)
            except Exception as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    continue

        # Avoid paying the full network timeout for every specialist when one
        # provider is down.  A later request retries after this short cooldown.
        self._circuit_open_until[circuit_key] = time.perf_counter() + 30.0
        # STRONG provider failures fall back once to LOCAL without recursion.
        if role == ModelRole.STRONG and served_role == ModelRole.STRONG:
            local = await self.call(
                requested_role=ModelRole.LOCAL, agent_name=agent_name, trace_id=trace_id,
                messages=messages, privacy=PrivacyMode.LOCAL_ONLY,
                temperature=temperature, max_tokens=max_tokens,
            )
            local.record.requested_model_role = ModelRole.STRONG.value
            local.record.fallback = True
            local.record.fallback_reason = f"strong_provider_error:{last_error.__class__.__name__}"
            return local
        raise ModelGatewayError(f"{provider} model unavailable: {last_error.__class__.__name__}") from last_error


model_gateway = ModelGateway()
