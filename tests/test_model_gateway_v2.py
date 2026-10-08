from types import SimpleNamespace

import pytest

from app.agent.registry import PrivacyMode
from app.config import Settings
from app.services.model_gateway import ModelGateway, ModelGatewayError


class FakeCompletions:
    def __init__(self, *, content="ok", error=None):
        self.content = content
        self.error = error
        self.calls = 0

    async def create(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1),
        )


def client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def settings(**kwargs):
    base = dict(
        local_model_base_url="http://local/v1", local_model_api_key="x", local_model_name="local",
        strong_model_base_url="https://strong/v1", strong_model_api_key="y", strong_model_name="strong",
        model_max_attempts=1,
    )
    base.update(kwargs)
    return Settings(_env_file=None, **base)


@pytest.mark.asyncio
async def test_private_strong_request_falls_back_to_local():
    gateway = ModelGateway(settings(allow_cloud_internal_data=False))
    local = FakeCompletions(content="local answer")
    strong = FakeCompletions(content="strong answer")
    gateway.local_client, gateway.strong_client = client(local), client(strong)
    response = await gateway.call(
        requested_role="STRONG", agent_name="diagnosis_agent", trace_id="t",
        messages=[{"role": "user", "content": "internal"}], privacy=PrivacyMode.LOCAL_ONLY,
    )
    assert response.content == "local answer"
    assert response.record.requested_model_role == "STRONG"
    assert response.record.served_model_role == "LOCAL"
    assert response.record.fallback_reason == "cloud_internal_data_not_allowed"
    assert strong.calls == 0


@pytest.mark.asyncio
async def test_strong_provider_error_falls_back_once():
    gateway = ModelGateway(settings(allow_cloud_internal_data=True))
    local = FakeCompletions(content="safe fallback")
    strong = FakeCompletions(error=TimeoutError("timeout"))
    gateway.local_client, gateway.strong_client = client(local), client(strong)
    response = await gateway.call(
        requested_role="STRONG", agent_name="supervisor_agent", trace_id="t",
        messages=[{"role": "user", "content": "harmless"}], privacy=PrivacyMode.CLOUD_ALLOWED,
    )
    assert response.content == "safe fallback"
    assert response.record.fallback is True
    assert response.record.fallback_reason == "strong_provider_error:TimeoutError"
    assert local.calls == 1 and strong.calls == 1


@pytest.mark.asyncio
async def test_local_failure_is_bounded_and_explicit():
    gateway = ModelGateway(settings())
    local = FakeCompletions(error=ConnectionError("offline"))
    gateway.local_client = client(local)
    with pytest.raises(ModelGatewayError):
        await gateway.call(
            requested_role="LOCAL", agent_name="knowledge_agent", trace_id="t",
            messages=[{"role": "user", "content": "hello"}],
        )
    assert local.calls == 1
    with pytest.raises(ModelGatewayError, match="circuit open"):
        await gateway.call(
            requested_role="LOCAL", agent_name="knowledge_agent", trace_id="t2",
            messages=[{"role": "user", "content": "hello again"}],
        )
    assert local.calls == 1
