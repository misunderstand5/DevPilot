# Project Status

## V1 已实现
- FastAPI Gateway
- MySQL 业务/知识/Agent/评测表
- Redis Session / Cache / Rate Limit
- 文档解析（MD/TXT/PDF/DOCX）
- Qdrant Dense Retrieval
- BM25 + RRF Hybrid Retrieval
- 可选 CrossEncoder Rerank
- LangGraph Knowledge/Database/Mixed Router
- 参数化只读 MySQL Tools
- MCP Python SDK v2 Server
- WSL2 + vLLM 脚本
- Retrieval / Agent / Cache Evaluation
- Windows 一键 setup/start/stop 脚本

## V2 已实现（2026-10-06）
- Manager–Specialist LangGraph（Fast / Complex 双路径）
- Direct / Knowledge / Ops / Diagnosis / Supervisor Agent Registry
- LOCAL / STRONG 模型角色与 ModelScope 网关
- 默认 LOCAL_ONLY 隐私策略及有界降级
- ContextProjector 最小权限上下文隔离
- Redis 多轮会话实体与主题状态
- 工具调用与模型调用 MySQL 审计
- 30 条分类与多轮回归集
- 前端展示路径、Agent、工具与模型降级标签
- 6000-token 上下文预算、滑动窗口、滚动摘要与可见截断
- RAG 文档新增、同源自动更新、显式版本更新与 chunk 预览
- 同一用户多会话、MySQL 历史恢复与跨用户会话 403 隔离
- PBKDF2 密码、签名 Bearer Token、租户/用户数据库身份
- 文档 TENANT / PRIVATE 可见性、READ / WRITE ACL 与 ACL 感知 RAG
- 用户级缓存隔离、知识库提示注入过滤与危险请求策略门
- 48 份合成企业服务文档（12 服务 × 4 文档类型）及自动构建脚本
- 单/多 Agent 无缓存 A/B、16 条认证/ACL/无答案/对抗评测
- 结构化 LLM 滚动摘要、记忆冲突/版本/时间有效性
- Qdrant 原生 tenant_id / user_id 过滤
- 200+ 条困难场景评测集
- 运行总览、Agent 对话、发布、故障工单与知识库管理控制台
- 全局登录退出、历史会话恢复与宽屏/移动端响应式布局
- MySQL、Redis、Qdrant、vLLM 组件级健康检查
- 71 项自动化测试通过
- 可选 GitHub MCP 外部证据链：只读白名单、超时重试、结果截断、审计与降级
- 前端展示内部 Tool、Knowledge RAG 与 GitHub MCP 连接/证据状态

## 后续可扩展
- token-level SSE streaming
- Text-to-SQL + AST/权限防护
- Qdrant 原生 sparse/BM25
- Langfuse/OpenTelemetry tracing
- 企业 IdP 的 OIDC/SSO、Refresh Token、Token 吊销与密钥轮换
- 运维业务表的 tenant_id 改造（当前演示租户共享只读运维数据）
- Token 级流式前端渲染与工具执行时间线
