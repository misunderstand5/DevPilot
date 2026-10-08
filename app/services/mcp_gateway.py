from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import anyio
import httpx

from app.config import Settings, get_settings


ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


class MCPGatewayError(RuntimeError):
    pass


class ExternalMCPGateway:
    """Bounded, read-only gateway for optional external MCP servers.

    Internal DevPilot tools intentionally do not use this network hop.  The
    gateway applies an explicit allowlist, timeout, retry and output bound
    before external evidence reaches an Agent prompt.
    """

    def __init__(self, settings: Settings | None = None, executor: ToolExecutor | None = None):
        self.settings = settings or get_settings()
        self._executor = executor

    @property
    def configured(self) -> bool:
        return bool(self.settings.github_mcp_enabled and self.settings.github_mcp_url)

    def public_status(self) -> dict[str, Any]:
        return {
            "id": "github_mcp",
            "name": "GitHub MCP",
            "configured": self.configured,
            "mode": "read_only",
            "allowed_tools": list(self.settings.github_mcp_tool_allowlist),
            "mapped_services": sorted(self.settings.github_mcp_repositories),
        }

    def repository_for(self, service_name: str | None) -> str | None:
        mapping = self.settings.github_mcp_repositories
        return mapping.get(service_name or "") or mapping.get("*")

    async def _remote_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call the stateless Streamable HTTP transport exposed by GitHub MCP.

        The official server supports stateless requests.  Using the wire
        protocol here also avoids coupling this gateway to one MCP SDK's
        session-initialization implementation.
        """
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "MCP-Protocol-Version": "2025-11-25",
            "X-MCP-Readonly": "true",
            "X-MCP-Tools": ",".join(self.settings.github_mcp_tool_allowlist),
        }
        if self.settings.github_mcp_token and self.settings.github_mcp_token.get_secret_value():
            headers["Authorization"] = f"Bearer {self.settings.github_mcp_token.get_secret_value()}"
        timeout = self.settings.github_mcp_timeout_seconds
        async with httpx.AsyncClient(headers=headers, timeout=timeout, trust_env=False) as client:
            listed = await client.post(self.settings.github_mcp_url, json={
                "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
            })
            tools_result = self._parse_http_message(listed)
            available = {item.get("name") for item in tools_result.get("tools", [])}
            if tool_name not in available:
                raise MCPGatewayError(f"tool_not_exposed:{tool_name}")
            called = await client.post(self.settings.github_mcp_url, json={
                "jsonrpc": "2.0", "id": 2, "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
            })
            result = self._parse_http_message(called)
        if result.get("isError"):
            raise MCPGatewayError(f"tool_returned_error:{tool_name}")
        structured = result.get("structuredContent")
        if structured is not None:
            return structured if isinstance(structured, dict) else {"value": structured}
        texts = [
            item.get("text", "") for item in result.get("content", [])
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        text_value = "\n".join(texts)
        try:
            parsed = json.loads(text_value)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except (TypeError, json.JSONDecodeError):
            return {"text": text_value}

    @staticmethod
    def _parse_http_message(response: httpx.Response) -> dict[str, Any]:
        if response.status_code >= 400:
            raise MCPGatewayError(f"mcp_http_{response.status_code}")
        body = response.text
        if "text/event-stream" in response.headers.get("content-type", ""):
            data_lines = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
            if not data_lines:
                raise MCPGatewayError("mcp_empty_event_stream")
            message = json.loads(data_lines[-1])
        else:
            message = response.json()
        if message.get("error"):
            code = message["error"].get("code", "unknown")
            raise MCPGatewayError(f"mcp_rpc_error:{code}")
        result = message.get("result")
        if not isinstance(result, dict):
            raise MCPGatewayError("mcp_invalid_result")
        return result

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.configured:
            raise MCPGatewayError("github_mcp_not_configured")
        if tool_name not in self.settings.github_mcp_tool_allowlist:
            raise MCPGatewayError(f"tool_not_allowed:{tool_name}")
        executor = self._executor or self._remote_call
        last_error: Exception | None = None
        for attempt in range(max(1, self.settings.github_mcp_max_attempts)):
            try:
                with anyio.fail_after(self.settings.github_mcp_timeout_seconds):
                    return await executor(tool_name, arguments)
            except Exception as exc:  # bounded retry; error text is not exposed to users
                last_error = exc
                if attempt + 1 < self.settings.github_mcp_max_attempts:
                    await anyio.sleep(min(0.2 * (2**attempt), 1.0))
        raise MCPGatewayError(last_error.__class__.__name__ if last_error else "unknown_error")

    def _summary(self, payload: dict[str, Any], commit_sha: str) -> tuple[str, str | None]:
        commit = payload.get("commit") if isinstance(payload.get("commit"), dict) else {}
        message = commit.get("message") or payload.get("message") or "未返回提交说明"
        url = payload.get("html_url") or payload.get("url")
        files = payload.get("files") if isinstance(payload.get("files"), list) else []
        names = [str(item.get("filename")) for item in files[:8] if isinstance(item, dict) and item.get("filename")]
        changed = f"；变更文件：{', '.join(names)}" if names else ""
        return f"提交 {commit_sha[:12]}：{str(message)[:500]}{changed}", str(url) if url else None

    async def collect_github_evidence(
        self, service_name: str | None, commit_sha: str | None
    ) -> dict[str, Any]:
        started = time.perf_counter()
        base = {"source": "github_mcp", "tool": "get_commit"}
        if not self.configured:
            return {**base, "status": "unavailable", "summary": "GitHub MCP 尚未配置"}
        repository = self.repository_for(service_name)
        if not repository or "/" not in repository:
            return {**base, "status": "empty", "summary": "当前服务未配置 GitHub 仓库映射"}
        if not commit_sha:
            return {**base, "status": "empty", "summary": "发布记录中没有可关联的 commit_sha"}
        owner, repo = repository.split("/", 1)
        try:
            payload = await self.call("get_commit", {"owner": owner, "repo": repo, "sha": commit_sha})
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            if len(serialized) > self.settings.github_mcp_max_result_chars:
                payload = {"truncated": True, "excerpt": serialized[: self.settings.github_mcp_max_result_chars]}
            summary, reference = self._summary(payload, commit_sha)
            return {
                **base, "status": "success", "summary": summary, "reference": reference,
                "repository": repository, "commit_sha": commit_sha, "data": payload,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except MCPGatewayError as exc:
            return {
                **base, "status": "error", "summary": "GitHub 证据暂时不可用",
                "error": str(exc), "latency_ms": int((time.perf_counter() - started) * 1000),
            }


external_mcp_gateway = ExternalMCPGateway()
