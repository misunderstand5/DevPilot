# DevPilot 面试速查表

## 一句话

DevPilot 是一个面向研发运维场景的本地优先企业 Agent，通过语义路由把问题分发到 ACL RAG、只读业务工具或有界多 Agent 协作，并提供 JWT 租户认证、可恢复会话、跨会话长期记忆、引用和调用审计。

## 核心技术

- API：FastAPI、Pydantic、asyncio
- Agent：LangGraph、Manager–Specialist、fast path
- RAG：Embedding、Qdrant、BM25、RRF、可选 Rerank
- 数据：MySQL、Redis
- 模型：vLLM 本地模型、可选 OpenAI-compatible 强模型
- 工具：参数化只读 SQL、MCP
- 上下文：滑动窗口、结构化 LLM 摘要、Session Snapshot、SessionMemory、Long-term Memory
- 安全：四级 RBAC、Service/Repository Scope、tenant/user 隔离、文档 ACL、Qdrant 原生过滤、Prompt Injection 防护
- 可靠性：request_id 幂等、Redis session lock、限流、降级
- 评测：pytest、Recall@K、MRR、Intent/Tool/Memory 指标

## 四条执行路径

```text
Direct    → 简单对话和会话回忆
Knowledge → RAG 企业知识
Ops       → MySQL 实时事实
Complex   → Ops → Knowledge → Diagnosis → Supervisor
```

## 三个最重要的设计取舍

1. 知识和实时事实分离：SOP 走 RAG，发布/故障走 Tool。
2. 确定性优先：规则覆盖高置信路由，模型只处理歧义。
3. 本地和最小权限优先：内部数据默认 LOCAL_ONLY，Ops 只有四个只读工具。

## 上下文怎么做

```text
MySQL/Redis 历史
 → 单条截断
 → 最近消息滑动窗口
 → 旧消息结构化 LLM 摘要（失败时规则回退）
 → SessionMemory 保存关键实体
 → tenant_id + user_id 召回跨会话记忆
 → Resolver 补全“它/刚才/继续”
 → ContextProjector 分发给 Agent
```

## RAG 怎么做

```text
文档解析 → Chunk → Embedding → Qdrant
Query → MySQL ACL → Qdrant 原生 document_id 过滤 → Dense + BM25 → RRF → Top-K → LLM + Citation
```

## 如何防止幻觉

- 实时事实只能来自工具；
- 知识结论只能来自 evidence；
- 检索增加相关性阈值；
- 无证据时拒答；
- Citation 与真实 chunk 绑定；
- RAG 文档按不可信输入处理。

## 可靠性

- request_id：重复请求只产生一次结果；
- session lock：同一会话串行执行；
- MySQL：长期消息、Session Snapshot、长期记忆事实源和审计；
- Redis：热状态、TTL、锁、缓存、限流；
- STRONG 失败或隐私不允许时降级 LOCAL；
- 会话问题不使用公共缓存。

## 真实指标

```text
pytest                         75 passed
Intent Accuracy               100%（6 条）
Tool Success Rate             100%（6 条）
Answer Keyword Accuracy       100%（6 条）
Memory/Restore/Isolation      100%（2 个多轮场景）
RAG Recall@1                  87.5%（8 条）
RAG Recall@3 / Recall@5       100%（8 条）
RAG MRR                       0.9375
P50 / P95                     222.9 ms / 9166 ms
困难评测集                    240 条、12 类
在线困难 A/B                  12 条 × 单/多 Agent
单 Agent / 多 Agent 严格通过率 66.67% / 75.00%
单 Agent / 多 Agent P50       6264 ms / 5019 ms
```

必须同时说出样本规模，不能把本地小型评测描述成生产指标。

## 当前不足

- 已有四级应用 RBAC、资源 Scope 和文档 ACL，但没有企业 SSO、MFA、SCIM、Token 撤销和集中式策略引擎；
- 240 条困难评测已生成，但在线 A/B 只跑了首批 12 条；
- 固定复杂路径不是动态 Planner；
- 复杂生成延迟仍然较高；
- 长期记忆能版本化和删除，但提取类型、编辑和用户同意机制仍有限；
- 缺少异步索引任务和 LangGraph 持久化节点 checkpoint。

## 30 秒介绍

> 我实现了一个研发运维场景的本地优先企业 Agent。系统用 FastAPI 和 LangGraph 编排 Direct、Knowledge、Ops、Diagnosis、Supervisor，用 ACL 过滤的 Qdrant Dense、BM25 和 RRF 检索文档，用参数化只读工具查询实时数据，并通过本地只读 GitHub MCP 关联 Commit 证据；同时实现四级 RBAC、服务/仓库范围授权、结构化摘要、会话快照和跨会话长期记忆。目前 75 项测试通过，首批 12 条困难在线 A/B 中，多 Agent 严格通过率从 66.67% 提升到 75%。

GitHub MCP 实测链路：`版本查询 → recent_deployments → get_commit → RAG → Diagnosis/Supervisor → Evidence Gate`。Online Boutique `v0.10.7 / 5b608cb` 查询中，外部证据成功且质量评分 100%。

## 被追问时的原则

- 不把“多个 Prompt”吹成自主 Agent；
- 不把本地 JWT/ACL 基线说成完整企业 IAM；
- 不说模型拥有永久记忆，说明外部存储和 Prompt 注入链路；
- 不只报准确率，同时报样本规模、延迟和失败案例；
- 不回避固定图、在线 A/B 样本量、延迟和记忆治理等缺点；
- 能解释为什么做这个设计，而不只是用了哪些框架。

最新学习内容见 [DevPilot 项目学习与面试指南 V2](INTERVIEW_STUDY_GUIDE_V2.md)；原完整长版仍保留在 [详细指南](INTERVIEW_STUDY_GUIDE.md)。
