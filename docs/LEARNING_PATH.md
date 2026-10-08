# 学习路线（按顺序）

建议先通读 [项目学习与面试指南](INTERVIEW_STUDY_GUIDE.md)，建立业务和架构全局图，再按下面顺序进入源码。

1. MySQL：读 sql/001_schema.sql，在 DataGrip 练 SELECT/JOIN/GROUP BY/索引。
2. FastAPI：读 app/main.py、app/api/*，理解 Pydantic、async、SSE。
3. Redis：读 app/redis_store.py，理解 Session/Cache/Rate Limit。
4. RAG：Parser -> Chunk -> Embedding -> Qdrant -> Dense -> BM25 -> RRF -> Rerank。
5. LangGraph：画出 route/rag/db/mixed/answer 节点与边。
6. MCP：运行 09_RUN_MCP_INSPECTOR_WIN11.cmd，逐个调用工具。
7. vLLM：WSL2 部署 Qwen3-4B-Instruct-2507，把 .env 切到 openai_compatible。
8. Evaluation：跑 Retrieval Eval、Agent Eval、Cache Benchmark，把真实数字写进简历。
