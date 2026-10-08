import pytest
from fastapi import HTTPException

from app.api import chat as chat_api
from app.schemas import ChatRequest, ChatResponse
from app.security import AuthUser


USER = AuthUser(id="user-1", tenant_id="tenant-1", tenant_slug="devpilot", username="tester", role="MEMBER")


def response_payload():
    return ChatResponse(
        session_id="00000000-0000-0000-0000-000000000001",
        trace_id="00000000-0000-0000-0000-000000000002",
        intent="direct", answer="ok",
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_request_id_returns_previous_result_without_running_agent(monkeypatch):
    async def prior(*_args):
        return response_payload()

    async def must_not_run(_req, _user):
        raise AssertionError("agent should not run for an idempotent replay")

    monkeypatch.setattr(chat_api.redis_store, "get_request_result", prior)
    monkeypatch.setattr(chat_api, "_chat_once", must_not_run)
    result = await chat_api.chat(ChatRequest(
        query="你好", user_id="u",
        request_id="00000000-0000-0000-0000-000000000003",
    ), USER)
    assert result.answer == "ok"


@pytest.mark.asyncio
async def test_session_lock_rejects_concurrent_turn(monkeypatch):
    async def no_prior(*_args):
        return None

    async def locked(*_args):
        return False

    monkeypatch.setattr(chat_api.redis_store, "get_request_result", no_prior)
    monkeypatch.setattr(chat_api.redis_store, "acquire_session_lock", locked)
    with pytest.raises(HTTPException) as exc:
        await chat_api.chat(ChatRequest(
            query="继续", user_id="u",
            session_id="00000000-0000-0000-0000-000000000001",
            request_id="00000000-0000-0000-0000-000000000003",
        ), USER)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_session_lock_is_released_when_agent_fails(monkeypatch):
    released = []

    async def no_prior(*_args):
        return None

    async def acquired(*_args):
        return True

    async def fail(_req, _user):
        raise RuntimeError("boom")

    async def release(session_id, token):
        released.append((session_id, token))

    monkeypatch.setattr(chat_api.redis_store, "get_request_result", no_prior)
    monkeypatch.setattr(chat_api.redis_store, "acquire_session_lock", acquired)
    monkeypatch.setattr(chat_api.redis_store, "release_session_lock", release)
    monkeypatch.setattr(chat_api, "_chat_once", fail)
    with pytest.raises(RuntimeError):
        await chat_api.chat(ChatRequest(
            query="继续", user_id="u",
            session_id="00000000-0000-0000-0000-000000000001",
            request_id="00000000-0000-0000-0000-000000000003",
        ), USER)
    assert released and released[0][0] == "00000000-0000-0000-0000-000000000001"
