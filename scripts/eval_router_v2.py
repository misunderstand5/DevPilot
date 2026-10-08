"""Offline deterministic routing check for the 30-case V2 dataset."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.agent.router import SemanticRouter


def expected_path(decision):
    if decision.intent == "direct":
        return "fast_direct"
    if decision.intent == "knowledge" and decision.complexity == "simple":
        return "fast_knowledge"
    if decision.intent in {"database", "ops_tool"} and decision.complexity == "simple":
        return "fast_ops"
    return "complex"


cases = [json.loads(line) for line in (ROOT / "data/eval/agent_v2_cases.jsonl").read_text(encoding="utf-8").splitlines()]
previous = {}
rows = []
for case in cases:
    group = case.get("session_group")
    decision = SemanticRouter().deterministic(case["query"], previous.get(group))
    actual = {"intent": decision.intent, "path": expected_path(decision), "service": decision.service_name}
    passed = (
        actual["intent"] == case["expected_intent"]
        and actual["path"] == case["expected_path"]
        and actual["service"] == case.get("expected_service")
    )
    rows.append({"id": case["id"], "passed": passed, "actual": actual})
    if group:
        previous[group] = decision.service_name
report = {"total": len(rows), "passed": sum(x["passed"] for x in rows), "rows": rows}
report["pass_rate"] = report["passed"] / report["total"]
target = ROOT / "reports/agent_v2_router_eval.json"
target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({key: report[key] for key in ("total", "passed", "pass_rate")}, ensure_ascii=False))
