import hashlib
import re
import uuid
from pathlib import Path

import jieba
from qdrant_client import QdrantClient, models
from rank_bm25 import BM25Okapi
from sqlalchemy import text

from app.config import get_settings
from app.db import session_scope
from app.services.embeddings import get_embedding_service
from app.services.parsers import chunk_text, read_document
from app.security import AuthUser
from app.services.acl import accessible_document_ids


def _tokens(s: str):
    return [x.strip().lower() for x in jieba.lcut(s) if x.strip()]


class RAGService:
    def __init__(self):
        self.settings = get_settings()
        # Local infrastructure must not be routed through a machine-wide HTTP
        # proxy. Otherwise Qdrant calls to 127.0.0.1 can fail with a proxy 502.
        self.qdrant = QdrantClient(
            url=self.settings.qdrant_url,
            trust_env=False,
            check_compatibility=False,
            timeout=5.0,
        )
        self._bm25 = None
        self._bm25_rows: list[dict] = []
        self._ensure_collection()

    def _ensure_collection(self):
        dim = len(get_embedding_service().embed_query("dimension probe"))
        names = [c.name for c in self.qdrant.get_collections().collections]
        if self.settings.qdrant_collection not in names:
            self.qdrant.create_collection(
                collection_name=self.settings.qdrant_collection,
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
            )

    async def refresh_bm25(self):
        async with session_scope() as db:
            rs = await db.execute(text("""
                SELECT c.id,c.document_id,c.content,c.heading,d.title,d.source_uri
                FROM kb_chunk c JOIN kb_document d ON d.id=c.document_id
                WHERE d.status='INDEXED' ORDER BY c.id
            """))
            self._bm25_rows = [dict(x._mapping) for x in rs]
        corpus = [_tokens(x["content"]) for x in self._bm25_rows]
        self._bm25 = BM25Okapi(corpus) if corpus else None

    async def ingest_file(
        self,
        path: Path,
        *,
        title: str | None = None,
        source_uri: str | None = None,
        document_id: int | None = None,
        tenant_id: str | None = None,
        owner_user_id: str | None = None,
        visibility: str = "TENANT",
    ):
        content = read_document(path)
        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        chunks = chunk_text(content)
        if not chunks:
            raise ValueError("No text chunks extracted")

        title = title or path.stem
        source_uri = source_uri or str(path)
        doc_type = path.suffix.lower().lstrip(".")

        vectors = get_embedding_service().embed_documents([x["content"] for x in chunks])
        old_ids: list[str] = []
        new_ids: list[str] = []
        updated = False
        try:
            async with session_scope() as db:
                duplicate = await db.execute(
                    text("SELECT id,status FROM kb_document WHERE checksum=:c AND tenant_id=:tenant LIMIT 1"),
                    {"c": checksum, "tenant": tenant_id}
                )
                duplicate_row = duplicate.first()
                if duplicate_row and (document_id is None or duplicate_row.id != document_id):
                    return {"document_id": duplicate_row.id, "skipped": True, "updated": False,
                            "reason": "checksum already indexed"}

                row = None
                if document_id is not None:
                    existing = await db.execute(
                        text("SELECT id,checksum,version,title,source_uri FROM kb_document WHERE id=:id AND tenant_id=:tenant FOR UPDATE"),
                        {"id": document_id, "tenant": tenant_id},
                    )
                    row = existing.first()
                    if not row:
                        raise LookupError("document_not_found")
                else:
                    by_source = await db.execute(
                        text("SELECT id,checksum,version,title,source_uri FROM kb_document WHERE source_uri=:u AND tenant_id=:tenant ORDER BY id DESC LIMIT 1 FOR UPDATE"),
                        {"u": source_uri, "tenant": tenant_id},
                    )
                    row = by_source.first()

                if row and row.checksum == checksum:
                    return {"document_id": row.id, "skipped": True, "updated": False,
                            "reason": "checksum already indexed"}
                if row:
                    doc_id = row.id
                    updated = True
                    old = await db.execute(
                        text("SELECT vector_point_id FROM kb_chunk WHERE document_id=:id"), {"id": doc_id}
                    )
                    old_ids = [item[0] for item in old.fetchall()]
                    await db.execute(text("DELETE FROM kb_chunk WHERE document_id=:id"), {"id": doc_id})
                    await db.execute(text("""
                        UPDATE kb_document SET source_uri=:u,title=:t,doc_type=:dt,checksum=:c,visibility=:visibility,
                          version=version+1,status='PENDING',chunk_count=0
                        WHERE id=:id
                    """), {"u": source_uri, "t": title, "dt": doc_type, "c": checksum,
                            "visibility": visibility, "id": doc_id})
                else:
                    created = await db.execute(text("""
                        INSERT INTO kb_document(tenant_id,owner_user_id,visibility,source_uri,title,doc_type,checksum,status)
                        VALUES(:tenant,:owner,:visibility,:u,:t,:dt,:c,'PENDING')
                    """), {"tenant": tenant_id, "owner": owner_user_id, "visibility": visibility,
                            "u": source_uri, "t": title, "dt": doc_type, "c": checksum})
                    doc_id = created.lastrowid

                points = []
                for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
                    point_id = str(uuid.uuid4())
                    new_ids.append(point_id)
                    inserted = await db.execute(text("""
                        INSERT INTO kb_chunk(document_id,vector_point_id,chunk_index,heading,content,char_count)
                        VALUES(:d,:v,:i,:h,:c,:n)
                    """), {
                        "d": doc_id, "v": point_id, "i": i, "h": chunk.get("heading"),
                        "c": chunk["content"], "n": len(chunk["content"]),
                    })
                    points.append(models.PointStruct(
                        id=point_id, vector=vector.tolist(), payload={
                            "chunk_id": inserted.lastrowid, "document_id": doc_id,
                            "title": title, "source_uri": source_uri, "tenant_id": tenant_id,
                            "owner_user_id": owner_user_id, "visibility": visibility,
                            "heading": chunk.get("heading"), "content": chunk["content"],
                        },
                    ))
                self.qdrant.upsert(collection_name=self.settings.qdrant_collection, points=points)
                await db.execute(text("""
                    UPDATE kb_document SET status='INDEXED',chunk_count=:n WHERE id=:id
                """), {"n": len(chunks), "id": doc_id})
        except Exception:
            if new_ids:
                self.qdrant.delete(
                    collection_name=self.settings.qdrant_collection,
                    points_selector=models.PointIdsList(points=new_ids),
                )
            raise

        if old_ids:
            self.qdrant.delete(
                collection_name=self.settings.qdrant_collection,
                points_selector=models.PointIdsList(points=old_ids),
                wait=False,
            )
        await self.refresh_bm25()
        return {"document_id": doc_id, "chunks": len(chunks), "skipped": False, "updated": updated}

    async def dense_search(self, query: str, top_k: int | None = None, allowed_document_ids: set[int] | None = None):
        top_k = top_k or self.settings.rag_dense_top_k
        qvec = get_embedding_service().embed_query(query)
        query_filter = None
        if allowed_document_ids is not None:
            if not allowed_document_ids:
                return []
            query_filter = models.Filter(must=[models.FieldCondition(
                key="document_id", match=models.MatchAny(any=list(allowed_document_ids))
            )])
        dense = self.qdrant.query_points(
            collection_name=self.settings.qdrant_collection,
            query=qvec.tolist(),
            limit=top_k,
            with_payload=True,
            query_filter=query_filter,
        ).points
        out = []
        for rank, p in enumerate(dense, 1):
            x = dict(p.payload or {})
            x["dense_score"] = float(p.score)
            x["dense_rank"] = rank
            out.append(x)
        return out

    async def bm25_search(self, query: str, top_k: int | None = None):
        top_k = top_k or self.settings.rag_bm25_top_k
        if self._bm25 is None:
            await self.refresh_bm25()
        if not self._bm25 or not self._bm25_rows:
            return []
        scores = self._bm25.get_scores(_tokens(query))
        top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        out = []
        for rank, idx in enumerate(top_idx, 1):
            row = dict(self._bm25_rows[idx])
            row["chunk_id"] = row.pop("id")
            row["bm25_score"] = float(scores[idx])
            row["bm25_rank"] = rank
            out.append(row)
        return out

    async def hybrid_search(
        self, query: str, final_top_k: int | None = None, use_rerank: bool = True,
        allowed_document_ids: set[int] | None = None,
    ):
        dense_items = await self.dense_search(
            query, top_k=max(self.settings.rag_dense_top_k, 60),
            allowed_document_ids=allowed_document_ids,
        )
        bm_items = await self.bm25_search(query, top_k=max(self.settings.rag_bm25_top_k, 60))
        if allowed_document_ids is not None:
            dense_items = [item for item in dense_items if int(item.get("document_id", -1)) in allowed_document_ids]
            bm_items = [item for item in bm_items if int(item.get("document_id", -1)) in allowed_document_ids]

        # If a query explicitly names a service, evidence for a different
        # service is not an acceptable nearest neighbour.  This is the most
        # important no-answer guard for enterprise service catalogs.
        named_services = set(re.findall(r"(?<![a-z0-9-])([a-z0-9]+(?:-[a-z0-9]+)*-service)(?![a-z0-9-])", query.lower()))
        if named_services:
            def service_matches(item: dict) -> bool:
                haystack = f"{item.get('title', '')}\n{item.get('content', '')}".lower()
                return any(service in haystack for service in named_services)
            dense_items = [item for item in dense_items if service_matches(item)]
            bm_items = [item for item in bm_items if service_matches(item)]

        # RRF 融合 rank，避免 cosine 与 BM25 score 量纲不同直接相加。
        merged: dict[int, dict] = {}
        k = 60.0
        for x in dense_items:
            cid = int(x["chunk_id"])
            base = merged.setdefault(cid, dict(x))
            base["rrf"] = base.get("rrf", 0.0) + 1.0 / (k + x["dense_rank"])
        for x in bm_items:
            cid = int(x["chunk_id"])
            base = merged.setdefault(cid, dict(x))
            base["bm25_score"] = x["bm25_score"]
            base["rrf"] = base.get("rrf", 0.0) + 1.0 / (k + x["bm25_rank"])

        fused = sorted(merged.values(), key=lambda x: x.get("rrf", 0.0), reverse=True)
        # Dense retrieval always returns neighbours. Require actual lexical or
        # semantic relevance so unrelated questions can safely produce no answer.
        fused = [item for item in fused if (
            item.get("bm25_score", 0.0) > 0
            or item.get("dense_score", 0.0) >= self.settings.rag_min_dense_score
        )]
        fused = fused[: self.settings.rag_fused_top_k]
        final_top_k = final_top_k or self.settings.rag_final_top_k
        if use_rerank:
            return get_embedding_service().rerank(query, fused, final_top_k)
        return fused[:final_top_k]

    async def search(self, query: str, user: AuthUser | None = None):
        allowed = await accessible_document_ids(user) if user else None
        return await self.hybrid_search(query, use_rerank=True, allowed_document_ids=allowed)

    async def delete_document(self, document_id: int, tenant_id: str) -> bool:
        async with session_scope() as db:
            existing = await db.execute(text(
                "SELECT id FROM kb_document WHERE id=:id AND tenant_id=:tenant"
            ), {"id": document_id, "tenant": tenant_id})
            if not existing.first():
                return False
            points = await db.execute(text(
                "SELECT vector_point_id FROM kb_chunk WHERE document_id=:id"
            ), {"id": document_id})
            point_ids = [row[0] for row in points]
            await db.execute(text("DELETE FROM kb_document WHERE id=:id"), {"id": document_id})
        if point_ids:
            self.qdrant.delete(
                collection_name=self.settings.qdrant_collection,
                points_selector=models.PointIdsList(points=point_ids),
                wait=False,
            )
        await self.refresh_bm25()
        return True


_instance = None


def get_rag_service() -> RAGService:
    global _instance
    if _instance is None:
        _instance = RAGService()
    return _instance
