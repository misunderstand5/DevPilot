import re
from copy import deepcopy
from typing import Any


SERVICE_ALIASES = {
    "订单服务": "order-service",
    "支付服务": "payment-service",
    "用户服务": "user-service",
    "order-service": "order-service",
    "payment-service": "payment-service",
    "user-service": "user-service",
}
ENVIRONMENT_ALIASES = {
    "生产环境": "prod", "线上环境": "prod", "prod": "prod",
    "测试环境": "test", "test": "test",
    "预发环境": "staging", "staging": "staging",
    "开发环境": "dev", "dev": "dev",
}
FOLLOW_UP_MARKERS = ("它", "这个", "刚才", "之前", "前面", "继续", "第二个", "那个", "呢", "为什么")
OPERATION_MARKERS = ("部署", "发布", "故障", "工单", "排查", "服务", "状态", "回滚", "接口")
_NAME = re.compile(r"(?:我叫|我的名字是)(?!什么)([\w\u3400-\u9fff·]{1,20})")


def empty_memory() -> dict[str, Any]:
    return {
        "version": 1,
        "user_facts": {},
        "entities": {"service": None, "environment": None, "time_range_days": None},
        "active_goal": None,
        "last_user_query": None,
        "updated_turns": 0,
    }


def _service(text: str) -> str | None:
    lowered = text.lower()
    for alias, canonical in sorted(SERVICE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        if alias.lower() in lowered:
            return canonical
    return None


def _environment(text: str) -> str | None:
    lowered = text.lower()
    for alias, canonical in ENVIRONMENT_ALIASES.items():
        if alias.lower() in lowered:
            return canonical
    return None


def _time_range_days(text: str) -> int | None:
    match = re.search(r"最近\s*(\d{1,3})\s*天", text)
    if match:
        return min(365, max(1, int(match.group(1))))
    if "一个月" in text or "近一月" in text:
        return 30
    if "两周" in text:
        return 14
    if "一周" in text or "最近七天" in text or "最近 7 天" in text:
        return 7
    return None


def update_memory(existing: dict[str, Any] | None, messages: list[dict], query: str) -> dict[str, Any]:
    """Deterministically maintain bounded, session-scoped facts without hidden reasoning."""
    memory = deepcopy(existing) if isinstance(existing, dict) and existing else empty_memory()
    memory.setdefault("user_facts", {})
    memory.setdefault("entities", {})
    for key in ("service", "environment", "time_range_days"):
        memory["entities"].setdefault(key, None)

    # Rebuild after Redis expiry by replaying only user-authored text, then apply the current query.
    user_texts = [str(item.get("content", "")) for item in messages if item.get("role") == "user"]
    for text in [*user_texts[-20:], query]:
        if service := _service(text):
            memory["entities"]["service"] = service
        if environment := _environment(text):
            memory["entities"]["environment"] = environment
        if days := _time_range_days(text):
            memory["entities"]["time_range_days"] = days
        if name := _NAME.search(text):
            memory["user_facts"]["name"] = name.group(1).rstrip("，。,.！!？?")

    if any(marker in query for marker in OPERATION_MARKERS):
        memory["active_goal"] = query[:240]
    memory["last_user_query"] = query[:500]
    memory["updated_turns"] = int(memory.get("updated_turns", 0)) + 1
    return memory


def resolve_query(query: str, memory: dict[str, Any]) -> str:
    """Add explicit inherited entities only for elliptical follow-up requests."""
    if not any(marker in query for marker in FOLLOW_UP_MARKERS):
        return query
    inherited = []
    entities = memory.get("entities", {})
    if not _service(query) and entities.get("service"):
        inherited.append(f"service={entities['service']}")
    if not _environment(query) and entities.get("environment"):
        inherited.append(f"environment={entities['environment']}")
    if _time_range_days(query) is None and entities.get("time_range_days"):
        inherited.append(f"time_range_days={entities['time_range_days']}")
    return query if not inherited else f"{query}\n[已解析的会话指代：{', '.join(inherited)}]"


def public_memory(memory: dict[str, Any] | None) -> dict[str, Any]:
    memory = memory or empty_memory()
    return {
        "user_facts": dict(memory.get("user_facts", {})),
        "entities": dict(memory.get("entities", {})),
        "active_goal": memory.get("active_goal"),
        "updated_turns": int(memory.get("updated_turns", 0)),
    }
