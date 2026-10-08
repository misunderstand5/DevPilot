# User Service API

## POST /api/v1/user/login

请求字段：

- `username`: string, required
- `password`: string, required
- `device_id`: string, optional

成功响应：

- `access_token`
- `refresh_token`
- `expires_in`

常见错误码：

- `AUTH_001`: 用户不存在
- `AUTH_002`: 密码错误
- `AUTH_003`: 账号锁定

连续 5 次密码错误会触发临时锁定。
