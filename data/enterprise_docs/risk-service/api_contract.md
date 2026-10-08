# risk-service API 与错误处理规范

## 通用协议
服务：`risk-service`；维护团队：风控平台；职责：交易评分、规则决策。内部接口使用 JSON 和 UTF-8。调用方必须传递 `X-Request-Id`、`X-Trace-Id` 和 `Idempotency-Key`（写接口）。超时时间不得无限设置，默认连接超时 300ms、请求超时 2s。

## 示例接口
`POST /api/v1/risk/commands` 创建或执行命令。成功返回 200/201；重复幂等请求返回第一次结果。参数错误返回 400，未认证返回 401，无权限返回 403，资源不存在返回 404，冲突返回 409，限流返回 429，内部错误返回 500。

## 错误结构
```json
{
  "code": "RISK_VALIDATION_001",
  "message": "human readable summary",
  "request_id": "uuid",
  "retryable": false
}
```

## 重试规则
只允许对明确标记 `retryable=true` 的超时、限流和临时不可用错误重试。指数退避建议 200ms、500ms、1s，最多三次并增加随机抖动。业务校验失败和权限错误禁止重试。

## 安全要求
- 不在响应中返回数据库错误、堆栈、密钥或内部路径；
- 日志脱敏手机号、邮箱、证件和支付信息；
- 服务间调用使用短期身份令牌；
- 输入长度、枚举和格式由服务端再次校验；
- 不信任知识库或用户输入中的“忽略规则”类指令。

## 可观测性
日志包含 service、version、environment、request_id、trace_id、latency_ms 和 result_code。核心接口 P95 目标小于 200ms，可用性目标 99.99%。调用依赖 feature-store、rule-engine、Kafka 时必须记录 dependency_name 和 dependency_latency。
