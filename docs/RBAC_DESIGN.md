# DevPilot RBAC 与资源授权设计

## 1. 为什么不是只用 ACL

ACL 适合回答“这个用户能不能访问这份具体文档”，但无法完整表达“开发者能否查看 Trace”“租户管理员能否分配服务范围”“系统管理员是否能读取租户会话”。DevPilot 因此采用三层授权：

1. **RBAC**：角色映射权限点，决定用户能执行什么动作。
2. **Resource Scope**：限制权限可作用的 Service 或 Repository。
3. **Document ACL**：在知识库读取和写入时继续约束具体文档。

授权判断全部发生在服务端。前端隐藏按钮只是可用性优化，不能代替鉴权；Prompt 也不参与授权决策。

## 2. 内置角色

| 角色 | 继承 | 主要能力 | 明确边界 |
| --- | --- | --- | --- |
| `end_user` | 无 | 自己的会话与长期记忆、知识读取、获授权的 Ops 和 GitHub MCP 只读调用 | 不能管理用户、知识、Agent 配置和系统设置 |
| `developer` | `end_user` | 自己的 Trace、评测和 Agent 应用配置、MCP 连通性测试 | 不能访问其他用户数据和租户管理能力 |
| `tenant_admin` | `developer` | 本租户用户、角色、知识库、ACL、Service/Repository Scope 与统计 | 不能跨租户，不能管理底层集群和平台全局配置 |
| `system_admin` | **不继承租户角色** | 平台生命周期、模型/MCP 服务、日志指标、集群资源与全局配置 | 默认不能读取租户会话、记忆、知识正文和业务工具结果 |

`system_admin` 的独立设计是刻意的：平台运维能力不等于业务数据访问权。如平台人员需要进入某租户，应通过显式、限时、可审计的租户角色授权，而不是隐式超级管理员绕过。

## 3. 关键权限点

- 用户域：`session.own.*`、`memory.own.*`、`agent.chat.use`
- 知识域：`kb.document.read/create/update/delete`、`kb.acl.manage`
- 事实域：`ops.service.read`、`ops.deployment.read`、`ops.incident.read`、`ops.ticket.read`
- 外部工具：`mcp.github.commit.read`、`mcp.integration.own.test`
- 租户管理：`tenant.user.*`、`tenant.role.assign`、`service.authorization.manage`、`repository.authorization.manage`
- 平台管理：`system.config.manage`、`model.provider.manage`、`mcp.server.manage`、`observability.*`、`cluster.*`

## 4. 请求授权链路

```text
JWT 只承载身份提示
  → current_user 从 MySQL 重新确认账号状态
  → 加载 rbac_user_role / rbac_role_permission / rbac_resource_scope
  → API 检查 permission
  → Ops/MCP Agent 再检查 permission + resource scope
  → 知识检索额外检查 tenant_id + document ACL
  → 记录角色和 Scope 变更审计
```

即使旧 Token 仍包含历史 `ADMIN/MEMBER` 字段，最终权限也以数据库中的 RBAC 状态为准。迁移期间仅在 RBAC 表缺失时使用 `ADMIN → tenant_admin`、`MEMBER → end_user` 的安全兼容映射。

## 5. 数据模型

- `rbac_role`：角色定义。
- `rbac_permission`：原子权限点。
- `rbac_role_permission`：角色到权限的映射，内置继承展开后写入。
- `rbac_user_role`：用户角色，可扩展到期时间。
- `rbac_resource_scope`：用户对 Service/Repository 的授权范围，支持精确资源和 `*`。
- `rbac_audit_log`：角色与范围变更审计元数据。

## 6. 运维与验证

```powershell
python scripts/migrate_rbac.py
pytest -q
python scripts/smoke_rbac.py
```

`migrate_rbac.py` 可重复执行；一键启动脚本会在 API 启动前自动运行它。在线冒烟测试验证租户管理员可以读取租户用户列表、开发者会被拒绝，同时开发者仍可访问已授权的 Dashboard 和知识库。

## 7. 后续生产增强

- 为角色和 Scope 增加 `expires_at` 管理界面及到期回收任务。
- 将 RBAC 审计接入 OpenTelemetry/SIEM，并对越权拒绝建立告警。
- 增加 Break-glass 临时访问流程，要求工单、审批、到期时间和完整审计。
- 对服务和仓库范围增加用户组授权，避免大租户逐用户维护。
