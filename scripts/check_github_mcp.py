"""Sanitized connectivity check for the local read-only GitHub MCP server."""
import asyncio
import json
import httpx

import _bootstrap  # noqa: F401
from app.services.mcp_gateway import external_mcp_gateway


async def main() -> int:
    token_value = external_mcp_gateway.settings.github_mcp_token
    secret_value = token_value.get_secret_value() if token_value else ""
    async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
        identity_response = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {secret_value}", "Accept": "application/vnd.github+json"},
        )
    identity = identity_response.json() if identity_response.headers.get("content-type", "").startswith("application/json") else {}
    evidence = await external_mcp_gateway.collect_github_evidence(
        "order-service", "5b608cb"
    )
    report = {
        "configured": external_mcp_gateway.configured,
        "github_auth_status": identity_response.status_code,
        "github_login": identity.get("login"),
        "status": evidence.get("status"),
        "tool": evidence.get("tool"),
        "repository": evidence.get("repository"),
        "commit_sha": evidence.get("commit_sha"),
        "summary": evidence.get("summary"),
        "reference": evidence.get("reference"),
        "latency_ms": evidence.get("latency_ms"),
        "error": evidence.get("error"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if evidence.get("status") != "success":
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            probe = await client.post(
                external_mcp_gateway.settings.github_mcp_url,
                headers={
                    "Authorization": f"Bearer {secret_value}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-11-25",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-11-25", "capabilities": {},
                    "clientInfo": {"name": "devpilot-diagnostic", "version": "1"},
                }},
            )
        print(json.dumps({
            "http_probe_status": probe.status_code,
            "http_probe_body": probe.text.replace(secret_value, "[REDACTED]")[:1000],
        }, ensure_ascii=False, indent=2))
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            raw_list = await client.post(
                external_mcp_gateway.settings.github_mcp_url,
                headers={
                    "Authorization": f"Bearer {secret_value}",
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-11-25",
                },
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            )
        print(json.dumps({"raw_list_status": raw_list.status_code,
                          "raw_list_body": raw_list.text[:1000]}, ensure_ascii=False, indent=2))
        try:
            import httpx2
            from mcp import ClientSession
            from mcp.client.streamable_http import streamable_http_client
            async with httpx2.AsyncClient(
                headers={"Authorization": f"Bearer {secret_value}"}, timeout=15
            ) as diagnostic_client:
                async with streamable_http_client(
                    external_mcp_gateway.settings.github_mcp_url, http_client=diagnostic_client
                ) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        print(json.dumps({"mcp_stage": "initialize"}))
                        await session.initialize()
                        print(json.dumps({"mcp_stage": "list_tools"}))
                        listed = await session.list_tools()
                        print(json.dumps({"mcp_tools": [tool.name for tool in listed.tools]}))
        except BaseException as exc:
            token = external_mcp_gateway.settings.github_mcp_token
            secret = token.get_secret_value() if token else ""
            messages = []
            pending = [exc]
            while pending:
                current = pending.pop()
                nested = getattr(current, "exceptions", None)
                if nested:
                    pending.extend(nested)
                else:
                    message = str(current).replace(secret, "[REDACTED]") if secret else str(current)
                    messages.append({"type": current.__class__.__name__, "message": message[:500]})
            print(json.dumps({"diagnostics": messages}, ensure_ascii=False, indent=2))
    return 0 if evidence.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
