"""Bounded semantic rolling summary with deterministic fallback."""
import json
import re

from app.agent.registry import ModelRole, PrivacyMode
from app.services.context_manager import truncate_to_tokens
from app.services.model_gateway import ModelGatewayError, model_gateway


FIELDS = (
    "confirmed_facts", "user_constraints", "decisions", "rejected_options",
    "open_tasks", "entities", "latest_goal",
)


def _json_object(text: str) -> dict | None:
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.I).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.S)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


async def refine_summary(summary: str, *, trace_id: str, token_budget: int, enabled: bool) -> tuple[str, dict | None]:
    """Convert a bounded fallback summary to stable JSON; never block chat on failure."""
    if not enabled or not summary.strip():
        return summary, None
    prompt = (
        "把下面的较早对话压缩为严格 JSON。只能保留用户明确说过或工具已经确认的信息，"
        "不得推测。冲突时保留最新信息。字段必须是 confirmed_facts、user_constraints、"
        "decisions、rejected_options、open_tasks、entities、latest_goal；前五项为字符串数组，"
        "entities 为对象，latest_goal 为字符串或 null。只输出 JSON。\n\n" + summary
    )
    try:
        response = await model_gateway.call(
            requested_role=ModelRole.LOCAL, agent_name="context_summarizer", trace_id=trace_id,
            messages=[{"role": "system", "content": "你是保守的会话状态压缩器。"},
                      {"role": "user", "content": prompt}],
            privacy=PrivacyMode.LOCAL_ONLY, temperature=0.0, max_tokens=min(700, token_budget),
        )
        parsed = _json_object(response.content)
        if not parsed or any(key not in parsed for key in FIELDS):
            return summary, response.record.model_dump()
        normalized = json.dumps({key: parsed.get(key) for key in FIELDS}, ensure_ascii=False, separators=(",", ":"))
        normalized, _ = truncate_to_tokens(normalized, token_budget)
        return normalized, response.record.model_dump()
    except (ModelGatewayError, Exception):
        return summary, None
