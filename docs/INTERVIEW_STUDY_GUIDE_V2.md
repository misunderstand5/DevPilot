# DevPilot 最新项目学习与面试指南（2026-10）

> 目标：能解释为什么这样设计、一次请求怎样运行、权限在哪里生效、评测如何证明收益，以及当前真实边界。

## 1. 项目到底解决什么问题

DevPilot 是面向研发运维的本地优先企业 Agent，把三类割裂的信息统一到对话入口：

1. 文档知识：部署手册、故障 SOP、接口契约。
2. 运行事实：服务状态、发布、事故和工单。
3. 代码证据：GitHub Commit、提交说明和变更文件。

核心逻辑是：RAG 证明“规范怎么说”，Ops Tool 证明“系统发生了什么”，GitHub MCP 证明“代码改了什么”，Multi-Agent 组织联合诊断，RBAC 决定谁能访问哪些能力和资源。

## 2. 四类请求与业务边界

| 类型 | 示例 | 路径 |
| --- | --- | --- |
| Direct | “我刚才查的是哪个服务？” | Direct + SessionMemory |
| Knowledge | “order-service 如何部署？” | Knowledge + Hybrid RAG |
| Ops | “最近 7 天发布情况？” | Ops + 只读工具 |
| Mixed | “结合失败发布和 SOP 分析原因” | Ops → Knowledge → Diagnosis → Supervisor |

当前只开放查询与诊断，不自动发布、回滚或修改工单，也不允许模型执行任意 SQL。生产写操作需要额外的审批、幂等、补偿和 Human-in-the-loop。

## 3. 整体架构

```text
Web Console → FastAPI
  ├─ JWT + current_user
  ├─ RBAC Permission
  ├─ Service / Repository Scope
  ├─ Tenant + Document ACL
  └─ Rate Limit / Idempotency / Session Lock
       ↓
Context Engineering
  ├─ MySQL Message + Snapshot
  ├─ Redis Hot State
  ├─ Sliding Window + Structured Summary
  ├─ SessionMemory + Long-term Memory
  └─ ContextProjector
       ↓
LangGraph Router
  ├─ Direct
  ├─ Knowledge → Dense + BM25 + RRF → Qdrant
  ├─ Ops → Read-only Tools → MySQL
  └─ Mixed → Ops + Knowledge → Diagnosis → Supervisor
                    └─ GitHub MCP
       ↓
Evidence Quality Gate → Answer + Citation + Trace
```

基础设施分工：MySQL 保存事实和持久状态；Redis 保存热状态、锁与幂等结果；Qdrant 负责知识和长期记忆向量；vLLM 在 RTX 4090 上提供本地推理；Docker Compose 管理基础组件。

## 4. Mixed 请求完整生命周期

以“order-service 最近发布为什么失败，结合 SOP 排查”为例：

1. JWT 提供身份，服务端重新查询用户状态和 RBAC，不直接相信 Token 中的旧角色。
2. 加载 Permission、Service Scope、Repository Scope。
3. 检查 request_id 幂等结果，获取 Redis session lock。
4. 从 Redis 或 MySQL Snapshot 恢复上下文，解析服务和时间范围。
5. Router 选择 Mixed 路径。
6. Ops 校验 `ops.deployment.read + SERVICE scope` 后查询固定参数化 SQL。
7. 需要代码归因时校验 `mcp.github.commit.read + REPOSITORY scope`，调用 GitHub MCP。
8. Knowledge 计算可读 document_id，再执行带过滤的混合检索。
9. Diagnosis 关联发布、代码和 SOP，Supervisor 生成结果。
10. Evidence Quality Gate 检查引用、工具事实和外部证据是否真实存在。
11. 持久化消息、工具/模型日志、Snapshot 和必要的长期记忆。

## 5. 多 Agent 的工程价值

- Knowledge 只能处理文档证据。
- Ops 只能调用有限只读工具。
- Diagnosis 不直接访问数据源，只消费确认后的证据。
- Supervisor 负责最终表达，不拥有额外权限。

简单问题走 fast path，避免无意义地调用所有 Agent。当前是固定有界 Manager–Specialist 图，不是无限 ReAct，也不是完全自主 Planner。

暂不使用 A2A，因为所有 Agent 仍处于同一进程、同一 LangGraph 和同一安全域。A2A 更适合跨团队、跨服务且具有独立身份与生命周期的 Agent。

## 6. RAG 必须掌握的内容

```text
文件校验 → 解析 → Chunk → Embedding
→ MySQL Metadata → Qdrant Vector → BM25 Corpus

Query → Document ACL → Qdrant Filter
→ Dense + BM25 → RRF → Threshold → Top-K → Citation
```

Dense 处理语义相似，BM25 处理错误码、版本和接口名。RRF 用排名融合不同检索器：

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

向量库即使面对无关问题也会返回最近邻，因此必须增加相关性阈值和无答案处理。Citation 由后端绑定真实 document/chunk，不能让模型自行编造。

## 7. 上下文与记忆

```text
Turn 持久化
→ 最近 Turn 进入 Sliding Window
→ 旧 Turn 进入 Structured Rolling Summary
→ SessionMemory 保存关键实体和约束
→ Long-term Memory 按 tenant_id + user_id 召回
→ ContextProjector 向各 Agent 投影最小上下文
```

摘要保存叙事背景，结构化记忆负责稳定字段和用户纠正。LLM 摘要必须通过 JSON Schema 和 Token 预算；失败时使用确定性摘要。Redis 过期后从 MySQL 消息和 `agent_session_snapshot` 恢复，所以刷新或缓存失效不会丢会话。

长期记忆只保存明确、低风险、相对稳定的事实；密码和 Token 不入库。冲突事实通过 ACTIVE、SUPERSEDED、DELETED 和有效期管理。

## 8. RBAC、Scope 与 ACL

三层授权分别解决不同问题：

1. RBAC：能做什么。
2. Resource Scope：能对哪些 Service/Repository 做。
3. Document ACL：能访问哪份文档。

| 角色 | 能力 | 边界 |
| --- | --- | --- |
| end_user | 自己的会话/记忆、知识读取、授权范围内工具 | 无管理权 |
| developer | 继承 end_user；自己的 Trace、评测和 Agent 配置 | 不看其他用户数据 |
| tenant_admin | 继承 developer；本租户用户、知识、ACL、Scope | 不跨租户、不管集群 |
| system_admin | 平台、模型、MCP、可观测性和集群 | 独立角色，不默认读租户内容 |

前端隐藏按钮只改善体验，真正鉴权发生在 API 和 Agent 工具调用层。`system_admin` 不设计成业务数据超级用户，是为了分离平台控制权与租户数据访问权。

## 9. MCP、普通函数与 A2A

- 内部 MySQL 工具与应用同进程，直接函数调用延迟低、身份传递简单。
- GitHub 是独立外部系统，MCP 提供统一工具发现、Schema 和传输协议。
- A2A 解决独立 Agent 服务之间的发现、身份和任务协作，当前不需要。

GitHub MCP 使用本地回环地址、服务端只读模式、`repos` 工具集、客户端 `get_commit` 白名单，并在调用前检查 RBAC 和 Repository Scope；还设置超时、有限重试和结果大小限制。

## 10. 可靠性与安全

- request_id：重试不重复生成结果。
- Redis session lock：同一会话 Turn 串行执行。
- 参数化只读 SQL：模型无法接触数据库连接和任意 SQL。
- Prompt Injection：RAG 正文视为不可信数据，不能覆盖系统规则或触发工具。
- LOCAL_ONLY：企业上下文默认不发送到云端模型。
- 有界重试：防止下游故障放大。
- `/health`：真实检查 MySQL、Redis、Qdrant 和本地模型。
- Windows 预检：自动启动 Docker、生成缺失的本地随机凭据并复用已有数据卷密码。

## 11. 当前评测与正确表达

| 指标 | 结果 | 样本边界 |
| --- | ---: | --- |
| 自动化测试 | 75 passed | 单元/集成基线 |
| Intent / Tool Success | 100% / 100% | 6 条 |
| RAG Recall@1 | 87.5% | 8 条 |
| RAG Recall@3/5 | 100% | 8 条 |
| RAG MRR | 0.9375 | 8 条 |
| 记忆/恢复/隔离 | 100% | 2 个多轮场景 |
| 困难评测集 | 240 条 | 12 类离线用例 |
| 单/多 Agent 严格通过率 | 66.67% / 75.00% | 首批 12 条在线 A/B |
| 单/多 Agent P50 | 6264 / 5019 ms | 同批在线 A/B |

必须同时说出样本量。首批 A/B 说明阶段性趋势，不能证明生产 SLA 或统计显著性。

## 12. 高频问题回答框架

### 为什么不用一个大 Prompt？

Prompt 不能替代权限、实时数据、持久记忆和证据追踪。系统需要存储恢复上下文、工具查询事实、RAG 提供来源、路由控制成本。

### 为什么不用 Text-to-SQL？

当前工具少且稳定，固定参数化 SQL 更安全可审计。未来若引入，需要只读账号、Schema 白名单、AST 校验、行数与超时限制。

### 上下文超长怎么办？

单条截断、最近消息窗口、旧历史摘要、关键实体结构化保存，再通过 ContextProjector 只发送必要字段。

### 如何保证不同用户不串数据？

Session 校验 owner；长期记忆按 tenant+user 过滤；RAG 先做文档 ACL；Ops/MCP 检查 Permission+Scope；请求体 user_id 不作为可信身份。

### 多 Agent 是否真的更好？

用同一模型、工具和困难样本进行 A/B。首批提升 8.33 个百分点，但样本仅 12 条，下一步需要全量、多次重复和置信区间。

### 当前最大不足？

缺少企业 SSO/MFA/SCIM；在线 A/B 样本小；尚未接入真实 Prometheus/Kubernetes/Trace；复杂路径仍是固定图；长期记忆缺少完整同意/编辑/导出；索引仍同步；写操作没有审批与补偿。

## 13. 面试表达模板

### 30 秒版

> 我实现了一个研发运维场景的本地优先多 Agent Copilot。系统用 Hybrid RAG 查询规范，用参数化只读工具查询发布、故障和工单，再通过 GitHub MCP 关联代码提交；复杂问题由 Knowledge、Ops、Diagnosis、Supervisor 基于证据协同诊断。工程上实现了结构化上下文、会话快照、长期记忆，以及四级 RBAC、资源 Scope 和文档 ACL。目前 75 项测试通过，首批 12 条困难 A/B 中多 Agent 严格通过率从 66.67% 提升到 75%。

### 两分钟版

> 项目解决的是研发排障时知识、运行事实和代码变化分散的问题。我先用语义路由把请求分成 Direct、Knowledge、Ops 和 Mixed。Knowledge 使用 Dense+BM25+RRF 并返回 chunk 引用；Ops 只开放四个参数化只读工具；版本归因通过 GitHub MCP 获取 Commit；复杂问题再由 Diagnosis 和 Supervisor 合并证据。
>
> 上下文方面，用滑动窗口、结构化摘要和 SessionMemory 控制 Token，用 MySQL Snapshot 解决刷新和 Redis 过期恢复，用 Qdrant 隔离长期记忆。安全方面实现四级 RBAC，并叠加服务、仓库 Scope 和文档 ACL，权限在 API 与工具层同时检查。
>
> 当前 75 项测试通过；240 条困难集已建立，首批 12 条在线 A/B 中，多 Agent 严格通过率从 66.67% 提升到 75%。我会明确说明样本仍小，下一步需要全量重复实验和真实可观测性证据。

## 14. 推荐代码阅读顺序

1. `main.py`、`api/chat.py`：请求生命周期。
2. `security.py`、`services/rbac.py`、`api/rbac.py`：权限系统。
3. `agent/state.py`、`router.py`、`graph.py`、`specialists.py`：Agent 图。
4. `context_manager.py`、`structured_summary.py`、`session_memory.py`、`long_term_memory.py`：上下文。
5. `rag.py`、`embeddings.py`、`parsers.py`、`acl.py`：RAG。
6. `tools.py`、`mcp_gateway.py`、`model_gateway.py`：工具和模型。
7. `tests/`、`scripts/eval_*.py`：测试和评测。

## 15. 七天学习计划

- Day 1：画业务与整体架构图。
- Day 2：跟踪一次 `/chat` 请求，理解幂等、锁和持久化。
- Day 3：阅读 Router/Graph/Specialists，手判 20 个问题的路径。
- Day 4：模拟 10 轮对话，理解窗口、摘要和两类记忆。
- Day 5：手算 RRF，运行 RAG 评测并分析误召回。
- Day 6：验证四角色、Service/Repository Scope、ACL 和越权拒绝。
- Day 7：运行测试与 A/B，练习项目介绍和缺陷改进题。

## 16. 最终自检问题

1. 为什么知识、实时事实和代码证据必须分开？
2. Dense、BM25、RRF 分别解决什么？
3. Redis 丢失后会话为什么还能恢复？
4. RBAC、Resource Scope、Document ACL 有什么区别？
5. 为什么权限必须在工具层再次检查？
6. MCP、函数调用、A2A 分别解决什么问题？
7. 单/多 Agent A/B 如何做到公平？
8. 当前评测数字能证明什么、不能证明什么？
9. 为什么 system_admin 不默认拥有租户数据权限？
10. 接入生产写操作时如何设计审批、幂等和补偿？
