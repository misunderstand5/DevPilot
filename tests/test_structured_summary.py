import pytest

from app.services import structured_summary


class Record:
    def model_dump(self):
        return {"agent_name": "context_summarizer"}


class Response:
    content = '{"confirmed_facts":["已确认发布失败"],"user_constraints":["不得重启全部实例"],"decisions":[],"rejected_options":["全量重启"],"open_tasks":["检查 trace"],"entities":{"service":"order-service"},"latest_goal":"定位失败原因"}'
    record = Record()


@pytest.mark.asyncio
async def test_semantic_summary_is_validated_and_bounded(monkeypatch):
    async def call(**_kwargs):
        return Response()

    monkeypatch.setattr(structured_summary.model_gateway, "call", call)
    summary, record = await structured_summary.refine_summary(
        "旧对话", trace_id="trace", token_budget=200, enabled=True
    )
    assert "confirmed_facts" in summary
    assert "order-service" in summary
    assert record["agent_name"] == "context_summarizer"


@pytest.mark.asyncio
async def test_invalid_model_summary_falls_back_without_data_loss(monkeypatch):
    async def call(**_kwargs):
        response = Response()
        response.content = "not-json"
        return response

    monkeypatch.setattr(structured_summary.model_gateway, "call", call)
    summary, _ = await structured_summary.refine_summary(
        "可靠的规则摘要", trace_id="trace", token_budget=200, enabled=True
    )
    assert summary == "可靠的规则摘要"
