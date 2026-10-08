from __future__ import annotations

from typing import Any


def assess_evidence(result: dict[str, Any]) -> dict[str, Any]:
    """Deterministic quality gate for the evidence contract of each route."""
    intent = result.get("intent", "unknown")
    citations = result.get("citations", [])
    tools = result.get("tools_used", [])
    external = result.get("external_evidence", [])
    successful_external = [item for item in external if item.get("status") == "success"]
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    if intent in {"knowledge", "mixed", "diagnosis"}:
        add("knowledge_citation", bool(citations), "知识型结论需要至少一个可追踪文档引用")
    if intent in {"database", "ops_tool", "mixed", "diagnosis"}:
        internal_tools = [name for name in tools if not name.startswith("mcp.")]
        add("operational_fact", bool(internal_tools), "运行事实必须来自参数化只读工具")
    if result.get("needs_github_evidence"):
        add("code_provenance", bool(successful_external), "代码归因问题需要成功的外部代码证据")
    add("answer_present", bool(str(result.get("final_answer", "")).strip()), "回答不能为空")

    passed_count = sum(item["passed"] for item in checks)
    return {
        "status": "passed" if passed_count == len(checks) else "insufficient",
        "score": round(passed_count / max(1, len(checks)), 3),
        "checks": checks,
        "citation_count": len(citations),
        "tool_count": len(tools),
        "external_evidence_count": len(successful_external),
    }
