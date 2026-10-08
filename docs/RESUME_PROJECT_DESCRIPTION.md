# DevPilot 简历项目描述与面试表达

## 简历推荐版

**DevPilot——企业级研发运维多 Agent Copilot**  
`FastAPI / LangGraph / MySQL / Redis / Qdrant / vLLM / Qwen / RAG / BM25 / RRF / MCP / JWT / ACL / Docker`

**项目描述：** 面向研发运维场景构建证据驱动的对话式 Copilot，将部署规范、故障 Runbook 等静态知识与服务状态、发布、事故、工单及 GitHub Commit 等动态事实统一到一个工作入口，帮助工程师连续完成“查知识—查现状—联合诊断—生成处理方案”。

- 设计 Direct、Knowledge、Ops、Mixed 语义路由及 Knowledge、Ops、Diagnosis、Supervisor 多 Agent 工作流，按问题证据需求动态选择快速路径或协同诊断路径。
- 构建 Dense + BM25 + RRF 混合检索，支持文档切块、向量化、版本更新、来源追踪、ACL 过滤和答案引用，并以 Google Cloud Online Boutique `v0.10.7` 建立可复现的微服务参考案例。
- 将服务状态、发布、事故和工单封装为参数化只读工具，禁止模型生成 SQL；通过 JWT、租户隔离、资源 ACL、请求幂等和工具审计约束数据访问。
- 实现“滑动窗口 + LLM 滚动摘要 + Context Projector”的会话上下文工程，以及基于 Qdrant、按租户和用户过滤的跨会话长期记忆。
- 本地部署 GitHub 官方 MCP Server，采用服务端只读模式、`repos` 工具集和 `get_commit` 客户端白名单，将发布记录中的版本与 Commit 关联为可追踪代码证据。
- 增加 Evidence Quality Gate，确定性检查知识引用、Ops 事实和代码来源；实现四级 RBAC、服务/仓库资源范围与文档 ACL 组合授权，现有 **75 项自动化测试全部通过**。

## 一句话介绍

> DevPilot 不是普通的企业知识库聊天机器人，而是面向研发运维的证据驱动型 Copilot：RAG 回答“规范上应该怎么做”，只读业务工具回答“系统实际发生了什么”，GitHub MCP 回答“对应代码改了什么”，再由多 Agent 联合诊断并通过证据质量门阻止无依据结论。

## 面试展开版

项目主要解决研发排障中的信息割裂：规范存在文档中，生产事实存在发布、事故和工单系统中，代码变化又在 GitHub。传统 RAG 只能回答文档知识，无法证明当前运行状态；单纯 Tool Calling 又缺少规范约束。因此系统先通过语义路由区分 Direct、Knowledge、Ops 和 Mixed，再决定调用 RAG、内部只读工具或外部 MCP。

Knowledge 路径使用 Dense、BM25 和 RRF 组合召回，并在检索前执行租户和文档 ACL。Ops 路径只开放参数化只读查询，不允许模型直接接触数据库。复杂问题由 Diagnosis 对知识与事实进行关联，再由 Supervisor 输出最终答案。涉及版本和代码归因时，系统从发布记录定位用户指定版本对应的 Commit，然后通过本地 GitHub MCP 获取提交说明、变更文件和链接。

为了避免“Agent 看起来会回答，但没有可靠证据”，响应前增加确定性 Evidence Quality Gate：知识问题必须有 Citation，运行事实必须来自内部工具，代码归因必须有成功的外部证据。证据不足时保留回答但标记 `insufficient`，前端直接展示评分。

## 可量化结果与边界

- 75 项自动化测试通过，并完成真实 API RBAC 冒烟验证。
- 首批 12 条困难 A/B：多 Agent 严格通过率由 66.67% 提升到 75.00%。
- Online Boutique 真实参考案例：固定 `v0.10.7`，RAG 成功召回，Ops 参考发布可读取。
- GitHub MCP：账号鉴权成功，`get_commit` 实际返回 `5b608cb` 的提交信息与变更文件。
- Mixed 端到端：`recent_deployments + get_commit + rag_search` 全部成功，Evidence Quality 评分 1.0。
- 公开参考案例不是生产遥测；项目尚未连接真实 Prometheus/Kubernetes/Trace，因此不会声称可以提供真实生产 P95/P99。

## 高频面试问题

### 为什么需要多 Agent？

不是为了增加角色数量，而是隔离证据职责：Knowledge 只能处理文档，Ops 只能获取参数化事实，Diagnosis 负责关联假设，Supervisor 负责最终表达。简单问题走单 Agent 快速路径，只有 Mixed 或高风险问题进入完整协作链路。

### MCP 与普通函数调用有什么区别？

内部 MySQL 工具与应用同进程、同权限域，Python 函数调用延迟更低。GitHub 属于独立外部系统，使用 MCP 能统一工具发现、输入 Schema、传输和权限约束。项目没有为了使用 MCP 而把所有内部函数都网络化。

### 为什么现在没有使用 A2A？

A2A 面向独立 Agent 服务之间的身份、能力发现和任务协作。当前专业 Agent 属于同一应用和同一 LangGraph，使用 A2A 只会增加网络、鉴权和一致性成本。只有未来跨团队或跨系统部署独立 Agent 时才值得引入。

### 如何降低幻觉？

通过语义路由、RAG 引用、参数化只读工具、GitHub 代码证据、租户 ACL、无答案阈值和 Evidence Quality Gate 共同约束。模型负责综合与表达，不能替代事实来源。

### 下一步如何升级？

优先接入 Prometheus/Kubernetes/OpenTelemetry 的只读工具，补齐指标、Pod 和 Trace 证据；生产写操作必须增加 Human-in-the-loop 审批、持久化 checkpoint、幂等执行和补偿机制。之后再根据复杂规划评测结果决定是否加入预算受限的 Planner/Critic。
