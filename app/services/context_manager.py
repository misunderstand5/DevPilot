import hashlib
import re
from dataclasses import dataclass
from typing import Any

from app.config import get_settings


_CJK = re.compile(r"[\u3400-\u9fff]")
_SERVICE = re.compile(r"(?:order|payment|user)-service|订单服务|支付服务|用户服务", re.I)


def estimate_tokens(text: str) -> int:
    """Conservative tokenizer-free estimate suitable for mixed Chinese/English."""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    non_cjk = len(text) - cjk
    return cjk + max(1, (non_cjk + 3) // 4)


def truncate_to_tokens(text: str, budget: int) -> tuple[str, bool]:
    if estimate_tokens(text) <= budget:
        return text, False
    if budget <= 8:
        return text[: max(1, budget)], True
    # Preserve both the instruction/question prefix and recent details at the end.
    char_budget = max(16, budget * 2)
    head = int(char_budget * 0.7)
    tail = char_budget - head
    candidate = text[:head].rstrip() + "\n…[内容已按上下文预算截断]…\n" + text[-tail:].lstrip()
    while estimate_tokens(candidate) > budget and head > 8 and tail > 4:
        head = int(head * 0.9)
        tail = int(tail * 0.9)
        candidate = text[:head].rstrip() + "\n…[已截断]…\n" + text[-tail:].lstrip()
    return candidate, True


@dataclass
class PreparedContext:
    summary: str
    recent_messages: list[dict[str, Any]]
    stats: dict[str, Any]
    summary_through_seq: int = 0


class ConversationContextManager:
    """Sliding window + deterministic rolling summary with hard token budgets."""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()

    def prepare(
        self,
        existing_summary: str,
        messages: list[dict],
        current_query: str = "",
        summary_through_seq: int = 0,
    ) -> PreparedContext:
        normalized: list[dict[str, Any]] = []
        truncated = 0
        visible_messages = messages[-self.settings.context_history_message_limit:]
        for index, message in enumerate(visible_messages, 1):
            content, was_truncated = truncate_to_tokens(
                str(message.get("content", "")), self.settings.context_message_tokens
            )
            truncated += int(was_truncated)
            normalized.append({
                "role": str(message.get("role", "user")), "content": content,
                "_seq": int(message.get("_seq", index)),
            })

        query_tokens = estimate_tokens(current_query)
        window_budget = min(
            self.settings.context_recent_tokens,
            max(256, self.settings.context_max_input_tokens - query_tokens - self.settings.context_summary_tokens - 800),
        )
        selected_reversed: list[dict[str, str]] = []
        used = 0
        for message in reversed(normalized):
            cost = estimate_tokens(message["content"]) + 6
            if selected_reversed and used + cost > window_budget:
                break
            if not selected_reversed and cost > window_budget:
                content, _ = truncate_to_tokens(message["content"], max(64, window_budget - 6))
                message = {**message, "content": content}
                cost = estimate_tokens(content) + 6
                truncated += 1
            selected_reversed.append(message)
            used += cost
        recent = list(reversed(selected_reversed))
        evicted = normalized[: len(normalized) - len(recent)]
        newly_evicted = [message for message in evicted if message["_seq"] > summary_through_seq]
        summary = self._compress(existing_summary, newly_evicted)
        next_summary_seq = max([summary_through_seq] + [message["_seq"] for message in newly_evicted])
        summary_tokens = estimate_tokens(summary)
        fingerprint = hashlib.sha256(
            (summary + "|" + "|".join(x["content"] for x in recent[-4:])).encode("utf-8")
        ).hexdigest()[:16]
        return PreparedContext(summary=summary, recent_messages=recent, stats={
            "max_input_tokens": self.settings.context_max_input_tokens,
            "estimated_query_tokens": query_tokens,
            "estimated_summary_tokens": summary_tokens,
            "estimated_recent_tokens": used,
            "window_message_count": len(recent),
            "summarized_message_count": len(newly_evicted),
            "truncated_message_count": truncated,
            "context_fingerprint": fingerprint,
        }, summary_through_seq=next_summary_seq)

    def _compress(self, existing: str, evicted: list[dict[str, str]]) -> str:
        if not evicted:
            summary, _ = truncate_to_tokens(existing, self.settings.context_summary_tokens)
            return summary
        services: list[str] = []
        facts: list[str] = []
        for message in evicted[-16:]:
            for service in _SERVICE.findall(message["content"]):
                canonical = {"订单服务": "order-service", "支付服务": "payment-service", "用户服务": "user-service"}.get(
                    service, service.lower()
                )
                if canonical not in services:
                    services.append(canonical)
            compact = " ".join(message["content"].split())
            compact, _ = truncate_to_tokens(compact, 90)
            if compact:
                facts.append(f"- {message['role']}: {compact}")
        blocks = []
        if existing:
            blocks.append(existing)
        if services:
            blocks.append("涉及服务：" + "、".join(services))
        if facts:
            blocks.append("较早对话摘要：\n" + "\n".join(facts[-8:]))
        merged = "\n".join(blocks)
        merged, _ = truncate_to_tokens(merged, self.settings.context_summary_tokens)
        return merged


context_manager = ConversationContextManager()
