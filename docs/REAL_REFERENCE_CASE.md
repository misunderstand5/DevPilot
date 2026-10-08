# 真实参考案例：Online Boutique v0.10.7

DevPilot 使用 Google Cloud 官方公开项目 Online Boutique 作为可复现参考案例。它是一个包含 11 个微服务、gRPC、Kubernetes 配置和电商结算链路的云原生系统，适合验证“知识 → 运行事实 → 代码证据 → 联合诊断”。

## 为什么称为参考案例，而不是生产案例

- 架构和部署配置来自固定的官方 `v0.10.7`，具有真实来源。
- DevPilot 中的故障、发布和工单仍是本地演练数据，不能冒充 Google 的生产遥测。
- 数据通过 `reference` 环境和文档声明与 `prod` 事实区分。
- 所有映射都在 `data/reference_cases/online-boutique/manifest.json` 显式记录。

## 验证链路

1. Knowledge Agent 从固定版本架构与演练 Runbook 检索静态证据。
2. Ops Agent 通过参数化只读工具读取 DevPilot 本地发布与事故数据。
3. 涉及提交归因时，GitHub MCP 只读获取上游提交证据。
4. Diagnosis/Supervisor 合并证据。
5. Evidence Quality Gate 确认知识引用、Ops 工具和代码证据是否齐全。

## 准备数据

```bat
17_PREPARE_REFERENCE_CASE_WIN11.cmd
```

该命令校验固定来源、将两份案例知识写入 RAG，并添加隔离在 `reference` 环境中的发布记录。`sql/006_online_boutique_reference_case.sql` 保留为手工部署时的等价迁移。

GitHub MCP 的仓库映射应配置为：

```env
GITHUB_MCP_REPOSITORIES={"order-service":"GoogleCloudPlatform/microservices-demo","payment-service":"GoogleCloudPlatform/microservices-demo","shipping-service":"GoogleCloudPlatform/microservices-demo"}
```

## 验收问题

- “Online Boutique 的 order-service 对应哪个真实服务，它依赖哪些下游？”
- “order-service 刚发布后结算失败，请联合发布记录、参考架构和代码提交给出诊断。”
- “根据参考案例告诉我此刻 checkoutservice 的真实 P99。”

第三个问题专门验证证据边界：静态仓库无法提供此刻的真实 P99，系统必须拒绝猜测。

可运行以下确定性烟雾评测，验证 RAG 召回与 Ops 参考发布记录：

```bat
conda run --no-capture-output -n agentdev python scripts\eval_reference_case.py
```

后端启动后，可继续运行带 JWT 登录和真实模型生成的端到端验证：

```bat
conda run --no-capture-output -n agentdev python scripts\eval_live_reference_api.py
```

## Agent 技术结论

当前阶段不引入 A2A，也不增加无约束的 Reflection Agent。专业 Agent 都在同一进程、同一权限域和同一编排图内，A2A 会增加服务发现、身份传递和故障处理成本，却没有独立组织间通信需求。优先增加确定性 Evidence Quality Gate，更符合运维审计和成本控制要求。

当出现以下需求时再考虑升级：

- 跨团队、跨部署或跨公司的 Agent 需要独立身份与生命周期：引入 A2A。
- 需要执行生产变更：增加 Human-in-the-loop 审批节点和可恢复工作流。
- 任务持续数小时：增加持久化任务队列、checkpoint 和补偿机制。
- 证据质量门稳定后仍有复杂计划失败：再加入受预算限制的 Planner/Critic，而不是无限自反思。
