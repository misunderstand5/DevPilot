"""Authenticated end-to-end check for the live Online Boutique case."""
import asyncio
import json
import os

import httpx

import _bootstrap  # noqa: F401
from app.config import get_settings


async def main() -> int:
    settings = get_settings()
    password = settings.auth_engineer_password
    if not password:
        print(json.dumps({"passed": False, "error": "AUTH_ENGINEER_PASSWORD is not configured"}))
        return 2
    base_url = os.getenv("DEVPILOT_API_URL", "http://127.0.0.1:8001").rstrip("/")
    async with httpx.AsyncClient(base_url=base_url, timeout=180, trust_env=False) as client:
        login = await client.post("/api/v1/auth/login", json={
            "tenant": settings.auth_default_tenant,
            "username": "engineer",
            "password": password,
        })
        login.raise_for_status()
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        response = await client.post("/api/v1/chat", headers=headers, json={
            "query": "Online Boutique 的 order-service 对应哪个真实服务，它依赖哪些下游？",
            "user_id": "ignored-by-auth",
            "bypass_cache": True,
        })
        response.raise_for_status()
        data = response.json()
        mcp_response = await client.post("/api/v1/chat", headers=headers, json={
            "query": "查询 order-service 最近30天发布，并说明 v0.10.7 这个 commit 改了什么",
            "user_id": "ignored-by-auth",
            "bypass_cache": True,
        })
        mcp_response.raise_for_status()
        mcp_data = mcp_response.json()
    quality = data.get("evidence_quality", {})
    report = {
        "http_status": response.status_code,
        "intent": data.get("intent"),
        "selected_path": data.get("selected_path"),
        "citation_titles": [item.get("title") for item in data.get("citations", [])],
        "evidence_quality": quality,
        "answer_excerpt": data.get("answer", "")[:300],
        "mcp_case": {
            "intent": mcp_data.get("intent"),
            "tools_used": mcp_data.get("tools_used", []),
            "external_evidence": mcp_data.get("external_evidence", []),
            "evidence_quality": mcp_data.get("evidence_quality", {}),
        },
    }
    report["passed"] = bool(
        data.get("intent") == "knowledge"
        and data.get("citations")
        and quality.get("status") == "passed"
        and any(item.get("status") == "success" for item in mcp_data.get("external_evidence", []))
        and "mcp.github.get_commit" in mcp_data.get("tools_used", [])
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
