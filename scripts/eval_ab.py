import asyncio
import json
import os
import statistics
import time
import uuid
from pathlib import Path

import httpx


API_URL = os.getenv("DEVPILOT_API_URL", "http://127.0.0.1:8001").rstrip("/")


async def main():
    password = os.getenv("DEVPILOT_PASSWORD")
    if not password:
        raise RuntimeError("DEVPILOT_PASSWORD is required; evaluation scripts do not embed credentials")
    case_path = Path(os.getenv("DEVPILOT_AB_CASES", "data/eval/hard_agent_cases.jsonl"))
    cases = [json.loads(line) for line in case_path.read_text(
        encoding="utf-8"
    ).splitlines() if line.strip()]
    limit = int(os.getenv("DEVPILOT_AB_LIMIT", "0"))
    if limit:
        cases = cases[:limit]
    rows = []
    async with httpx.AsyncClient(timeout=240, trust_env=False) as client:
        health_response = await client.get(f"{API_URL}/health")
        health_response.raise_for_status()
        environment = health_response.json()
        login = await client.post(f"{API_URL}/api/v1/auth/login", json={
            "tenant": os.getenv("DEVPILOT_TENANT", "devpilot"),
            "username": os.getenv("DEVPILOT_USERNAME", "engineer"),
            "password": password,
        })
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        for case in cases:
            for mode in ("single", "multi"):
                started = time.perf_counter()
                response = await client.post(f"{API_URL}/api/v1/chat", json={
                    "query": case["question"], "session_id": str(uuid.uuid4()),
                    "request_id": str(uuid.uuid4()), "execution_mode": mode, "bypass_cache": True,
                })
                response.raise_for_status()
                data = response.json()
                answer = data.get("answer", "")
                row = {
                    "id": case["id"], "segment": case.get("segment", "unspecified"), "mode": mode,
                    "answer_ok": (
                        all(word.lower() in answer.lower() for word in case.get("required_all", case.get("keywords", [])))
                        and not any(word.lower() in answer.lower() for word in case.get("forbidden", []))
                        and (not case.get("requires_citations") or bool(data.get("citations")))
                    ),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    "model_calls": len(data.get("model_info", [])),
                    "agents": data.get("selected_agents", []),
                    "answer": answer,
                }
                rows.append(row)
                print({key: value for key, value in row.items() if key != "answer"})

    summary = {}
    for mode in ("single", "multi"):
        selected = [row for row in rows if row["mode"] == mode]
        latencies = sorted(row["latency_ms"] for row in selected)
        summary[mode] = {
            "cases": len(selected),
            "answer_accuracy": sum(row["answer_ok"] for row in selected) / len(selected),
            "p50_ms": statistics.median(latencies),
            "p95_ms": latencies[max(0, int(len(latencies) * .95) - 1)],
            "avg_model_calls": sum(row["model_calls"] for row in selected) / len(selected),
        }
    pairs = []
    for case in cases:
        single = next(row for row in rows if row["id"] == case["id"] and row["mode"] == "single")
        multi = next(row for row in rows if row["id"] == case["id"] and row["mode"] == "multi")
        pairs.append({
            "id": case["id"], "segment": case.get("segment", "unspecified"),
            "quality_delta": int(multi["answer_ok"]) - int(single["answer_ok"]),
            "latency_delta_ms": round(multi["latency_ms"] - single["latency_ms"], 1),
        })
    summary["comparison"] = {
        "quality_delta": summary["multi"]["answer_accuracy"] - summary["single"]["answer_accuracy"],
        "p50_latency_delta_ms": summary["multi"]["p50_ms"] - summary["single"]["p50_ms"],
        "multi_benefit_demonstrated": (
            summary["multi"]["answer_accuracy"] > summary["single"]["answer_accuracy"]
        ),
        "verdict": (
            "multi_agent_quality_gain" if summary["multi"]["answer_accuracy"] > summary["single"]["answer_accuracy"]
            else "no_measured_quality_gain"
        ),
    }
    report = {
        "environment": {
            "generation_mode": environment.get("generation_mode"),
            "local_model_online": environment.get("local_model_online"),
            "llm_model": environment.get("llm_model"),
            "note": "Latency and model-call comparisons are not online-model evidence when generation_mode is deterministic_fallback.",
        },
        "summary": summary, "pairs": pairs, "rows": rows,
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/agent_ab_eval.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
