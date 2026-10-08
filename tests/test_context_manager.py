from app.config import Settings
from app.services.context_manager import ConversationContextManager, estimate_tokens


def manager(**overrides):
    values = dict(
        context_max_input_tokens=500,
        context_recent_tokens=120,
        context_summary_tokens=60,
        context_message_tokens=45,
        context_history_message_limit=20,
    )
    values.update(overrides)
    return ConversationContextManager(Settings(_env_file=None, **values))


def test_single_long_message_is_head_tail_truncated():
    prepared = manager().prepare("", [{"role": "user", "content": "开头" + "内容" * 200 + "结尾"}])
    content = prepared.recent_messages[0]["content"]
    assert "开头" in content and "结尾" in content
    assert prepared.stats["truncated_message_count"] >= 1
    assert estimate_tokens(content) <= 45


def test_sliding_window_keeps_newest_and_summarizes_evicted():
    messages = [{"role": "user", "content": f"第{i}条消息 payment-service " + "详情" * 15} for i in range(10)]
    prepared = manager().prepare("", messages)
    assert "第9条消息" in prepared.recent_messages[-1]["content"]
    assert prepared.stats["summarized_message_count"] > 0
    assert "payment-service" in prepared.summary


def test_rolling_summary_has_hard_budget():
    prepared = manager().prepare("旧摘要" * 200, [{"role": "user", "content": "新消息"}])
    assert estimate_tokens(prepared.summary) <= 60


def test_query_reservation_reduces_recent_window_without_dropping_latest():
    messages = [{"role": "user", "content": "history " * 30} for _ in range(5)]
    prepared = manager(context_max_input_tokens=300).prepare("", messages, "问题" * 150)
    assert prepared.recent_messages
    assert prepared.stats["estimated_query_tokens"] >= 150
    assert prepared.stats["estimated_recent_tokens"] <= 120


def test_rolling_summary_does_not_resummarize_same_sequence():
    messages = [
        {"role": "user", "content": f"消息{i} " + "内容" * 20, "_seq": i + 1}
        for i in range(8)
    ]
    first = manager().prepare("", messages)
    second = manager().prepare(
        first.summary, messages, summary_through_seq=first.summary_through_seq
    )
    assert first.stats["summarized_message_count"] > 0
    assert second.stats["summarized_message_count"] == 0
    assert second.summary == first.summary
