# Online Boutique 结算链路故障演练 Runbook

> 本文是基于 Online Boutique v0.10.7 公开架构制作的 DevPilot 演练材料，不是上游项目官方生产 Runbook。

## 场景

结算请求在新版本发布后失败。目标是区分 checkoutservice 自身故障和 productcatalogservice、shippingservice、paymentservice、emailservice、currencyservice、cartservice 下游故障。

## 证据收集顺序

1. 从发布系统确认 order-service 对应版本、提交、开始时间和发布状态。
2. 检查 checkoutservice 的 gRPC readiness/liveness 以及 5050 端口是否可用。
3. 按请求 trace 检查六个下游调用，不能仅凭平均延迟判定根因。
4. 将异常开始时间与发布窗口对齐；时间相关性只能形成假设，不能直接证明因果。
5. 若问题涉及代码变更，通过只读 GitHub MCP 获取对应 commit，并保留来源链接。

## 止损与回滚门槛

- 只有新版本异常且上一稳定版本健康：暂停扩容发布，按审批流程回滚应用镜像。
- 所有版本同时异常：优先检查共享下游和集群网络，不进行无差别重启。
- 数据格式或接口可能不向后兼容：先验证兼容性，不直接删除字段或生产数据。
- 恢复后同时验证结算成功率、P95/P99、错误率、关键下游 trace，并持续观察 30 分钟。

## 人工审批边界

DevPilot 只生成证据和建议，不自动执行回滚、删除资源或修改数据。任何生产变更必须由授权人员确认目标、影响面、备份和回滚方案。
