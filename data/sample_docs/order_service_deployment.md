# Order Service 部署手册

## 服务信息

服务名：`order-service`
负责团队：trade-platform
默认生产环境：prod

## 发布前检查

1. 确认数据库 migration 已在 staging 验证。
2. 确认 Redis key 变更向后兼容。
3. 检查 `/actuator/health` 返回 `UP`。
4. 检查订单创建、取消、查询三个核心接口 smoke test。

## 生产部署

采用滚动发布。每批 25% 实例，观察 5 分钟后继续下一批。
若错误率超过 2% 或 P95 延迟超过 800ms，应立即停止发布。

## 回滚

若健康检查失败或核心接口异常：
1. 停止后续批次。
2. 回滚到上一稳定版本。
3. 保留失败版本日志。
4. 创建 P1/P2 incident 并关联 deployment id。
