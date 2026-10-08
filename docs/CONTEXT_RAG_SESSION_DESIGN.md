# DevPilot 上下文、RAG 与会话设计

## 1. 上下文工程

### 请求上下文的组成

```text
结构化会话状态
  ├─ SessionMemory（用户事实 / 服务 / 环境 / 时间范围 / 当前目标）
  ├─ current_service / current_topic
  ├─ rolling_summary（旧消息压缩）
  └─ recent_messages（token-aware 滑动窗口）
             ↓ ContextProjector
Agent 专属最小上下文 + 当前 query + RAG/Tool 证据
```

历史消息不会直接无限追加到 prompt。当前默认预算：

| 配置 | 默认值 | 用途 |
|---|---:|---|
| `CONTEXT_MAX_INPUT_TOKENS` | 6000 | 对话输入的保守总预算 |
| `CONTEXT_RECENT_TOKENS` | 2800 | 最近消息滑动窗口 |
| `CONTEXT_SUMMARY_TOKENS` | 900 | 滚动摘要硬上限 |
| `CONTEXT_MESSAGE_TOKENS` | 900 | 单条历史消息硬上限 |
| `CONTEXT_HISTORY_MESSAGE_LIMIT` | 100 | Redis 最多保留的原始消息条数 |

本地模型配置为 8192 上下文。6000 的输入预算为系统提示、RAG 证据、工具结果和输出预留空间。由于没有强耦合某一个模型 tokenizer，系统采用对中英文偏保守的 token 估算；生产环境可按实际模型 tokenizer 替换估算函数。

### 超限处理顺序

1. 单条消息先按 900 token 截断，保留头部与尾部并插入可见截断标记。
2. 从最新消息向前填充 2800-token 窗口，优先保留最新对话。
3. 离开窗口的旧消息压缩进滚动摘要，提取服务实体和最近关键片段。
4. 摘要自身超过 900 token 时再次压缩。
5. `current_service` 与 `current_topic` 独立结构化保存，不会因摘要改写而丢失。
6. ContextProjector 对 Ops facts、Knowledge evidence 和 Supervisor 输入再次限量，防止 Specialist 结果重新撑爆上下文。
7. Context Resolver 在路由前补全“它、这个、刚才、继续”等省略指代，但保留原始 query 用于审计。

### 结构化记忆与可靠执行

- `SessionMemory` 是会话级、体积有界的结构化状态，不保存模型思维过程。
- 用户最新纠正覆盖较早的服务、环境和时间范围。
- Redis 状态过期后，可从 MySQL 中最近的用户消息确定性重建关键实体。
- 前端为每个逻辑用户分别保存活动 session，刷新后恢复；显式“新会话”不会重新打开旧记录。
- 前端每轮生成 `request_id`，服务端对重复请求返回同一结果，避免重试产生重复消息。
- 同一 session 使用 Redis 分布式锁串行执行，防止多标签页并发写乱上下文。

每个回答返回 `context_info`，前端显示估算 token、窗口消息数和摘要数量。Redis 状态还保存 `context_fingerprint`，用于诊断上下文是否发生变化。

### 当前摘要策略的选择

滚动摘要目前采用确定性压缩，不额外调用模型。这样即使本地模型离线，也不会让会话状态停止更新，同时避免为了摘要持续消耗云端额度。它保留事实的能力不如模型摘要，因此关键实体使用结构化字段单独保存。后续可以增加 LOCAL 模型摘要器，但必须继续保留硬预算和确定性降级。

## 2. RAG 知识库生命周期

### 新增

前端“知识库”页可上传 `.md`、`.txt`、`.pdf`、`.docx`，单文件最大 20 MB。后端流程：

```text
校验文件 → 提取文本 → 分块 → 生成 embedding
→ MySQL 写文档/块元数据 → Qdrant upsert → INDEXED → 刷新 BM25
```

接口：`POST /api/v1/documents/ingest`。可选字段：`title`、`source_uri`。

### 更新与幂等

- 相同 checksum：跳过重复索引。
- 相同 `source_uri`、内容变化：更新原文档并把 `version + 1`。
- 显式选择文档更新：`PUT /api/v1/documents/{document_id}`。
- 更新时先 upsert 新向量并提交新的块元数据，成功后再移除旧向量，避免“先删旧知识、后续失败”造成空窗。
- MySQL 为 `source_uri` 增加前缀索引，保证同源查找可扩展。

前端显示版本、状态、chunk 数，并提供“更新”按钮。新增的完整接口包括：

- `GET /api/v1/documents`
- `GET /api/v1/documents/{id}`（含 chunk 预览）
- `POST /api/v1/documents/ingest`
- `PUT /api/v1/documents/{id}`

当前没有提供物理删除按钮：删除会同时影响 MySQL、Qdrant 和引用审计，应该先设计软删除与恢复机制，再开放给用户。

检索融合后还会执行最低相关性过滤：只有 BM25 存在实际词项命中，或 dense score 达到配置阈值的 chunk 才能进入生成阶段。知识库正文始终按不可信数据处理，其中要求覆盖系统规则、泄露秘密或调用工具的文字不会获得指令权限。

## 3. 用户与会话隔离

### 已实现语义

- `user_id`：逻辑用户标识。
- `session_id`：单次对话线程，UUID。
- 一个用户可拥有多个 session；每个 session 有独立消息、摘要、服务实体、主题和上下文指纹。
- API 在继续会话前查询 `agent_session.user_id`。用户尝试读取或继续其他用户的 session 时返回 HTTP 403。
- Redis 过期后，会从 MySQL 恢复最近历史消息，因此不会立即丢失会话连续性。
- 前端提供当前用户、切换用户、历史会话列表和会话恢复。

接口：

- `GET /api/v1/sessions?user_id=...`
- `GET /api/v1/sessions/{id}?user_id=...`
- `PATCH /api/v1/sessions/{id}`（重命名）

### 安全边界

当前 `user_id` 由本地浏览器提供，只能实现数据逻辑隔离，不等于身份认证。任何知道 user_id 的客户端都可冒充该用户。生产环境应由可信登录系统签发 JWT/session cookie，从 token 的 subject 获取 user_id，不能继续信任请求体或 query string，并应增加 RBAC、租户 ID 和审计事件。

## 4. 验证结果（2026-10-06）

- 自动测试 42 项通过，覆盖窗口与摘要、Prompt 上下文、结构化记忆、路由、工具答案、模型降级、幂等和会话锁释放。
- 实测 3600 个中文内容字符的长请求被安全截断，最新用户消息仍保留。
- 同一用户成功创建并列出两个独立 session。
- 另一用户读取或继续这些 session 均返回 403。
- 新增上下文工程知识文档成功；显式更新后版本由 v1 升到 v2，状态为 `INDEXED`，Qdrant 与 MySQL 检索链路正常。
- 会话评测：记忆召回、刷新恢复、逻辑用户隔离均为 100%（2 个多轮场景）。
- Agent 评测：Intent Accuracy、Tool Success Rate、Answer Keyword Accuracy 均为 100%（6 个场景）。
- 检索评测：Dense/Hybrid Recall@3 与 Recall@5 为 100%，MRR 为 0.9375（8 个场景）。

这些数据仅代表仓库自带的小型本地评测集，不应外推为生产流量效果。生产上线前仍需接入可信身份系统、tenant/RBAC、知识库 ACL、更多对抗样本和压力测试。
