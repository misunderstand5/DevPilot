SET NAMES utf8mb4;
USE devpilot;

-- Public reference data. The "reference" environment prevents this release
-- metadata from being confused with live production telemetry.
INSERT INTO service(name,owner_team,repo_url,environment,status,description) VALUES
('shipping-service','reference-commerce','https://github.com/GoogleCloudPlatform/microservices-demo','reference','UNKNOWN','映射到 Online Boutique shippingservice 的公开参考服务'),
('notification-service','reference-commerce','https://github.com/GoogleCloudPlatform/microservices-demo','reference','UNKNOWN','映射到 Online Boutique emailservice 的公开参考服务'),
('inventory-service','reference-commerce','https://github.com/GoogleCloudPlatform/microservices-demo','reference','UNKNOWN','映射到 Online Boutique productcatalogservice 的公开参考服务'),
('pricing-service','reference-commerce','https://github.com/GoogleCloudPlatform/microservices-demo','reference','UNKNOWN','映射到 Online Boutique currencyservice 的公开参考服务')
ON DUPLICATE KEY UPDATE repo_url=VALUES(repo_url);

UPDATE service
SET repo_url='https://github.com/GoogleCloudPlatform/microservices-demo'
WHERE name IN ('order-service','payment-service','shipping-service','notification-service','inventory-service','pricing-service');

INSERT INTO deployment(service_id,version,environment,status,started_at,finished_at,operator_name,commit_sha,notes)
SELECT s.id,'v0.10.7','reference','SUCCESS','2026-09-18 00:00:00','2026-09-18 00:00:00',
       'upstream-release','5b608cb','公开参考版本；不是 DevPilot 生产发布记录'
FROM service s
WHERE s.name='order-service'
  AND NOT EXISTS (
    SELECT 1 FROM deployment d
    WHERE d.service_id=s.id AND d.version='v0.10.7' AND d.environment='reference'
  );
