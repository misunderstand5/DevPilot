# DevPilot Architecture

## 分层

Client -> FastAPI Gateway -> LangGraph Router -> RAG / MySQL Tool / Mixed / Direct -> Answer + Citation + Tool Trace

基础设施：MySQL 保存业务事实与审计；Redis 保存 Session/Cache/Rate Limit；Qdrant 保存 Dense Vector；BM25 做词法检索；vLLM 提供 OpenAI-compatible LLM API。

## 为什么 MySQL + Qdrant

MySQL 擅长事务、关系、版本、精确筛选；Qdrant 擅长语义近邻搜索。`kb_chunk.vector_point_id` 把两者关联。

## 为什么 Hybrid Retrieval

Dense 对语义问题强；BM25 对错误码、接口名、版本号等精确 token 强。V1 使用 RRF 按 rank 融合，避免直接混加不同量纲 score。

## Agent 安全边界

V1 不让 LLM 任意执行 SQL，只能选择参数化只读 Tool：get_service_status、recent_deployments、open_incidents、open_tickets。

V2 可增加 bounded ReAct、max_steps/retry/timeout、token-level SSE、Qdrant sparse/BM25、Text-to-SQL sandbox。
