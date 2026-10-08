"""Curated cross-session user memory.

MySQL is the source of truth; Qdrant is only a user/tenant-filtered semantic index.
Only explicit, low-risk facts are extracted. Raw conversations and secrets are never
automatically promoted to long-term memory.
"""
import hashlib
import re
import uuid
from typing import Any

from qdrant_client import QdrantClient, models
from sqlalchemy import text

from app.config import get_settings
from app.db import session_scope
from app.services.embeddings import get_embedding_service


_NAME = re.compile(r"(?:我叫|我的名字是)(?!什么)([\w\u3400-\u9fff·]{1,20})")
_PREFERENCE = re.compile(r"(?:我喜欢|我偏好|请以后|以后请|我的习惯是)([^。！？\n]{2,120})")
_PROJECT = re.compile(r"(?:我正在做|我的项目是|长期目标是)([^。！？\n]{2,160})")
_SECRET = re.compile(r"(?i)(api[_-]?key|token|password|密码|密钥|secret|sk-[a-z0-9]|ms-[a-z0-9])")


def extract_memories(query: str) -> list[dict[str, str]]:
    """Extract only explicit durable facts; fail closed for possible secrets."""
    if _SECRET.search(query):
        return []
    candidates: list[dict[str, str]] = []
    for kind, pattern in (("identity", _NAME), ("preference", _PREFERENCE), ("project", _PROJECT)):
        match = pattern.search(query)
        if match:
            value = match.group(1).strip(" ，,。.!！？?")
            if value:
                candidates.append({"memory_type": kind, "content": value})
    return candidates


class LongTermMemoryService:
    def __init__(self, settings=None, qdrant=None):
        self.settings = settings or get_settings()
        self.qdrant = qdrant

    def _client(self):
        if self.qdrant is None:
            self.qdrant = QdrantClient(
                url=self.settings.qdrant_url, trust_env=False,
                check_compatibility=False, timeout=5.0,
            )
        return self.qdrant

    def ensure_collection(self) -> None:
        client = self._client()
        names = [item.name for item in client.get_collections().collections]
        if self.settings.qdrant_memory_collection not in names:
            dim = len(get_embedding_service().embed_query("memory dimension probe"))
            client.create_collection(
                collection_name=self.settings.qdrant_memory_collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )

    async def remember(self, tenant_id: str, user_id: str, session_id: str, query: str) -> list[dict]:
        if not self.settings.long_term_memory_enabled:
            return []
        extracted = extract_memories(query)
        if not extracted:
            return []
        saved = []
        for item in extracted:
            fingerprint = hashlib.sha256(
                f"{tenant_id}|{user_id}|{item['memory_type']}|{item['content'].lower()}".encode("utf-8")
            ).hexdigest()
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, fingerprint))
            superseded_ids: list[str] = []
            async with session_scope() as db:
                # Identity and current project are single-valued memories. Keep history for
                # audit, but only the newest value remains eligible for retrieval.
                if item["memory_type"] in {"identity", "project"}:
                    old = await db.execute(text("""
                        SELECT id FROM user_memory
                        WHERE tenant_id=:tenant AND user_id=:user AND memory_type=:kind
                          AND status='ACTIVE' AND fingerprint<>:fp
                    """), {"tenant": tenant_id, "user": user_id,
                            "kind": item["memory_type"], "fp": fingerprint})
                    superseded_ids = [str(row.id) for row in old]
                    if superseded_ids:
                        await db.execute(text("""
                            UPDATE user_memory SET status='SUPERSEDED',superseded_by=:new_id,updated_at=NOW()
                            WHERE tenant_id=:tenant AND user_id=:user AND memory_type=:kind
                              AND status='ACTIVE' AND fingerprint<>:fp
                        """), {"new_id": point_id, "tenant": tenant_id, "user": user_id,
                                "kind": item["memory_type"], "fp": fingerprint})
                result = await db.execute(text("""
                    INSERT INTO user_memory(
                      id,tenant_id,user_id,memory_type,content,fingerprint,source_session_id,
                      confidence,status,last_accessed_at
                    ) VALUES(:id,:tenant,:user,:kind,:content,:fp,:session,1.0,'ACTIVE',NOW())
                    ON DUPLICATE KEY UPDATE content=VALUES(content),source_session_id=VALUES(source_session_id),
                      status='ACTIVE',updated_at=NOW()
                """), {"id": point_id, "tenant": tenant_id, "user": user_id,
                        "kind": item["memory_type"], "content": item["content"],
                        "fp": fingerprint, "session": session_id})
            try:
                self.ensure_collection()
                vector = get_embedding_service().embed_query(item["content"])
                self._client().upsert(collection_name=self.settings.qdrant_memory_collection, points=[
                    models.PointStruct(id=point_id, vector=vector.tolist(), payload={
                        "tenant_id": tenant_id, "user_id": user_id,
                        "memory_type": item["memory_type"], "content": item["content"],
                    })
                ])
                if superseded_ids:
                    self._client().delete(
                        collection_name=self.settings.qdrant_memory_collection,
                        points_selector=models.PointIdsList(points=superseded_ids),
                    )
            except Exception:
                # Durable MySQL write remains valid; retrieval has a SQL fallback.
                pass
            saved.append({"id": point_id, **item})
        return saved

    async def recall(self, tenant_id: str, user_id: str, query: str) -> list[dict[str, Any]]:
        if not self.settings.long_term_memory_enabled:
            return []
        items: list[dict[str, Any]] = []
        try:
            self.ensure_collection()
            vector = get_embedding_service().embed_query(query)
            conditions = [
                models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id)),
                models.FieldCondition(key="user_id", match=models.MatchValue(value=user_id)),
            ]
            points = self._client().query_points(
                collection_name=self.settings.qdrant_memory_collection, query=vector.tolist(),
                query_filter=models.Filter(must=conditions),
                limit=self.settings.long_term_memory_top_k, with_payload=True,
                score_threshold=self.settings.long_term_memory_min_score,
            ).points
            items = [{**dict(p.payload or {}), "id": str(p.id), "score": float(p.score)} for p in points]
        except Exception:
            pass
        # Identity/preferences are useful at session start even when vector service is unavailable.
        if not items:
            async with session_scope() as db:
                rows = await db.execute(text("""
                    SELECT id,memory_type,content,confidence FROM user_memory
                    WHERE tenant_id=:tenant AND user_id=:user AND status='ACTIVE'
                      AND (expires_at IS NULL OR expires_at>NOW())
                    ORDER BY updated_at DESC LIMIT :n
                """), {"tenant": tenant_id, "user": user_id, "n": self.settings.long_term_memory_top_k})
                items = [dict(row._mapping) for row in rows]
        return items[: self.settings.long_term_memory_top_k]

    async def list_for_user(self, tenant_id: str, user_id: str) -> list[dict]:
        async with session_scope() as db:
            rows = await db.execute(text("""
                SELECT id,memory_type,content,confidence,source_session_id,created_at,updated_at
                FROM user_memory WHERE tenant_id=:tenant AND user_id=:user AND status='ACTIVE'
                  AND (expires_at IS NULL OR expires_at>NOW())
                ORDER BY updated_at DESC
            """), {"tenant": tenant_id, "user": user_id})
            return [dict(row._mapping) for row in rows]

    async def forget(self, memory_id: str, tenant_id: str, user_id: str) -> bool:
        async with session_scope() as db:
            result = await db.execute(text("""
                UPDATE user_memory SET status='DELETED',updated_at=NOW()
                WHERE id=:id AND tenant_id=:tenant AND user_id=:user AND status='ACTIVE'
            """), {"id": memory_id, "tenant": tenant_id, "user": user_id})
            changed = result.rowcount > 0
        if changed:
            try:
                self._client().delete(
                    collection_name=self.settings.qdrant_memory_collection,
                    points_selector=models.PointIdsList(points=[memory_id]),
                )
            except Exception:
                pass
        return changed


long_term_memory = LongTermMemoryService()
