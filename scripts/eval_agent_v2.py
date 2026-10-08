"""Run the 30-case V2 regression against a live DevPilot API."""
import argparse
import json
import statistics
import time
from collections import Counter
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "eval" / "agent_v2_cases.jsonl"
REPORT = ROOT / "reports" / "agent_v2_eval.json"


def load_cases():
    return [json.loads(line) for line in DATASET.read_text(encoding="utf-8").splitlines() if line.strip()]


def subset(expected, actual):
    return set(expected).issubset(set(actual))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--timeout", type=float, default=180)
    args = parser.parse_args()
    sessions: dict[str, str] = {}
    rows = []
    with httpx.Client(base_url=args.base_url, timeout=args.timeout, trust_env=False) as client:
        for case in load_cases():
            group = case.get("session_group")
            started = time.perf_counter()
            response = client.post("/api/v1/chat", json={
                "query": case["query"], "user_id": "agent-v2-eval",
                "session_id": sessions.get(group) if group else None,
            })
            latency = int((time.perf_counter() - started) * 1000)
            response.raise_for_status()
            data = response.json()
            if group:
                sessions[group] = data["session_id"]
            requested_roles = [x.get("requested_model_role") for x in data.get("model_info", [])]
            checks = {
                "intent": data.get("intent") == case["expected_intent"],
                "path": data.get("selected_path") == case["expected_path"],
                "agents": data.get("selected_agents") == case["expected_agents"],
                "tools": subset(case.get("expected_tools", []), data.get("tools_used", [])),
                "model_roles": subset(case.get("expected_model_roles", []), requested_roles),
                "answer_nonempty": bool(data.get("answer", "").strip()),
            }
            rows.append({
                "id": case["id"], "category": case["category"], "latency_ms": latency,
                "checks": checks, "passed": all(checks.values()),
                "actual": {
                    "intent": data.get("intent"), "path": data.get("selected_path"),
                    "agents": data.get("selected_agents"), "tools": data.get("tools_used"),
                    "citation_count": len(data.get("citations", [])),
                    "requested_model_roles": requested_roles,
                    "fallback_reasons": [x.get("fallback_reason") for x in data.get("model_info", []) if x.get("fallback")],
                },
            })
    counts = Counter(row["category"] for row in rows)
    passed = Counter(row["category"] for row in rows if row["passed"])
    report = {
        "dataset": str(DATASET), "total": len(rows),
        "passed": sum(row["passed"] for row in rows),
        "pass_rate": round(sum(row["passed"] for row in rows) / max(1, len(rows)), 4),
        "category_pass_rate": {key: round(passed[key] / value, 4) for key, value in counts.items()},
        "latency_ms": {
            "median": int(statistics.median(row["latency_ms"] for row in rows)),
            "max": max(row["latency_ms"] for row in rows),
        },
        "rows": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "passed", "pass_rate", "category_pass_rate", "latency_ms")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
