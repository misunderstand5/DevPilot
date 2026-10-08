from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app.db import session_scope
from app.redis_store import redis_store
from app.schemas import SessionRenameRequest
from app.security import AuthUser, current_user

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(limit: int = Query(20, ge=1, le=100), user: AuthUser = Depends(current_user)):
    async with session_scope() as db:
        result = await db.execute(text("""
            SELECT s.id,s.title,s.created_at,s.last_active_at,COUNT(m.id) AS message_count,
                   (SELECT content FROM agent_message x WHERE x.session_id=s.id
                    ORDER BY x.id DESC LIMIT 1) AS last_message
            FROM agent_session s
            LEFT JOIN agent_message m ON m.session_id=s.id
            WHERE s.user_id=:u
            GROUP BY s.id,s.title,s.created_at,s.last_active_at
            ORDER BY s.last_active_at DESC LIMIT :n
        """), {"u": user.id, "n": limit})
        return {"user_id": user.id, "sessions": [dict(row._mapping) for row in result]}


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    limit: int = Query(50, ge=1, le=200),
    user: AuthUser = Depends(current_user),
):
    async with session_scope() as db:
        owner = await db.execute(text("SELECT user_id,title FROM agent_session WHERE id=:s"), {"s": session_id})
        session = owner.first()
        if not session:
            raise HTTPException(404, "session not found")
        if session.user_id != user.id:
            raise HTTPException(403, "session belongs to another user")
        result = await db.execute(text("""
            SELECT role,content,trace_id,created_at FROM (
              SELECT id,role,content,trace_id,created_at FROM agent_message
              WHERE session_id=:s ORDER BY id DESC LIMIT :n
            ) recent ORDER BY id
        """), {"s": session_id, "n": limit})
        state = await redis_store.get_conversation_state(session_id)
        if not state:
            snapshot_result = await db.execute(text("""
                SELECT summary,summary_through_seq,memory_json,context_json
                FROM agent_session_snapshot WHERE session_id=:s AND user_id=:u
            """), {"s": session_id, "u": user.id})
            snapshot = snapshot_result.first()
            if snapshot:
                state = dict(snapshot.context_json or {})
                state.update({"summary": snapshot.summary or "",
                              "summary_through_seq": int(snapshot.summary_through_seq or 0),
                              "memory": dict(snapshot.memory_json or {})})
                await redis_store.set_conversation_state(session_id, state)
        return {
            "session_id": session_id, "title": session.title,
            "messages": [dict(row._mapping) for row in result], "context_state": state,
        }


@router.patch("/{session_id}")
async def rename_session(session_id: str, req: SessionRenameRequest, user: AuthUser = Depends(current_user)):
    async with session_scope() as db:
        result = await db.execute(text("""
            UPDATE agent_session SET title=:t
            WHERE id=:s AND user_id=:u
        """), {"s": session_id, "u": user.id, "t": req.title.strip()})
        if result.rowcount == 0:
            raise HTTPException(404, "session not found for this user")
    return {"session_id": session_id, "title": req.title.strip()}
