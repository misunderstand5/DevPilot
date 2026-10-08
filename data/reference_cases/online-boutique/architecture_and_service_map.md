# Online Boutique v0.10.7：架构与 DevPilot 服务映射

> 数据性质：公开参考案例，不是生产运行事实。所有结论固定到 `v0.10.7`，用于验证 DevPilot 的检索、引用、路由和证据边界。

## 来源

- 项目：GoogleCloudPlatform/microservices-demo
- 固定版本：v0.10.7（发布页短提交 `5b608cb`）
- 官方 README：https://github.com/GoogleCloudPlatform/microservices-demo/blob/v0.10.7/README.md
- Checkout Kubernetes 清单：https://github.com/GoogleCloudPlatform/microservices-demo/blob/v0.10.7/kubernetes-manifests/checkoutservice.yaml

## 业务架构

Online Boutique 是一个云原生电商参考应用。官方版本由 11 个使用不同语言实现、通过 gRPC 通信的微服务组成。用户流程包括浏览商品、加入购物车和结算。

DevPilot 为了复用现有运维数据模型，采用显式映射，而不是假装两边服务名完全一致：

| DevPilot 服务 | 上游真实服务 | 职责 |
|---|---|---|
| order-service | checkoutservice | 编排购物车、支付、配送和确认邮件 |
| payment-service | paymentservice | 模拟扣款并返回交易 ID |
| shipping-service | shippingservice | 估算运费并模拟配送 |
| notification-service | emailservice | 模拟发送订单确认邮件 |
| inventory-service | productcatalogservice | 商品列表、搜索和详情 |
| pricing-service | currencyservice | 使用汇率完成金额换算 |

## 可验证依赖

固定版本的 `checkoutservice` Kubernetes 清单声明了以下下游地址：

- productcatalogservice:3550
- shippingservice:50051
- paymentservice:50051
- emailservice:5000
- currencyservice:7000
- cartservice:7070

该清单同时提供 5050 端口的 gRPC readiness 与 liveness probe，并采用非 root、只读根文件系统、禁止提权和 drop ALL capabilities 的容器安全配置。

## 证据边界

本文可以回答版本架构、服务依赖和部署清单中的静态配置，不能证明某一时刻的 Pod、延迟、事故、发布结果或值班人。此类问题必须从 DevPilot 参数化 Ops 工具获得；没有实时数据时必须明确证据不足。
