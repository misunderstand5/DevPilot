# 外部 MCP 集成设计

本机官方 GitHub MCP Server 使用 Docker 运行在 `127.0.0.1:8082`，启用 `repos` 工具集和服务端只读模式。可执行以下脱敏检查验证 GitHub 身份和 `get_commit`：

```bat
conda run --no-capture-output -n agentdev python scripts\check_github_mcp.py
```

容器未启动时运行 `18_START_GITHUB_MCP_WIN11.cmd`。凭据保存在 Git 忽略的 `.env.local`，不得复制到 README、Compose 文件或提交记录。

## 设计目标

DevPilot 使用两类工具边界：

```text
内部高频事实：Ops Agent → Python Read-only Tool → MySQL
外部平台证据：Ops Agent → MCP Gateway → GitHub MCP
```

内部服务、发布、故障和工单与 DevPilot 同进程、同数据库，直接 Python 调用延迟更低，也便于传递 JWT/ACL 上下文。MCP 只用于独立外部系统，不为使用协议而增加无意义的网络跳转。

## 触发条件

只有查询包含以下证据需求时才触发 GitHub MCP：

- Commit 或提交记录
- Pull Request / PR
- 代码变更或“改了什么”
- Workflow、GitHub Actions 或 CI 失败

典型链路：

```text
“order-service 这次发布改了什么，为什么 CI 失败？”
  → Semantic Router: Mixed
  → Internal deployment Tool: version + commit_sha
  → GitHub MCP get_commit: message + files + URL
  → Knowledge RAG: deployment SOP
  → Diagnosis: 关联发布、代码和规范证据
  → Supervisor: 输出结论、证据缺口与处理建议
```

## 安全与可靠性

- 本地 `GITHUB_MCP_TOOL_ALLOWLIST` 与远端 `tools/list` 双重约束。
- 第一阶段仅开放 `get_commit`，不允许创建 Issue、合并 PR、触发 Workflow 等写操作。
- 每次调用具有超时、有限重试和最大结果长度。
- Token 仅进入 MCP HTTP Authorization Header，不进入 Prompt、日志或 API 响应。
- 调用成功或失败均进入现有工具审计链路。
- MCP 不可用不会导致整个 Agent 失败，系统会返回内部证据并声明外部证据缺失。

## 前后端数据

`GET /api/v1/integrations` 返回不含密钥的连接元数据：

```json
{
  "internal_tools": {
    "mode": "direct_python",
    "tools": ["service_status", "deployments", "incidents", "tickets"]
  },
  "external_mcp": [{
    "id": "github_mcp",
    "configured": false,
    "mode": "read_only",
    "allowed_tools": ["get_commit"]
  }]
}
```

聊天响应中的 `external_evidence` 提供来源、工具、状态、摘要、引用链接和延迟。前端将它与知识库 Citation 分开显示，避免把外部实时事实误认为 RAG 文档。

## 后续扩展

统一 Gateway 可以继续注册：

- Prometheus/Grafana MCP：延迟、错误率和发布前后指标
- Loki/OpenSearch MCP：时间范围内的日志聚合与 Trace ID
- Jira/Linear MCP：只读工单状态与负责人

外部写操作必须引入独立审批、幂等键、细粒度授权和人工确认，不能复用当前只读策略直接开放。
