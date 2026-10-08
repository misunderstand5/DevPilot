SET NAMES utf8mb4;
USE devpilot;

INSERT INTO service(name,owner_team,repo_url,environment,status,description) VALUES
('order-service','trade-platform','https://git.example.local/trade/order-service','prod','UP','订单核心服务'),
('user-service','account-platform','https://git.example.local/account/user-service','prod','UP','用户与认证服务'),
('payment-service','trade-platform','https://git.example.local/trade/payment-service','prod','DEGRADED','支付服务')
ON DUPLICATE KEY UPDATE owner_team=VALUES(owner_team), status=VALUES(status),
description=VALUES(description), repo_url=VALUES(repo_url), environment=VALUES(environment);

INSERT INTO deployment(service_id,version,environment,status,started_at,finished_at,operator_name,commit_sha,notes)
SELECT id,'v2.3.1','prod','SUCCESS',NOW()-INTERVAL 3 DAY,NOW()-INTERVAL 3 DAY+INTERVAL 8 MINUTE,'zhangsan','a1b2c3d4','常规发布' FROM service WHERE name='order-service';
INSERT INTO deployment(service_id,version,environment,status,started_at,finished_at,operator_name,commit_sha,notes)
SELECT id,'v2.3.2','prod','FAILED',NOW()-INTERVAL 1 DAY,NOW()-INTERVAL 1 DAY+INTERVAL 5 MINUTE,'lisi','e5f6a7b8','健康检查失败' FROM service WHERE name='order-service';
INSERT INTO deployment(service_id,version,environment,status,started_at,finished_at,operator_name,commit_sha,notes)
SELECT id,'v1.8.0','prod','SUCCESS',NOW()-INTERVAL 6 DAY,NOW()-INTERVAL 6 DAY+INTERVAL 7 MINUTE,'wangwu','11223344','常规发布' FROM service WHERE name='payment-service';

INSERT INTO incident(service_id,severity,title,status,started_at,root_cause,resolution)
SELECT id,'P1','支付回调延迟升高','OPEN',NOW()-INTERVAL 2 HOUR,'上游接口延迟，待进一步确认',NULL FROM service WHERE name='payment-service';
INSERT INTO incident(service_id,severity,title,status,started_at,resolved_at,root_cause,resolution)
SELECT id,'P2','订单健康检查异常','RESOLVED',NOW()-INTERVAL 1 DAY,NOW()-INTERVAL 23 HOUR,'错误配置导致探针失败','回滚配置并重新发布' FROM service WHERE name='order-service';

INSERT INTO ticket(service_id,title,description,status,priority,assignee)
SELECT id,'排查支付回调延迟','检查上游接口与线程池指标','IN_PROGRESS','P1','wangwu' FROM service WHERE name='payment-service';
INSERT INTO ticket(service_id,title,description,status,priority,assignee)
SELECT id,'补充订单发布监控','增加健康检查和错误率告警','OPEN','P2','lisi' FROM service WHERE name='order-service';
