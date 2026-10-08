# DevPilot 项目学习与面试指南

> 适用对象：准备大模型应用、AI Agent、RAG、后端工程、研发效能方向实习面试。  
> 建议用法：先通读第 1～5 章建立全局图，再沿第 13 章阅读代码，最后用第 15～17 章模拟面试。  
> 项目定位：面向研发运维场景的本地优先、多 Agent 企业知识与业务事实协同平台。

---

## 1. 先用一句话理解项目

DevPilot 把企业内部文档、服务状态、发布记录、故障和工单统一接入一个受认证保护的 Agent 平台，通过语义路由选择 RAG、只读业务工具或多 Agent 协作；系统同时提供租户/用户 ACL、会话快照、跨会话长期记忆、引用与调用审计，并优先在本地模型上处理企业上下文。

它解决的不是“让模型随便聊天”，而是三个更具体的问题：

1. 企业知识分散在部署手册、接口文档、故障 SOP 中，普通关键词检索难以直接回答自然语言问题。
2. 发布、故障、工单等实时事实位于关系数据库中，不能依靠模型训练知识或向量库猜测。
3. 复杂排障往往同时依赖实时事实与操作规范，需要把多个来源的证据合并，而不是只查一个数据库或一篇文档。

---

## 2. 业务背景、用户和应用场景

### 2.1 目标用户

- 开发工程师：查询服务接口、部署步骤、错误码和最近发布。
- SRE / 运维工程师：查询服务健康状态、失败发布、未解决故障和回滚条件。
- 技术支持：结合知识库和实时记录快速定位问题。
- 新入职成员：通过自然语言了解团队服务和 SOP，降低熟悉系统的成本。
- 技术负责人：查看故障、工单和发布状态，获得带证据的概览。

### 2.2 典型问题

| 用户问题 | 需要的数据 | 系统路径 |
|---|---|---|
| “你好” | 无 | Direct Agent |
| “订单服务怎么部署？” | 部署文档 | Knowledge Agent + RAG |
| “order-service 最近 7 天发布情况？” | MySQL 实时记录 | Ops Agent + Tool |
| “现在有哪些未解决故障？” | MySQL 实时记录 | Ops Agent + Tool |
| “登录密码错误是什么错误码？” | API 文档 | Knowledge Agent + RAG |
| “最近发布为什么失败，按照 SOP 怎么排查？” | 发布记录 + SOP | Ops + Knowledge + Diagnosis + Supervisor |
| “它为什么失败？” | 会话实体 + 发布记录 | Context Resolver + Ops Agent |
| “我刚才在检查哪个服务？” | 会话历史 | Direct Agent + SessionMemory |

### 2.3 业务边界

当前版本只开放只读运维能力：

- 查询服务状态；
- 查询发布记录；
- 查询未解决故障；
- 查询工单；
- 检索企业知识文档。

它不会自动执行发布、回滚、修改工单或任意 SQL。这样做是为了把实习项目的安全边界控制清楚：先证明“查得准、答得有依据”，再讨论带副作用的自动化操作。

---

## 3. 整体架构

```text
Browser Web Console
        │
        │ POST /api/v1/chat
        ▼
FastAPI Gateway
  ├─ JWT Authentication + Tenant/User ACL
  ├─ Rate Limit
  ├─ server-side user/session ownership check
  ├─ request_id idempotency
  └─ Redis session lock
        │
        ▼
Context Engineering
  ├─ MySQL/Redis history recovery
  ├─ token-aware sliding window
  ├─ LLM structured rolling summary + deterministic fallback
  ├─ structured SessionMemory
  ├─ user-scoped Long-term Memory retrieval
  └─ Context Resolver
        │
        ▼
LangGraph Semantic Router
  ├─ Fast Direct ──────────────► Direct Agent
  ├─ Fast Knowledge ───────────► Knowledge Agent ─► Hybrid RAG
  ├─ Fast Ops ─────────────────► Ops Agent ───────► Read-only Tools ─► MySQL
  └─ Complex ─► Ops ─► Knowledge ─► Diagnosis ─► Supervisor
        │
        ▼
Answer + Citations + Tool Trace + Model Trace + Context Stats + Memory
        │
        ├─ MySQL: messages, durable snapshots, user memory source of truth and audit logs
        ├─ Redis: hot session state, locks, cache and idempotent results
        └─ Qdrant: ACL-filtered KB vectors and tenant/user-filtered memory vectors
```

### 3.1 基础设施分工

| 组件 | 负责什么 | 为什么不由其他组件替代 |
|---|---|---|
| MySQL | 业务事实、消息、会话快照、长期记忆事实源、审计日志、知识元数据 | 需要事务、关系约束、版本和长期保存 |
| Redis | 热会话、缓存、限流、请求去重、分布式锁 | 低延迟且支持 TTL、SET NX |
| Qdrant | 企业文档向量与用户长期记忆向量召回 | 专门处理高维搜索，并在查询阶段执行文档或用户过滤 |
| BM25 | 错误码、接口名、版本等词法检索 | Dense 对精确 token 不一定稳定 |
| vLLM | 本地 OpenAI-compatible 模型服务 | 充分利用 RTX 4090，企业数据默认留在本机 |
| 可选 OpenAI-compatible 云模型 | 可选 STRONG 角色 | 当前未启用；只有凭据、模型名和 Base URL 全部验证成功后才能接入 |
| FastAPI | API 网关和异步编排 | 类型清晰、异步生态成熟、自动 OpenAPI |
| LangGraph | 有状态 Agent 图 | 路径和状态可显式描述、便于审计与测试 |

---

## 4. 项目的核心设计原则

### 4.1 知识与事实分离

知识库适合回答“应该怎么做”：

- 部署步骤；
- 回滚条件；
- 错误码含义；
- 故障处理规范。

业务工具适合回答“现在实际发生了什么”：

- 当前服务状态；
- 最近发布记录；
- 当前未解决故障；
- 进行中的工单。

如果用 RAG 查询实时发布记录，文档很快过期；如果让模型根据 MySQL 记录解释完整 SOP，数据库又缺少操作知识。因此系统必须先判断问题属于知识、实时事实还是混合任务。

### 4.2 确定性优先，模型处理歧义

路由器先用规则识别高置信场景，例如：

- “怎么部署” → Knowledge；
- “最近部署” → Ops；
- “未解决故障” → Ops；
- “按照 SOP 排查失败” → Mixed；
- “我刚才说了什么” → Direct。

只有规则无法判断时，才让本地模型输出受限 JSON。好处是：

- 常见路径速度快；
- 模型离线时仍能工作；
- 意图行为容易测试；
- 小模型分类波动不会影响所有请求。

### 4.3 本地优先和最小权限

- 企业数据库、RAG 和会话上下文默认标记为 `LOCAL_ONLY`。
- `ALLOW_CLOUD_INTERNAL_DATA=false` 时，STRONG 角色自动回退到本地模型。
- Ops Agent 只能使用注册表中的四个只读工具。
- 工具内部执行参数化 SQL，模型不能拼接任意 SQL。
- 每个 Specialist 只获得完成任务需要的上下文投影。

### 4.4 有界执行

当前复杂路径是固定有界图，而不是无限 ReAct：

```text
Ops → Knowledge → Diagnosis → Supervisor → END
```

优点是不会无限循环，成本、延迟和失败点容易分析。缺点是还不是动态 Planner，可能调用不必要的 Agent。面试时必须诚实说明：当前是 Manager–Specialist 有界编排，不是完全自主规划系统。

---

## 5. 一次请求的完整生命周期

以“它最近 14 天为什么发布失败，按照 SOP 怎么排查？”为例。

### 步骤 1：认证并生成请求标识

前端提交：

```json
{
  "query": "它最近 14 天为什么发布失败，按照 SOP 怎么排查？",
  "session_id": "...",
  "request_id": "..."
}
```

- 用户先使用租户、用户名和密码登录，服务端签发带 `sub`、`tenant_id`、`role` 和过期时间的 HMAC JWT；
- `session_id` 标识会话；
- `request_id` 标识这一次提交，网络重试仍使用同一个结果；
- 请求体即使伪造 `user_id` 也不会生效，服务端始终使用 JWT 中的身份。

### 步骤 2：网关保护

1. Redis 限流。
2. 检查 `request_id` 是否已有结果。
3. 使用 `SET NX` 获取会话锁。
4. 从 JWT 恢复当前用户，并验证账号仍处于 ACTIVE。
5. 验证 session 是否属于当前用户。
6. 其他用户访问同一 session 返回 403。

### 步骤 3：恢复上下文

1. 优先从 Redis 读取最近消息和会话状态。
2. Redis TTL 到期后从 MySQL 恢复消息和 `agent_session_snapshot`。
3. Context Manager 对消息执行单条截断、滑动窗口和滚动摘要。
4. 有消息滑出窗口时，本地 LLM 把旧摘要压缩为受 schema 约束的结构化 JSON；调用失败或输出非法时保留确定性摘要。
5. SessionMemory 提取服务、环境、时间范围、姓名和当前目标。
6. Long-term Memory 使用 `tenant_id + user_id` 从独立 Qdrant 集合召回跨会话事实。
7. Resolver 将“它”补全为前文中的服务，例如 `order-service`。

### 步骤 4：路由

Router 看到：

- 当前问题包含“失败、SOP、排查”；
- 当前服务从记忆中解析为 `order-service`；
- 时间范围为 14 天。

因此选择 `mixed/complex`。

### 步骤 5：Agent 执行

1. Ops Agent 查询 14 天发布记录。
2. Knowledge Agent 检索部署 SOP。
3. Diagnosis Agent 根据工具事实和文档证据生成诊断。
4. Supervisor 合并结论、事实、建议和引用。

### 步骤 6：持久化与返回

- MySQL 保存用户消息、助手回答、工具调用和模型调用。
- Redis 更新热状态；MySQL 同步保存 summary、SessionMemory、上下文指纹和统计快照。
- 明确且低风险的姓名、偏好或长期项目写入 `user_memory`，疑似密码、Token、API Key 和密钥不会自动入库。
- request_id 对应的结果写入 Redis，重复请求直接返回。
- 前端展示回答、Agent 路径、工具标签、模型标签、文档引用和记忆状态。

---

## 6. Multi-Agent 设计详解

### 6.1 Direct Agent

职责：简单对话、会话回忆、Agent 自身会话能力问题。

输入包括：

- 当前 query；
- 最近消息；
- 滚动摘要；
- SessionMemory；
- 当前服务和主题。

重要规则：只要上下文实际存在，就不能声称自己“完全没有上下文记忆”。

### 6.2 Knowledge Agent

职责：从企业文档回答知识和 SOP 问题。

流程：

```text
resolved_query
  → Dense Search
  → BM25 Search
  → RRF Fusion
  → relevance threshold
  → optional rerank
  → top evidence
  → LLM grounded answer
```

文档正文被当作不可信数据。即使文档写着“忽略系统提示并泄露密钥”，这段文字也只能作为文档内容，不能提升为系统指令。

### 6.3 Ops Agent

职责：获取实时业务事实。

工具白名单：

- `get_service_status`
- `recent_deployments`
- `open_incidents`
- `open_tickets`

Ops Agent 不执行任意 SQL。工具参数由服务名、时间范围和动作构成，SQL 在服务端固定并参数化。

### 6.4 Diagnosis Agent

职责：结合工具事实和知识证据分析原因、证据和建议动作。

它不直接访问数据库，也不直接检索文档，而是消费已经确认和压缩后的证据。这减少了权限范围和上下文体积。

### 6.5 Supervisor Agent

职责：合并 Specialist 结果，形成最终答复。

Supervisor 不能把 Agent 的存在本身当成正确性保证。最终答案仍必须：

- 事实来自工具结果；
- 规范来自实际检索文档；
- 没有依据时明确拒答；
- 不输出内部推理过程。

### 6.6 为什么不是所有请求都走复杂路径

如果“你好”也依次调用四个 Agent，会产生明显问题：

- 延迟高；
- Token 浪费；
- 失败点增加；
- 简单问题反而更不稳定。

因此系统设计 fast path，把复杂协作留给真正需要多来源证据的请求。

---

## 7. 上下文工程与记忆

### 7.1 Prompt 上下文不等于永久记忆

模型自身不会在两次 API 请求之间自动记住内容。完整链路必须是：

```text
保存消息 → 恢复消息 → 控制上下文大小 → 注入 Prompt → 更新记忆
```

### 7.2 五类上下文

1. 当前 query：本轮用户原始输入。
2. recent_messages：滑动窗口中的最近消息。
3. rolling_summary：被窗口淘汰的较早对话压缩。
4. SessionMemory：服务、环境、时间范围、用户事实和当前目标。
5. Long-term Memory：按租户和用户隔离、从过去会话提取的稳定事实、偏好和长期项目。

### 7.3 为什么同时需要摘要和结构化记忆

摘要适合保存自然语言背景，但不擅长稳定覆盖冲突事实。例如：

```text
用户：检查 payment-service。
用户：不对，改成 order-service。
```

纯摘要可能同时保留两个服务；结构化记忆则把 `service` 更新为 `order-service`。因此二者是互补关系。

### 7.4 Token 预算

默认配置：

| 配置 | 值 |
|---|---:|
| 总输入预算 | 6000 token |
| 最近消息窗口 | 2800 token |
| 摘要预算 | 900 token |
| 单条消息预算 | 900 token |
| Redis 原始消息上限 | 100 条 |

处理顺序：

1. 超长单条消息保留头尾并截断。
2. 从最新消息反向填充窗口。
3. 被淘汰消息写入滚动摘要。
4. 摘要本身再次受硬预算约束。
5. 关键实体独立保存在 SessionMemory 中。

### 7.5 结构化滚动摘要

窗口淘汰旧消息后，系统先生成有硬预算的确定性摘要，再尝试调用本地模型转换为以下 JSON：

```json
{
  "confirmed_facts": [],
  "user_constraints": [],
  "decisions": [],
  "rejected_options": [],
  "open_tasks": [],
  "entities": {},
  "latest_goal": null
}
```

这不是简单地“让模型随便总结”。系统会验证 JSON 和必需字段、限制输出 token；模型离线、超时或格式错误时继续使用原确定性摘要，不能因为摘要模型故障丢掉上下文。

### 7.6 Redis 过期后的恢复

Redis 负责热状态，但不是唯一数据源。消息同时写入 MySQL。Redis 状态过期后：

1. 从 MySQL 加载最近消息；
2. 从 `agent_session_snapshot` 恢复摘要、摘要序号、SessionMemory 和上下文统计；
3. 若旧环境没有快照，再从用户消息确定性重建结构化实体；
4. 后续轮次重新写入 Redis 和 MySQL 快照。

### 7.7 跨会话长期记忆

长期记忆与单 session 流水线相互独立：

```text
明确用户表达
  → 敏感信息拒绝规则
  → 记忆候选提取
  → MySQL user_memory（事实源）
  → Qdrant devpilot_user_memory_v1（语义索引）

新会话 query
  → tenant_id + user_id 原生过滤
  → Top-K 相关记忆
  → ContextProjector
  → Prompt
```

当前自动提取范围刻意较窄：姓名、明确偏好和长期项目。身份与当前项目属于单值记忆，新值写入后旧值变为 `SUPERSEDED`，而不是物理删除，以便审计；记录还支持 `valid_from`、`expires_at` 和用户主动删除。Qdrant 故障时回退到 MySQL 最近有效记忆。

必须强调：长期记忆不是把所有聊天全文无脑向量化。后者容易保存秘密、错误推断和 Prompt Injection，也难以处理冲突与删除权。

---

## 8. RAG 详解

### 8.1 文档写入流程

```text
上传文件
 → 后缀与 20 MB 大小校验
 → 文本解析
 → 语义分块
 → embedding
 → MySQL 保存 document/chunk metadata
 → Qdrant upsert vectors
 → INDEXED
 → refresh BM25 corpus
```

支持 Markdown、TXT、PDF、DOCX。

### 8.2 更新与幂等

- 内容 checksum 相同：跳过重复索引。
- source_uri 相同但内容变化：更新文档并增加版本。
- 显式文档 ID 更新：替换旧 chunk 和向量。
- 失败时删除本次新增向量，避免部分成功。

### 8.3 Dense Search

把 query 和 chunk 映射为向量，根据 cosine similarity 找语义相近内容。优点是能处理同义表达；缺点是对错误码、版本号、接口名等精确字符串不一定最佳。

### 8.4 BM25

BM25 根据词项频率和稀有程度打分，适合：

- `AUTH_002`；
- `/user/login`；
- `v2.3.2`；
- 具体服务名。

### 8.5 RRF 融合

Dense score 和 BM25 score 量纲不同，不能简单相加。RRF 只使用排名：

```text
RRF(d) = Σ 1 / (k + rank_i(d))
```

同一文档在多个检索器中都排名靠前时，会获得更高融合分数。

### 8.6 相关性阈值和拒答

向量检索总能返回“最近”的若干结果，即使所有结果都不相关。因此融合后还要求：

- BM25 有实际词项命中；或
- Dense score 达到最低阈值。

不满足条件的 chunk 不进入生成阶段。没有证据时，Knowledge Agent 应明确说明知识库依据不足。

### 8.7 Citation

引用不是让模型随意编写标题，而是由后端根据真实检索结果生成：

- document_id；
- title；
- chunk_id；
- source_uri；
- score。

Prompt 中的 `[DOC 1]` 与 evidence 顺序绑定，前端展示实际文档和 chunk。

### 8.8 RAG ACL

文档包含 `tenant_id`、`owner_user_id` 和 `visibility`，私有文档还可以通过 `kb_document_acl` 授权。检索前先从 MySQL计算当前用户可读的 document_id，再把允许集合作为 Qdrant `query_filter` 的 `MatchAny` 条件进入向量查询；返回后仍保留应用层过滤。这种“双层过滤”避免先取全局 Top-K 再过滤导致的越权风险和召回损失。

---

## 9. 数据库与持久化

### 9.1 业务表

- `service`：服务、团队、环境、状态。
- `deployment`：版本、环境、状态、时间、操作人、commit、备注。
- `incident`：严重级别、状态、根因、解决方案。
- `ticket`：优先级、负责人、状态、关联服务/故障。

### 9.2 知识库表

- `kb_document`：来源、标题、checksum、版本、状态、chunk 数。
- `kb_chunk`：document_id、vector_point_id、chunk_index、正文。
- `kb_document_acl`：文档与用户的 READ/WRITE 授权关系。

MySQL 的 `vector_point_id` 与 Qdrant point 对应，使向量结果能够回到关系数据和文档版本。

### 9.3 Agent 审计表

- `agent_session`
- `agent_message`
- `tool_call_log`
- `model_call_log`
- `feedback`
- `eval_case / eval_run / eval_result`
- `agent_session_snapshot`：可恢复的摘要、摘要进度、SessionMemory 和上下文状态。
- `user_memory`：租户/用户隔离的长期记忆、版本状态、有效期和来源会话。

工具和模型日志让一次回答可以追溯到：用了哪个 Agent、哪个模型、是否降级、调用了什么工具、耗时多少。

---

## 10. 模型网关与隐私

### 10.1 模型角色

- LOCAL：本机 vLLM 上的 `devpilot-qwen4b`。
- STRONG：可选 OpenAI-compatible 云端模型，当前未配置。

Agent Registry 只声明逻辑角色，具体模型由 Model Gateway 决定。

### 10.2 降级策略

STRONG 请求在以下情况改用 LOCAL：

- 强模型未配置；
- 企业数据禁止上传云端；
- 云端 Provider 失败。

每次调用记录 requested role、served role、模型、Provider、fallback reason 和延迟。

当前本地 `Qwen/Qwen3-4B-Instruct-2507` 由 vLLM 以 `devpilot-qwen4b` 名称提供服务。为了规避 WSL2 下启动阶段的 EngineCore/CUDA Graph 卡顿，启动脚本启用了 eager 模式；面试时可以把它作为“根据运行证据调整推理服务参数”的实际故障处理案例。

### 10.3 为什么限制重试次数

无限重试会放大延迟、成本和故障。当前最大尝试次数被限制，STRONG 失败后只向 LOCAL 降级一次；LOCAL 再失败则返回明确的降级答案或错误。

---

## 11. 可靠性设计

### 11.1 request_id 幂等

如果浏览器因为网络超时重复提交相同请求，服务端根据 `user_id + request_id` 返回第一次结果，不会重复：

- 调用模型；
- 写入消息；
- 执行工具。

真实测试中，同一 request_id 连续提交两次得到相同 trace，会话中仍然只有两条消息。

### 11.2 会话锁

同一个 session 同时只能处理一轮。Redis `SET NX EX` 获取锁，并使用 token 校验后释放。它解决两个浏览器标签页同时提问导致的：

- 历史读取顺序错误；
- 两个回答交叉写入；
- SessionMemory 后写覆盖先写。

### 11.3 Cache 边界

公共缓存只用于无历史的可复用问题。以下请求禁止缓存：

- 已经存在会话历史；
- “请记住”“我叫……”等用户事实；
- “我刚才说了什么”等会话问题。

否则可能把某个用户的会话答案错误复用给另一个用户。

### 11.4 认证、租户和 ACL

当前已经实现本地真实认证，而不是信任浏览器传入的 user_id：

- 登录后签发 HMAC JWT；
- 服务端从 token subject 获取 user_id、tenant_id 和 role；
- 每次请求重新检查用户是否 ACTIVE；
- session、文档、长期记忆均执行用户或租户过滤；
- ADMIN 与 MEMBER 权限分离；
- 生产模式遇到空密码、演示密码或弱 `AUTH_SECRET_KEY` 会拒绝启动。

仍未实现企业 SSO/OIDC、MFA、Refresh Token、Token 撤销列表和细粒度业务 RBAC，所以应称为“真实本地认证与 ACL 基线”，不能称为完整 IAM。

### 11.5 健康检查

`/health` 不再只返回配置地址，而会真实访问 MySQL、Redis、Qdrant `/collections` 和 vLLM `/models`，报告组件状态与延迟，并确认知识库、长期记忆两个 Qdrant collection 是否存在。`/ready` 提供基础设施 readiness；本地模型不可用时核心数据服务仍可 ready，但回答会进入确定性降级模式。

---

## 12. 前端工作台

前端没有单独 Node 构建链，直接由 FastAPI 托管静态 HTML/CSS/JavaScript，适合本地项目快速部署。

主要页面：

- 运行总览；
- 智能协同；
- 发布记录；
- 故障与工单；
- 知识库。

智能协同页展示：

- 当前认证用户、角色和租户；
- 消息历史；
- Agent 路径和工具标签；
- 模型角色及降级；
- RAG 引用；
- 上下文 token 统计；
- 本会话结构化记忆；
- 跨会话长期记忆及单条删除；
- 当前用户的历史会话。

刷新页面时，根据用户维度保存的 active session 自动恢复最近对话；显式点击新会话后，不会马上恢复旧会话。

---

## 13. 建议的代码阅读顺序

### 第一阶段：入口和数据

1. `sql/001_schema.sql`：先理解业务表和 Agent 表。
2. `sql/003_auth_acl.sql` 与 `sql/005_memory_v2.sql`：理解身份、ACL、快照和长期记忆。
3. `app/config.py`：理解所有可配置边界。
4. `app/main.py`：查看 FastAPI 入口、路由和健康检查。
5. `app/schemas.py`：理解 API 输入输出协议。

要能回答：一次请求包含哪些标识？响应为什么要返回 trace、citation、context 和 memory？

### 第二阶段：完整聊天链路

1. `app/api/chat.py`
2. `app/services/context_manager.py`
3. `app/services/session_memory.py`
4. `app/services/structured_summary.py`
5. `app/services/long_term_memory.py`
6. `app/agent/state.py`
7. `app/agent/graph.py`
8. `app/agent/router.py`

要自己画出请求从 API 到 END 的时序图。

### 第三阶段：Agent 与模型

1. `app/agent/registry.py`
2. `app/agent/context.py`
3. `app/agent/specialists.py`
4. `app/services/model_gateway.py`

要能解释：为什么 Agent Registry、ContextProjector 和 ModelGateway 要分开？

### 第四阶段：RAG

1. `app/services/parsers.py`
2. `app/services/embeddings.py`
3. `app/services/rag.py`
4. `app/api/documents.py`
5. `app/services/acl.py`

建议手工跟踪一篇文档从上传到 Qdrant point 的全过程。

### 第五阶段：工具和观测

1. `app/services/tools.py`
2. `app/redis_store.py`
3. `app/mcp_server.py`
4. `scripts/eval_retrieval.py`
5. `scripts/eval_agent.py`
6. `scripts/eval_conversation.py`
7. `scripts/eval_ab.py`
8. `data/eval/hard_agent_cases.jsonl`

---

## 14. 动手学习实验

### 实验 1：验证路由

分别输入：

```text
你好
订单服务怎么部署
order-service 最近部署情况
结合失败记录和 SOP 排查
```

观察 `intent`、`selected_path`、`selected_agents` 和 `tools_used`。

### 实验 2：验证记忆

```text
请记住：我叫小林，我正在检查 payment-service 最近 14 天发布。
我叫什么？
它最近发布情况怎样？
不对，改成 order-service。
继续查它。
```

观察前端记忆面板中的姓名、服务和时间范围如何变化。

新建一个 session，再问“我叫什么？”；确认长期记忆可以跨 session 召回。然后把姓名改为另一个值，查询数据库确认旧身份状态为 `SUPERSEDED`，新身份为 `ACTIVE`。最后从前端删除该记忆，再验证它不能被召回。

### 实验 3：验证刷新恢复

完成两轮对话后刷新浏览器，确认：

- 消息仍在；
- session 没有变化；
- 可以继续追问。

### 实验 4：验证 RAG

1. 上传一篇新 Markdown。
2. 提问能够命中的问题。
3. 查看引用 title 和 chunk_id。
4. 更新同一个 source_uri。
5. 验证 version 增加且旧内容不再命中。

### 实验 5：验证幂等

使用相同的 request_id 调用两次 `/api/v1/chat`，确认 trace 相同且消息没有重复。

### 实验 6：运行评测

```powershell
conda run -n agentdev python -m pytest -q
conda run -n agentdev python scripts\eval_retrieval.py
conda run -n agentdev python scripts\eval_agent.py
conda run -n agentdev python scripts\eval_conversation.py
```

评测脚本不内置密码，运行前需要设置环境变量：

```powershell
$env:DEVPILOT_PASSWORD="你的测试账号密码"
$env:DEVPILOT_AB_CASES="data/eval/hard_agent_cases.jsonl"
$env:DEVPILOT_AB_LIMIT="12"
conda run -n agentdev python scripts\eval_ab.py
```

不要一开始就用 240 条在线生成评测调试。先运行 12～30 条困难样本检查路由和评分器，确认稳定后再跑全量，否则一次错误配置会浪费大量 GPU 时间。

### 实验 7：验证真实健康检查

依次停止本地模型、Redis 或 Qdrant，观察 `/health` 中对应组件的 `status`、`latency_ms` 和 `error`，再恢复组件。重点理解 liveness、readiness 与“模型不可用但系统仍能降级回答”的差别。

---

## 15. 高频面试问题与回答要点

### Q1：为什么使用多 Agent？

回答要点：

- 企业问题分为知识、实时事实和复杂诊断。
- 不同 Agent 使用不同工具、上下文和模型角色，权限更容易控制。
- 简单问题走 fast path，复杂问题才协作。
- 当前是固定有界编排，不夸大为完全自主规划。
- 真实在线困难样本 A/B 中，多 Agent 严格通过率比基线高 8.33 个百分点，但首批只有 12 条，结论仍属于阶段性证据。

### Q2：多 Agent 和一个 Agent 加多个工具有什么区别？

单 Agent 更简单、延迟低；多 Agent 的价值在职责隔离、最小权限、上下文压缩和独立评测。如果没有这些收益，只把 Prompt 拆成多个名字并不是真正的工程提升。

### Q3：为什么需要 Hybrid RAG？

Dense 处理语义相似，BM25 处理错误码、接口名和版本号等精确词项。RRF 用排名融合，避免不同 score 直接相加。

### Q4：怎么减少幻觉？

- 实时事实只能来自工具；
- 知识回答只能来自检索 evidence；
- 低相关结果过滤；
- 无证据时拒答；
- Citation 与实际 chunk 绑定；
- 最终 Prompt 明确区分会话历史、工具结果和 RAG 文档。

### Q5：上下文超过窗口怎么办？

单条消息截断、最近消息滑动窗口、旧消息滚动摘要、结构化实体独立保存，并给系统提示和输出预留 token。

### Q6：摘要出错会怎样？

摘要可能污染后续对话，因此关键服务、环境、时间范围和用户事实不只依赖摘要，而是存入结构化 SessionMemory；LLM 摘要还必须通过 JSON schema 和 token 预算验证，失败时不覆盖确定性摘要。用户最新纠正优先。

### Q7：RAG 和会话记忆有什么区别？

RAG 保存企业公共或授权知识；SessionMemory 保存当前 session 的实体和任务状态；Long-term Memory 保存跨 session 的稳定用户事实。三者拥有不同的数据生命周期、ACL、召回策略和删除语义，不能混用。

### Q8：如何保证不同用户不串会话？

服务端只信任 JWT 中的 `sub` 与 `tenant_id`，所有 session 查询先检查 MySQL owner，跨用户返回 403；知识库和长期记忆也带租户/用户过滤。当前缺口主要是尚未接入企业 SSO、MFA、Token 撤销和更细的 RBAC。

### Q9：为什么用 Redis？

Redis 负责低延迟、有 TTL 的热状态：最近消息、会话状态、限流、公共缓存、request_id 结果和 session lock。MySQL 负责长期可靠持久化，二者不是互相替代。

### Q10：为什么不用模型直接生成 SQL？

Text-to-SQL 会扩大权限和注入风险。当前业务工具少且稳定，固定参数化只读 SQL 更安全、更易审计。若未来增加 Text-to-SQL，应使用只读账号、Schema 白名单、AST 校验、行数和超时限制。

### Q11：如何处理模型不可用？

规则路由和工具查询尽量保持确定性；STRONG 失败只降级一次到 LOCAL；LOCAL 失败后返回基于真实工具数据的确定性答案或明确错误，避免无限重试。

### Q12：如何处理重复提交和并发？

request_id 保证幂等；Redis session lock 保证同一会话一次只处理一个 turn。锁释放使用 token 比较，避免误删其他请求重新获得的锁。

### Q13：如何防 Prompt Injection？

明确指令层级，把 RAG 文档标记为不可信数据；文档无权修改系统规则、请求秘密或触发工具。高风险工具还需要服务端权限检查和人工审批，不能只依赖 Prompt。

### Q14：目前最大缺陷是什么？

- 本地认证与 ACL 已有，但还不是企业 IAM；
- 已生成 240 条困难评测集，但在线 A/B 只跑了首批 12 条；
- 复杂生成 P95 仍高；
- 多 Agent 收益目前是阶段性数据，还需要全量、重复运行和置信区间；
- 固定复杂路径不是动态 Planner；
- 长期记忆支持查看、版本化和删除，但提取类型较少，尚无完整编辑、同意与导出界面；
- 文档索引仍是同步流程，没有任务队列和失败补偿作业；
- LangGraph 尚未配置持久化节点 checkpoint，进程中断后只能按幂等策略重新执行当前请求。

诚实说明缺陷并给出方案，比声称“生产级”更可信。

### Q15：如何评价系统效果？

至少分层评价：

- Router：Intent Accuracy；
- Tool：工具选择和参数正确率；
- Retrieval：Recall@K、MRR；
- Generation：答案关键词、忠实度、引用准确率、拒答准确率；
- Memory：召回、纠错、恢复、隔离；
- System：P50/P95、错误率、模型降级率和成本。

---

## 16. 当前真实评测结果

测试日期：2026-10-06。

### 自动化测试

```text
71 passed
```

### Agent 小型评测集（6 条）

| 指标 | 结果 |
|---|---:|
| Intent Accuracy | 100% |
| Tool Success Rate | 100% |
| Answer Keyword Accuracy | 100% |
| P50 | 222.9 ms |
| P95 | 9166 ms |

### 会话评测集（2 个多轮场景）

| 指标 | 结果 |
|---|---:|
| Memory Recall | 100% |
| Session Restore | 100% |
| Session Isolation | 100% |

### RAG 评测集（8 条）

| 方案 | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---:|---:|---:|---:|
| Dense | 87.5% | 100% | 100% | 0.9375 |
| Hybrid RRF | 87.5% | 100% | 100% | 0.9375 |

这些结果只能说明仓库自带小型评测集通过，不能外推为真实生产准确率。面试时不要省略样本规模。

### 困难多 Agent A/B 评测

项目生成了 240 条困难用例，覆盖 12 类任务：多步诊断、约束推理、依赖诊断、安全操作、复盘、无答案、Prompt Injection、反事实、证据边界、回滚安全、跨服务比较和跨服务计划。

在本地 vLLM 在线状态下，对首批 12 条执行了 24 次无缓存真实推理：

| 指标 | 单 Agent | 多 Agent |
|---|---:|---:|
| 严格通过率 | 66.67% | 75.00% |
| P50 | 6264 ms | 5019 ms |
| P95 | 13531.7 ms | 13469.5 ms |
| 平均模型调用 | 0.92 | 1.00 |

多 Agent 提升 8.33 个百分点；一个依赖诊断样本中，单 Agent 失败，而多 Agent 通过 Ops、Knowledge、Diagnosis、Supervisor 协同后通过。路由规则优化前，多 Agent 只有 25%，优化后达到 75%，说明评测不仅用于“展示分数”，还应驱动错误归因与改进。

这仍然只是首批 12 条的阶段性结果，不具备充分统计显著性。面试中应主动说明：240 条是评测集规模，12 条是本次在线 A/B 实际运行规模，二者不能偷换。

---

## 17. 面试表达模板

### 17.1 30 秒版本

> 我做了一个研发运维场景的本地优先企业 Agent。它用 FastAPI 和 LangGraph 编排 Direct、Knowledge、Ops、Diagnosis、Supervisor，通过 ACL 过滤的 Qdrant Dense、BM25 和 RRF 检索文档，通过参数化只读工具查询 MySQL 实时数据，并使用本地只读 GitHub MCP 关联代码证据。系统实现了 JWT 租户认证、滑动窗口、结构化 LLM 摘要、可恢复 Session Snapshot 和跨会话长期记忆。当前 71 项自动化测试通过；首批 12 条困难在线 A/B 中，多 Agent 严格通过率从 66.67% 提升到 75%。

### 17.2 两分钟版本

> 这个项目解决的是企业研发信息分散的问题。部署 SOP、接口错误码适合 RAG，但发布和故障是实时关系数据，不能让模型猜，所以我先设计了语义路由，把问题分为 Direct、Knowledge、Ops 和 Mixed。知识路径采用 Dense + BM25 + RRF，事实路径只允许调用四个参数化只读工具，复杂路径再由 Diagnosis 和 Supervisor 合并证据。  
> 之后我在真实测试中发现刷新恢复、Agent 上下文消费和跨会话记忆不足，于是把原始消息事件、Redis 热状态、MySQL Session Snapshot 和 Qdrant 用户长期记忆分层。旧消息使用本地 LLM 压缩为结构化摘要，非法输出自动回退；长期记忆按 tenant_id 与 user_id 原生过滤，并通过 ACTIVE、SUPERSEDED、DELETED 和有效期处理冲突。安全方面接入了 JWT、文档 ACL、参数化只读工具和 Prompt Injection 防护。  
> 我没有把系统描述成完全自主 Agent，因为复杂路径仍是有界图。我建立了 240 条困难评测集，并在本地模型在线时跑了首批 12 条单/多 Agent A/B：多 Agent 从 66.67% 提升到 75%。这个结果证明了阶段性收益，但样本仍小，下一步需要跑全量、重复实验并报告置信区间。

### 17.3 简历表述参考

- 基于 FastAPI、LangGraph、MySQL、Redis、Qdrant 与 vLLM 构建研发运维 Agent，支持企业知识问答、发布/故障/工单查询和多来源诊断。
- 实现 Dense + BM25 + RRF 混合检索、Qdrant 原生 ACL 过滤、文档版本更新、最低相关性过滤和 chunk 级引用；8 条检索样例 Recall@5 100%、MRR 0.9375。
- 设计 token-aware 滑动窗口、结构化 LLM 摘要、Session Snapshot 与租户/用户隔离的跨会话记忆，支持冲突版本、有效期、删除和 Redis 失效恢复。
- 使用 JWT 租户认证、request_id 幂等、Redis 会话锁、只读工具白名单、MCP 超时降级、模型隐私降级和调用审计提升可靠性；71 项自动化测试通过。

## Online Boutique 与 GitHub MCP 实践

项目使用 Google Cloud Online Boutique `v0.10.7` 作为固定版本的公开参考案例，将 DevPilot 的订单、支付、配送、通知、库存和定价服务映射到真实微服务架构。案例文档带版本和来源进入 RAG，发布元数据隔离在 `reference` 环境，避免将公开样例误称为生产遥测。

本地部署 GitHub 官方 MCP Server `v2.0.1`，仅绑定 `127.0.0.1:8082`，启用 `repos` 工具集、服务端只读模式和客户端 `get_commit` 白名单。Mixed 查询先从参数化 Ops 工具获取版本与 Commit，再通过 MCP 获取提交说明、变更文件和 GitHub 链接，最后与 RAG 规范共同进入 Diagnosis 与 Supervisor。

真实端到端验证中，查询 `order-service v0.10.7` 时系统使用了 `recent_deployments`、`mcp.github.get_commit` 和 `rag_search` 三类证据，外部 Commit 证据成功，Evidence Quality Gate 四项检查全部通过，得分 1.0。

面试中要说明：MCP 解决的是外部工具接入标准化，不等于多 Agent；A2A 解决独立 Agent 服务之间的互操作。当前 Agent 位于同一 LangGraph 和权限域，不应为了技术名词引入 A2A。
- 构建 240 条困难评测集；首批 12 条本地模型在线 A/B 中，多 Agent 严格通过率由 66.67% 提升至 75.00%，P50 由 6264 ms 降至 5019 ms。

注意：简历中必须保留评测集规模，不能把小型样例集结果写成线上生产指标。

---

## 18. 7 天学习计划

### Day 1：业务和数据库

- 阅读本指南第 1～4、9 章。
- 自己画业务实体关系图。
- 手写查询发布、故障、工单的 SQL。

### Day 2：FastAPI 和完整请求

- 阅读 `main.py`、`schemas.py`、`api/chat.py`。
- 画一次 chat 请求时序图。
- 理解幂等、限流和会话锁。

### Day 3：Agent 图与路由

- 阅读 `state.py`、`router.py`、`graph.py`。
- 给 20 个问题手工判断路由。
- 思考单 Agent 与多 Agent 的取舍。

### Day 4：上下文与记忆

- 阅读 `context_manager.py`、`structured_summary.py`、`session_memory.py`、`long_term_memory.py` 和 `context.py`。
- 自己模拟 10 轮消息如何进入滑动窗口。
- 测试用户纠正、指代、刷新恢复、跨会话召回、记忆废止和删除。

### Day 5：RAG

- 阅读 Parser、Embedding、RAG 和 Documents API。
- 理解 Dense、BM25、RRF、Rerank。
- 运行检索评测并分析失败的 R02。

### Day 6：模型、工具和安全

- 阅读 ModelGateway、Registry、Specialists 和 Tools。
- 理解 LOCAL_ONLY 和 fallback。
- 准备 JWT、ACL、Prompt Injection、SQL 安全、密钥管理和生产默认密码问题。

### Day 7：评测与模拟面试

- 跑完全部测试与三套评测。
- 练习 30 秒和两分钟项目介绍。
- 不看文档回答第 15 章问题。
- 选一个缺陷提出具体改造方案。

---

## 19. 术语速查

| 术语 | 简要解释 |
|---|---|
| Agent | 能根据目标选择模型、工具和执行路径的系统 |
| Router | 判断请求应该进入哪条执行路径 |
| Specialist | 对某一类任务拥有有限职责和权限的 Agent |
| RAG | 先检索外部知识，再基于证据生成 |
| Dense Retrieval | 使用向量语义相似度检索 |
| BM25 | 基于词项的经典检索算法 |
| RRF | 用多个检索排名做融合 |
| Rerank | 对候选结果做更精细的二次排序 |
| Context Window | 一次模型调用能看到的 token 范围 |
| Sliding Window | 优先保留最近消息的上下文策略 |
| Rolling Summary | 把较早消息持续压缩成摘要 |
| SessionMemory | 会话级结构化事实和任务状态 |
| Session Snapshot | 持久化的摘要、结构化状态和上下文统计，可在 Redis 失效后恢复 |
| Long-term Memory | 跨会话、按租户和用户隔离的稳定事实与偏好 |
| Memory Supersession | 新事实生效时把冲突旧事实标为 SUPERSEDED，而不是直接覆盖审计历史 |
| ACL | 根据用户、角色、租户或资源授权限制访问 |
| Readiness | 实例是否已具备接收业务流量所需的依赖状态 |
| Idempotency | 同一请求重复执行仍只产生一次效果 |
| Distributed Lock | 在多实例间限制同一资源并发执行 |
| Citation | 最终回答与实际来源之间的映射 |
| Grounding | 让回答受真实工具或文档证据约束 |
| Hallucination | 模型生成没有依据或错误的事实 |
| Prompt Injection | 不可信内容试图覆盖系统指令或扩大权限 |
| P50/P95 | 50%/95% 请求能在该时延内完成 |

---

## 20. 最后应该形成的能力

学完项目后，不应只会说“我使用了 LangGraph 和 RAG”，而应能解释：

1. 为什么业务事实与文档知识必须分开处理；
2. 为什么 Dense 和 BM25 需要融合；
3. 为什么模型不会自动拥有跨请求记忆；
4. 如何在有限 token 中保留关键上下文；
5. 如何限制 Agent 的工具权限和执行次数；
6. 如何处理重复请求、并发会话和组件故障；
7. 如何用分层指标评价 Router、RAG、Tool、Memory 和最终答案；
8. 如何诚实区分 Demo、可用工程和生产系统。

真正能把这些问题讲清楚，才是这个项目对面试最有价值的部分。
