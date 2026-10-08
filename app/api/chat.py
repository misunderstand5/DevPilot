import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.agent.graph import agent_graph
from app.agent.router import is_conversation_query
from app.db import session_scope
from app.redis_store import redis_store
from app.schemas import ChatRequest, ChatResponse, ExternalEvidence
from app.services.evidence_quality import assess_evidence
from app.services.context_manager import context_manager
from app.services.session_memory import public_memory, resolve_query, update_memory
from app.services.long_term_memory import long_term_memory
from app.services.structured_summary import refine_summary
from app.security import AuthUser, current_user, require_permission

router = APIRouter(prefix="/api/v1", tags=["chat"])


def _context_stats_for_response(prepared, post_context) -> dict:
    stats = dict(post_context.stats)
    stats["estimated_query_tokens"] = prepared.stats["estimated_query_tokens"]
    stats["summarized_message_count"] += prepared.stats["summarized_message_count"]
    stats["truncated_message_count"] = max(
        stats["truncated_message_count"], prepared.stats["truncated_message_count"]
    )
    return stats


async def _load_owned_history(session_id: str, user_id: str) -> tuple[bool, list[dict]]:
    """Enforce logical ownership and recover history from MySQL after Redis TTL."""
    async with session_scope() as db:
        owner = await db.execute(text("SELECT user_id FROM agent_session WHERE id=:s"), {"s": session_id})
        row = owner.first()
        if row and row.user_id != user_id:
            raise HTTPException(status_code=403, detail="session belongs to another user")
        exists = bool(row)
        messages = await redis_store.recent_messages(session_id, limit=context_manager.settings.context_history_message_limit)
        if not messages and exists:
            result = await db.execute(text("""
                SELECT role,content FROM (
                  SELECT id,role,content FROM agent_message WHERE session_id=:s
                  ORDER BY id DESC LIMIT :n
                ) recent ORDER BY id
            """), {"s": session_id, "n": context_manager.settings.context_history_message_limit})
            messages = [dict(item._mapping) for item in result]
        return exists, messages


async def _load_snapshot(session_id: str, user_id: str) -> dict:
    """Redis is the hot cache; MySQL is the durable session-state source."""
    cached = await redis_store.get_conversation_state(session_id)
    if cached:
        return cached
    async with session_scope() as db:
        result = await db.execute(text("""
            SELECT summary,summary_through_seq,memory_json,context_json
            FROM agent_session_snapshot WHERE session_id=:s AND user_id=:u
        """), {"s": session_id, "u": user_id})
        row = result.first()
        if not row:
            return {}
        state = dict(row.context_json or {})
        state.update({
            "summary": row.summary or "",
            "summary_through_seq": int(row.summary_through_seq or 0),
            "memory": dict(row.memory_json or {}),
        })
        await redis_store.set_conversation_state(session_id, state)
        return state


async def _save_snapshot(session_id: str, user_id: str, state: dict) -> None:
    await redis_store.set_conversation_state(session_id, state)
    context = {key: value for key, value in state.items() if key not in {"summary", "summary_through_seq", "memory"}}
    async with session_scope() as db:
        await db.execute(text("""
            INSERT INTO agent_session_snapshot(session_id,user_id,summary,summary_through_seq,memory_json,context_json)
            VALUES(:s,:u,:summary,:seq,:memory,:context)
            ON DUPLICATE KEY UPDATE summary=VALUES(summary),summary_through_seq=VALUES(summary_through_seq),
              memory_json=VALUES(memory_json),context_json=VALUES(context_json),version=version+1
        """), {
            "s": session_id, "u": user_id, "summary": state.get("summary", ""),
            "seq": int(state.get("summary_through_seq", 0)),
            "memory": json.dumps(state.get("memory", {}), ensure_ascii=False),
            "context": json.dumps(context, ensure_ascii=False, default=str),
        })


async def _persist(session_id: str, user_id: str, trace_id: str, query: str, result: dict, elapsed_ms: int):
    async with session_scope() as db:
        await db.execute(text("""
            CREATE TABLE IF NOT EXISTS model_call_log (
              id BIGINT PRIMARY KEY AUTO_INCREMENT,
              session_id CHAR(36), trace_id CHAR(36) NOT NULL,
              agent_name VARCHAR(100) NOT NULL,
              requested_model_role VARCHAR(20) NOT NULL,
              served_model_role VARCHAR(20) NOT NULL,
              model_name VARCHAR(255) NOT NULL, provider VARCHAR(100) NOT NULL,
              fallback BOOLEAN NOT NULL DEFAULT FALSE,
              fallback_reason VARCHAR(255), latency_ms INT,
              prompt_tokens INT, completion_tokens INT, error VARCHAR(500),
              created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
              INDEX idx_model_trace(trace_id), INDEX idx_model_agent_time(agent_name,created_at)
            ) ENGINE=InnoDB
        """))
        await db.execute(text("""
            INSERT INTO agent_session(id,user_id,title,last_active_at)
            VALUES(:id,:u,:t,NOW())
            ON DUPLICATE KEY UPDATE last_active_at=NOW()
        """), {"id": session_id, "u": user_id, "t": query[:120]})
        await db.execute(text("""
            INSERT INTO agent_message(session_id,role,content,trace_id)
            VALUES(:s,'user',:c,:t),(:s,'assistant',:a,:t)
        """), {"s": session_id, "c": query, "a": result.get("final_answer", ""), "t": trace_id})

        tool_results = result.get("tool_results", [])
        for i, tool_name in enumerate(result.get("tools_used", [])):
            if tool_name == "rag_search":
                payload = {"citations": result.get("citations", [])}
            else:
                payload = tool_results[i - 1] if i > 0 and i - 1 < len(tool_results) else tool_results
            await db.execute(text("""
                INSERT INTO tool_call_log(session_id,trace_id,tool_name,args_json,result_json,status,latency_ms)
                VALUES(:s,:t,:n,:a,:r,'SUCCESS',:ms)
            """), {
                "s": session_id,
                "t": trace_id,
                "n": tool_name,
                "a": json.dumps({"query": query}, ensure_ascii=False),
                "r": json.dumps(payload, ensure_ascii=False, default=str),
                "ms": elapsed_ms,
            })
        for call in result.get("model_calls", []):
            await db.execute(text("""
                INSERT INTO model_call_log(
                  session_id,trace_id,agent_name,requested_model_role,served_model_role,
                  model_name,provider,fallback,fallback_reason,latency_ms,
                  prompt_tokens,completion_tokens,error
                ) VALUES(:s,:t,:a,:rr,:sr,:m,:p,:f,:fr,:ms,:pt,:ct,:e)
            """), {
                "s": session_id, "t": trace_id, "a": call.get("agent_name", "unknown"),
                "rr": call.get("requested_model_role", "LOCAL"),
                "sr": call.get("served_model_role", "LOCAL"),
                "m": call.get("model_name", "unknown"), "p": call.get("provider", "unknown"),
                "f": bool(call.get("fallback")), "fr": call.get("fallback_reason"),
                "ms": call.get("latency_ms"), "pt": call.get("prompt_tokens"),
                "ct": call.get("completion_tokens"), "e": call.get("error"),
            })


async def _chat_once(req: ChatRequest, auth_user: AuthUser):
    if not await redis_store.allowed(req.user_id):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    session_id = req.session_id or str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    _, raw_messages = await _load_owned_history(session_id, req.user_id)
    conversation = await _load_snapshot(session_id, req.user_id)
    prepared = context_manager.prepare(
        conversation.get("summary", ""), raw_messages, req.query,
        summary_through_seq=int(conversation.get("summary_through_seq", 0)),
    )
    if prepared.stats["summarized_message_count"]:
        prepared.summary, _ = await refine_summary(
            prepared.summary, trace_id=trace_id,
            token_budget=context_manager.settings.context_summary_tokens,
            enabled=context_manager.settings.context_llm_summary_enabled,
        )
    recent_messages = [{"role": item["role"], "content": item["content"]} for item in prepared.recent_messages]
    memory = update_memory(conversation.get("memory"), raw_messages, req.query)
    recalled_memories = await long_term_memory.recall(auth_user.tenant_id, auth_user.id, req.query)
    resolved_query = resolve_query(req.query, memory)
    current_service = memory.get("entities", {}).get("service") or conversation.get("current_service")
    # Cached answers can contain ACL-protected RAG evidence.  User identity is
    # therefore part of the key; never reuse a privileged answer for another
    # member, even inside the same tenant.
    context_key = (
        f"{auth_user.tenant_id}|{auth_user.id}|{req.execution_mode}|"
        f"{current_service or ''}|{conversation.get('current_topic', '')}"
    )

    cacheable = not req.bypass_cache and not recent_messages and not is_conversation_query(req.query)
    cached = await redis_store.get_cached_answer(req.query, context_key=context_key) if cacheable else None
    if cached:
        public = {key: value for key, value in cached.items() if not key.startswith("_")}
        public["memory"] = public_memory(memory)
        user_message = await redis_store.append_session_message(session_id, {"role": "user", "content": req.query})
        assistant_message = await redis_store.append_session_message(
            session_id, {"role": "assistant", "content": public["answer"]}
        )
        post_context = context_manager.prepare(
            prepared.summary,
            prepared.recent_messages + [user_message, assistant_message],
            summary_through_seq=prepared.summary_through_seq,
        )
        response_context_stats = _context_stats_for_response(prepared, post_context)
        public["context_info"] = response_context_stats
        snapshot = {
            "current_service": cached.get("_current_service"),
            "current_topic": cached.get("_current_topic"),
            "summary": post_context.summary,
            "context_fingerprint": post_context.stats["context_fingerprint"],
            "context_stats": response_context_stats,
            "summary_through_seq": post_context.summary_through_seq,
            "memory": memory,
        }
        await _persist(session_id, req.user_id, trace_id, req.query, {
            "final_answer": public["answer"], "tools_used": public.get("tools_used", []),
            "citations": public.get("citations", []), "model_calls": [], "tool_results": [],
        }, 0)
        await _save_snapshot(session_id, req.user_id, snapshot)
        await long_term_memory.remember(auth_user.tenant_id, auth_user.id, session_id, req.query)
        return ChatResponse(session_id=session_id, trace_id=trace_id, cached=True, **public)

    t0 = time.perf_counter()
    result = await agent_graph.ainvoke({
        "session_id": session_id,
        "user_id": auth_user.id,
        "tenant_id": auth_user.tenant_id,
        "user_role": auth_user.role,
        "user_roles": list(auth_user.roles),
        "user_permissions": sorted(auth_user.permissions),
        "resource_scopes": [{"permission": item.permission, "resource_type": item.resource_type,
                             "resource_key": item.resource_key} for item in auth_user.scopes],
        "trace_id": trace_id,
        "query": req.query,
        "execution_mode": req.execution_mode,
        "resolved_query": resolved_query,
        "current_service": current_service,
        "current_topic": conversation.get("current_topic"),
        "conversation_summary": prepared.summary,
        "recent_messages": recent_messages,
        "session_memory": memory,
        "long_term_memories": recalled_memories,
        "agent_results": {}, "model_calls": [], "tools_used": [], "citations": [], "tool_results": [],
        "external_evidence": [],
    })
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    payload = {
        "intent": result.get("intent", "unknown"),
        "answer": result.get("final_answer", ""),
        "citations": result.get("citations", []),
        "tools_used": result.get("tools_used", []),
        "selected_path": result.get("selected_path"),
        "selected_agents": result.get("selected_agents", []),
        "model_info": result.get("model_calls", []),
        "memory": public_memory(memory),
        "external_evidence": [
            ExternalEvidence.model_validate(item).model_dump()
            for item in result.get("external_evidence", [])
        ],
    }
    payload["evidence_quality"] = assess_evidence(result)

    user_message = await redis_store.append_session_message(session_id, {"role": "user", "content": req.query})
    assistant_message = await redis_store.append_session_message(
        session_id, {"role": "assistant", "content": payload["answer"]}
    )
    post_context = context_manager.prepare(
        prepared.summary,
        prepared.recent_messages + [user_message, assistant_message],
        summary_through_seq=prepared.summary_through_seq,
    )
    if post_context.stats["summarized_message_count"]:
        post_context.summary, _ = await refine_summary(
            post_context.summary, trace_id=trace_id,
            token_budget=context_manager.settings.context_summary_tokens,
            enabled=context_manager.settings.context_llm_summary_enabled,
        )
    response_context_stats = _context_stats_for_response(prepared, post_context)
    payload["context_info"] = response_context_stats

    cache_payload = {key: value for key, value in payload.items() if key not in {"model_info", "memory"}}
    cache_payload.update({
        "_current_service": result.get("current_service"),
        "_current_topic": result.get("current_topic"),
        "_summary": post_context.summary,
    })
    if cacheable:
        await redis_store.set_cached_answer(req.query, cache_payload, context_key=context_key)
    snapshot = {
        "current_service": result.get("current_service"),
        "current_topic": result.get("current_topic"),
        "summary": post_context.summary,
        "context_fingerprint": post_context.stats["context_fingerprint"],
        "context_stats": response_context_stats,
        "summary_through_seq": post_context.summary_through_seq,
        "memory": memory,
    }
    await _persist(session_id, req.user_id, trace_id, req.query, result, elapsed_ms)
    await _save_snapshot(session_id, req.user_id, snapshot)
    await long_term_memory.remember(auth_user.tenant_id, auth_user.id, session_id, req.query)
    return ChatResponse(session_id=session_id, trace_id=trace_id, cached=False, **payload)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, user: AuthUser = Depends(current_user)):
    require_permission(user, "agent.chat.use")
    """Idempotent, per-session serialized entry point around one Agent execution."""
    req = req.model_copy(update={"user_id": user.id})
    if req.request_id:
        prior = await redis_store.get_request_result(req.user_id, req.request_id)
        if prior:
            return ChatResponse(**prior)

    session_id = req.session_id or str(uuid.uuid4())
    request = req.model_copy(update={"session_id": session_id})
    lock_token = str(uuid.uuid4())
    if not await redis_store.acquire_session_lock(session_id, lock_token):
        raise HTTPException(status_code=409, detail="another request is already running for this session")
    try:
        response = await _chat_once(request, user)
        if request.request_id:
            await redis_store.set_request_result(
                request.user_id, request.request_id, response.model_dump(mode="json")
            )
        return response
    finally:
        await redis_store.release_session_lock(session_id, lock_token)


@router.post("/chat/stream")
async def chat_stream(req: ChatRequest, user: AuthUser = Depends(current_user)):
    """V1 为 Agent 事件级 SSE；V2 可继续升级为 token-level streaming。"""
    async def events():
        yield "event: status\ndata: " + json.dumps({"state": "running"}, ensure_ascii=False) + "\n\n"
        try:
            r = await chat(req, user)
            yield "event: result\ndata: " + r.model_dump_json() + "\n\n"
            yield "event: done\ndata: {}\n\n"
        except Exception as exc:
            yield "event: error\ndata: " + json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
