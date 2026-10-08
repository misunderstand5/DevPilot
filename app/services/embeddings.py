from sentence_transformers import SentenceTransformer, CrossEncoder
from app.config import get_settings


class EmbeddingService:
    def __init__(self):
        s = get_settings()
        self.settings = s
        self.model = SentenceTransformer(s.embed_model, device=s.embed_device)
        self.reranker = CrossEncoder(s.rerank_model, device=s.embed_device) if s.rerank_enabled else None

    def embed_documents(self, texts: list[str]):
        return self.model.encode(
            ["passage: " + t for t in texts],
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def embed_query(self, text: str):
        return self.model.encode(
            ["query: " + text],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]

    def rerank(self, query: str, items: list[dict], top_k: int):
        if not self.reranker or not items:
            return items[:top_k]
        scores = self.reranker.predict([(query, x["content"]) for x in items])
        for x, score in zip(items, scores):
            x["rerank_score"] = float(score)
        return sorted(items, key=lambda x: x["rerank_score"], reverse=True)[:top_k]


_instance = None


def get_embedding_service() -> EmbeddingService:
    global _instance
    if _instance is None:
        _instance = EmbeddingService()
    return _instance
