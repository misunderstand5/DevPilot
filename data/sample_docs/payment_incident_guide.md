# Payment Service 故障处置指南

## 支付回调延迟

当 `payment-service` 回调 P95 超过 1 秒时：

1. 检查上游支付渠道耗时和错误码分布。
2. 检查 HTTP 连接池、线程池活跃数和队列长度。
3. 检查数据库连接池与慢 SQL。
4. 若确认是上游抖动，应开启降级并延长异步回调重试窗口。
5. 若错误率超过 5%，创建 P1 incident 并通知 trade-platform。
