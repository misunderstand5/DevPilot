import pytest
import httpx

from app.config import Settings
from app.services.mcp_gateway import ExternalMCPGateway, MCPGatewayError
from app.agent.specialists import ops_agent


def settings(**overrides):
    values = {
        "github_mcp_enabled": True,
        "github_mcp_url": "https://mcp.example.test/mcp",
        "github_mcp_token": "test-only-token",
        "github_mcp_tool_allowlist": ["get_commit"],
        "github_mcp_repositories": {"order-service": "acme/order-service"},
        "github_mcp_timeout_seconds": 1,
        "github_mcp_max_attempts": 1,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.asyncio
async def test_gateway_rejects_tools_outside_read_only_allowlist():
    gateway = ExternalMCPGateway(settings())
    with pytest.raises(MCPGatewayError, match="tool_not_allowed"):
        await gateway.call("create_issue", {"title": "must never run"})


@pytest.mark.asyncio
async def test_gateway_collects_normalized_commit_evidence():
    captured = {}

    async def fake_executor(name, arguments):
        captured.update({"name": name, "arguments": arguments})
        return {
            "sha": "abc123",
            "html_url": "https://github.example/acme/order-service/commit/abc123",
            "commit": {"message": "fix connection pool timeout"},
            "files": [{"filename": "app/db.py"}, {"filename": "tests/test_db.py"}],
        }

    gateway = ExternalMCPGateway(settings(), executor=fake_executor)
    evidence = await gateway.collect_github_evidence("order-service", "abc123")

    assert evidence["status"] == "success"
    assert evidence["source"] == "github_mcp"
    assert "connection pool timeout" in evidence["summary"]
    assert captured == {
        "name": "get_commit",
        "arguments": {"owner": "acme", "repo": "order-service", "sha": "abc123"},
    }


@pytest.mark.asyncio
async def test_gateway_degrades_when_disabled():
    gateway = ExternalMCPGateway(settings(github_mcp_enabled=False))
    evidence = await gateway.collect_github_evidence("order-service", "abc123")
    assert evidence["status"] == "unavailable"
    assert "data" not in evidence


def test_public_status_never_exposes_token_or_endpoint():
    configured = settings()
    status = ExternalMCPGateway(configured).public_status()
    assert status["configured"] is True
    assert "token" not in status
    assert "url" not in status
    assert "test-only-token" not in repr(configured)


def test_streamable_http_sse_response_is_parsed():
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"tools":[{"name":"get_commit"}]}}\n\n',
    )
    assert ExternalMCPGateway._parse_http_message(response)["tools"][0]["name"] == "get_commit"


def test_streamable_http_error_is_bounded():
    response = httpx.Response(401, text="token details must not be propagated")
    with pytest.raises(MCPGatewayError, match="mcp_http_401"):
        ExternalMCPGateway._parse_http_message(response)


@pytest.mark.asyncio
async def test_ops_agent_joins_internal_deployment_with_external_mcp(monkeypatch):
    async def fake_deployments(service_name, days):
        return [{"service_name": service_name, "commit_sha": "abc123", "status": "FAILED"}]

    async def fake_evidence(service_name, commit_sha):
        return {
            "source": "github_mcp", "tool": "get_commit", "status": "success",
            "summary": "提交 abc123：fix timeout", "reference": "https://github.example/commit/abc123",
        }

    monkeypatch.setattr("app.agent.specialists.recent_deployments", fake_deployments)
    monkeypatch.setattr(
        "app.agent.specialists.external_mcp_gateway.collect_github_evidence", fake_evidence
    )
    result = await ops_agent({
        "query": "这次 commit 改了什么", "trace_id": "trace", "current_service": "order-service",
        "ops_action": "deployments", "needs_github_evidence": True, "session_memory": {},
        "agent_results": {}, "model_calls": [], "tools_used": [], "external_evidence": [],
    }, synthesize=False)

    assert "recent_deployments" in result["tools_used"]
    assert "mcp.github.get_commit" in result["tools_used"]
    assert result["external_evidence"][0]["status"] == "success"
    assert result["tool_results"][-1]["github_mcp"]["source"] == "github_mcp"


@pytest.mark.asyncio
async def test_ops_agent_selects_commit_for_requested_version(monkeypatch):
    async def fake_deployments(service_name, days):
        return [
            {"service_name": service_name, "version": "v2.0.0", "commit_sha": "newest"},
            {"service_name": service_name, "version": "v0.10.7", "commit_sha": "5b608cb"},
        ]

    captured = {}

    async def fake_evidence(service_name, commit_sha):
        captured["commit_sha"] = commit_sha
        return {"source": "github_mcp", "tool": "get_commit", "status": "success"}

    monkeypatch.setattr("app.agent.specialists.recent_deployments", fake_deployments)
    monkeypatch.setattr(
        "app.agent.specialists.external_mcp_gateway.collect_github_evidence", fake_evidence
    )
    await ops_agent({
        "query": "v0.10.7 这个 commit 改了什么", "trace_id": "trace",
        "current_service": "order-service", "ops_action": "deployments",
        "needs_github_evidence": True, "session_memory": {}, "agent_results": {},
        "model_calls": [], "tools_used": [], "external_evidence": [],
    }, synthesize=False)
    assert captured["commit_sha"] == "5b608cb"
