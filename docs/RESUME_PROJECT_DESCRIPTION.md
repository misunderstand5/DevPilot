# DevPilot 最新简历内容（2026-10）

## 推荐放入简历的版本

### DevPilot——企业级研发运维多 Agent Copilot

**技术栈：** `FastAPI / LangGraph / MySQL / Redis / Qdrant / vLLM / Qwen / Hybrid RAG / MCP / JWT / RBAC / Docker`

**项目描述：** 面向研发运维场景构建证据驱动的对话式 Copilot，将部署规范、故障 Runbook 等静态知识，与服务状态、发布、事故、工单和 GitHub Commit 等动态事实统一到一个工作入口，帮助工程师连续完成“查知识—查现状—联合诊断—生成处理方案”，并通过权限和证据约束降低大模型事实幻觉。

**核心职责与成果：**

- 设计 Direct、Knowledge、Ops、Mixed 四类语义路由，以及 Knowledge、Ops、Diagnosis、Supervisor 专业 Agent 工作流；简单请求走快速路径，复杂问题按证据需求进入有界多 Agent 协作。
- 构建 Dense + BM25 + RRF 混合检索链路，完成文档解析、切块、向量化、版本更新、相关性过滤、Qdrant 原生过滤和 chunk 级引用，并支持 Markdown、TXT、PDF、DOCX 企业资料管理。
- 将服务状态、发布、事故和工单封装为四个参数化只读工具，禁止模型直接生成 SQL；通过 GitHub 官方 MCP Server 将发布版本与 Commit、变更文件及代码链接关联。
- 实现“滑动窗口 + 结构化 LLM 滚动摘要 + SessionMemory + Context Projector”的上下文工程，并以 MySQL Snapshot 恢复会话、Qdrant 按 `tenant_id + user_id` 隔离跨会话长期记忆。
- 建设 `end_user / developer / tenant_admin / system_admin` 四级 RBAC，叠加 Service/Repository Scope 与文档 ACL；权限同时在 API 和 Agent 工具调用层校验，系统管理员不默认继承租户内容访问权。
- 实现 request_id 幂等、Redis 会话锁、模型隐私路由、超时降级、Evidence Quality Gate、健康检查和 Windows 一键部署；当前 **75 项自动化测试通过**。

**项目亮点：**

- 使用 Google Cloud Online Boutique `v0.10.7` 构建可复现的微服务参考案例，完成 `发布记录 → GitHub Commit → RAG Runbook → 多 Agent 诊断` 的完整证据链。
- 建设 240 条、12 类困难评测集；首批 12 条在线 A/B 中，多 Agent 严格通过率由 **66.67% 提升至 75.00%**，P50 由 **6264 ms 降至 5019 ms**。
- RAG 小型基准集 Recall@5 达到 **100%**、MRR 为 **0.9375**；明确标注样本规模，不将实验结果包装成生产 SLA。

## 空间有限时的压缩版

### DevPilot——企业级研发运维多 Agent Copilot

`FastAPI / LangGraph / MySQL / Redis / Qdrant / vLLM / RAG / MCP / RBAC / Docker`

- 构建面向研发运维的证据驱动 Copilot，以四类语义路由和 Knowledge/Ops/Diagnosis/Supervisor 多 Agent 协同完成知识查询、实时事实查询和联合诊断。
- 实现 Dense+BM25+RRF 混合检索、参数化只读 Ops 工具及 GitHub MCP 代码证据链，禁止模型生成 SQL，回答支持来源引用与证据质量检查。
- 设计滑动窗口、结构化滚动摘要、Session Snapshot 与用户级长期记忆；实现四级 RBAC、资源 Scope、文档 ACL、幂等和会话锁。
- 75 项自动化测试通过；240 条困难评测集首批 A/B 中，多 Agent 严格通过率由 66.67% 提升至 75.00%。

## 一句话项目介绍

> DevPilot 不是单纯把企业文档接入大模型，而是面向研发运维的证据驱动型 Copilot：RAG 回答“规范上应该怎么做”，只读业务工具回答“系统实际发生了什么”，GitHub MCP 回答“对应代码改了什么”，再由有界多 Agent 工作流联合诊断，并通过 RBAC 和证据质量门保证结果可追溯、权限可控制。

## 面试时不能夸大的内容

- Online Boutique 是公开参考案例，不是真实生产流量和遥测。
- 240 条是困难评测集总规模，当前在线 A/B 实际运行的是首批 12 条。
- 系统已有应用级 RBAC，但还未接入企业 SSO、MFA、SCIM 和集中式策略引擎。
- 当前复杂路径是固定有界图，不是能够无限自主规划的通用 Agent。
- 尚未接入真实 Prometheus、Kubernetes 和 OpenTelemetry，因此不能声称已经完成真实生产根因定位。

## 投递不同岗位时的侧重点

- **AI Agent / 大模型应用岗：** 突出语义路由、多 Agent 职责隔离、Context Projector、模型网关、Evidence Quality Gate 和单/多 Agent A/B。
- **RAG / 知识库岗：** 突出文档解析、版本管理、Dense+BM25+RRF、相关性阈值、Qdrant 原生过滤、Citation 和无答案处理。
- **后端 / 平台工程岗：** 突出 FastAPI 异步接口、MySQL/Redis/Qdrant 分工、幂等、会话锁、四级 RBAC、资源 Scope、健康检查和 Docker 部署。
- **SRE / 研发效能岗：** 突出知识与运行事实分离、参数化只读工具、GitHub Commit 归因、故障诊断工作流、审计和可观测性接入设计。
