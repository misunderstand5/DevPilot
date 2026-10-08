import pytest

from app.config import Settings
from app.services.long_term_memory import LongTermMemoryService, extract_memories


def test_extracts_only_explicit_durable_memories():
    assert extract_memories("我叫小林") == [{"memory_type": "identity", "content": "小林"}]
    assert extract_memories("以后请先给结论，再解释原因。") == [
        {"memory_type": "preference", "content": "先给结论，再解释原因"}
    ]
    assert extract_memories("今天 order-service 怎么了") == []


@pytest.mark.parametrize("text", [
    "我的 api_key 是 abc", "请记住密码 123456", "token=secret", "密钥是 ms-123456"
])
def test_secrets_are_never_promoted_to_memory(text):
    assert extract_memories(text) == []


class _Collections:
    collections = [type("C", (), {"name": "memory"})()]


class FakeQdrant:
    def __init__(self):
        self.filter = None

    def get_collections(self):
        return _Collections()

    def query_points(self, **kwargs):
        self.filter = kwargs["query_filter"]
        point = type("P", (), {"id": "1", "score": .9, "payload": {
            "tenant_id": "t1", "user_id": "u1", "memory_type": "preference", "content": "先给结论"
        }})()
        return type("R", (), {"points": [point]})()


@pytest.mark.asyncio
async def test_recall_always_applies_tenant_and_user_filter(monkeypatch):
    fake = FakeQdrant()
    settings = Settings(_env_file=None, qdrant_memory_collection="memory")
    service = LongTermMemoryService(settings, fake)
    monkeypatch.setattr("app.services.long_term_memory.get_embedding_service", lambda: type("E", (), {
        "embed_query": lambda self, _: type("V", (), {"tolist": lambda self: [0.1, 0.2]})()
    })())
    items = await service.recall("t1", "u1", "如何回答")
    conditions = fake.filter.must
    assert [(c.key, c.match.value) for c in conditions] == [("tenant_id", "t1"), ("user_id", "u1")]
    assert items[0]["content"] == "先给结论"
