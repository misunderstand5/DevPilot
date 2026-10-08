import pytest
from app.services.llm import LLMService

@pytest.mark.asyncio
async def test_router_database(monkeypatch):
    monkeypatch.setenv('LLM_MODE','mock')
    svc=LLMService()
    d=await svc.route('现在有哪些未解决故障？')
    assert d.intent in {'database','mixed'}
