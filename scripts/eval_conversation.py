import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

import httpx


API_URL = os.getenv("DEVPILOT_API_URL", "http://127.0.0.1:8001").rstrip("/")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


async def main():
    engineer_password = os.getenv("DEVPILOT_PASSWORD")
    admin_password = os.getenv("DEVPILOT_ADMIN_PASSWORD")
    if not engineer_password or not admin_password:
        raise RuntimeError("DEVPILOT_PASSWORD and DEVPILOT_ADMIN_PASSWORD are required")
    cases = [json.loads(line) for line in Path("data/eval/conversation_cases.jsonl").read_text(
        encoding="utf-8"
    ).splitlines() if line.strip()]
    rows = []
    async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
        login = await client.post(f"{API_URL}/api/v1/auth/login", json={
            "tenant": os.getenv("DEVPILOT_TENANT", "devpilot"),
            "username": os.getenv("DEVPILOT_USERNAME", "engineer"),
            "password": engineer_password,
        })
        login.raise_for_status()
        client.headers["Authorization"] = "Bearer " + login.json()["access_token"]
        admin_login = await client.post(f"{API_URL}/api/v1/auth/login", json={
            "tenant": os.getenv("DEVPILOT_TENANT", "devpilot"),
            "username": os.getenv("DEVPILOT_ADMIN_USERNAME", "admin"),
            "password": admin_password,
        })
        admin_login.raise_for_status()
        engineer_auth = client.headers["Authorization"]
        admin_auth = "Bearer " + admin_login.json()["access_token"]
        for case in cases:
            session_id = str(uuid.uuid4())
            result = None
            for query in case["turns"]:
                response = await client.post(f"{API_URL}/api/v1/chat", json={
                    "query": query, "session_id": session_id,
                    "request_id": str(uuid.uuid4()),
                })
                response.raise_for_status()
                result = response.json()
            answer = result.get("answer", "")
            restored = await client.get(
                f"{API_URL}/api/v1/sessions/{session_id}", params={"limit": 100}
            )
            client.headers["Authorization"] = admin_auth
            isolated = await client.get(
                f"{API_URL}/api/v1/sessions/{session_id}"
            )
            client.headers["Authorization"] = engineer_auth
            row = {
                "id": case["id"],
                "recall_ok": all(word.lower() in answer.lower() for word in case["answer_keywords"]),
                "restore_ok": restored.status_code == 200 and len(restored.json().get("messages", [])) == 4,
                "isolation_ok": isolated.status_code == 403,
                "answer": answer,
            }
            rows.append(row)
            print(row)
    summary = {
        "cases": len(rows),
        "memory_recall_accuracy": sum(row["recall_ok"] for row in rows) / len(rows),
        "session_restore_accuracy": sum(row["restore_ok"] for row in rows) / len(rows),
        "session_isolation_accuracy": sum(row["isolation_ok"] for row in rows) / len(rows),
    }
    Path("reports").mkdir(exist_ok=True)
    Path("reports/conversation_eval.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(summary)
    if not all(row["recall_ok"] and row["restore_ok"] and row["isolation_ok"] for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
