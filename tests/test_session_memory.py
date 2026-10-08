from app.services.session_memory import empty_memory, public_memory, resolve_query, update_memory


def test_extracts_structured_session_facts():
    memory = update_memory(
        empty_memory(), [],
        "请记住：我叫阿远，正在检查生产环境 order-service 最近 14 天的部署。",
    )
    assert memory["user_facts"]["name"] == "阿远"
    assert memory["entities"] == {
        "service": "order-service", "environment": "prod", "time_range_days": 14,
    }
    assert "order-service" in memory["active_goal"]


def test_latest_user_correction_wins():
    messages = [
        {"role": "user", "content": "检查 payment-service 测试环境"},
        {"role": "assistant", "content": "好的"},
        {"role": "user", "content": "不对，改成订单服务生产环境"},
    ]
    memory = update_memory({}, messages, "继续")
    assert memory["entities"]["service"] == "order-service"
    assert memory["entities"]["environment"] == "prod"


def test_follow_up_query_gets_explicit_inherited_entities():
    memory = update_memory({}, [], "检查 payment-service 最近 30 天发布")
    resolved = resolve_query("它为什么失败？", memory)
    assert "service=payment-service" in resolved
    assert "time_range_days=30" in resolved


def test_non_follow_up_query_is_not_rewritten():
    memory = update_memory({}, [], "检查 order-service")
    assert resolve_query("你好", memory) == "你好"


def test_public_memory_does_not_expose_internal_last_query():
    memory = update_memory({}, [], "检查 order-service")
    public = public_memory(memory)
    assert "last_user_query" not in public
    assert public["entities"]["service"] == "order-service"
