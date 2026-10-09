# DevPilot 部署指南

## 运行拓扑

- Windows Conda：FastAPI、Agent、RAG、MCP Client/Server
- Docker Desktop：MySQL、Redis、Qdrant
- WSL2 Ubuntu：vLLM 与本地 Qwen 模型
- 浏览器：DevPilot Web 控制台

## 环境要求

- Windows 11、WSL2 Ubuntu
- Docker Desktop
- Miniconda 或 Anaconda
- NVIDIA GPU 与兼容驱动（本地 vLLM 模式需要）
- 建议 16 GB 以上内存；项目默认模型配置面向 RTX 4090 24 GB

## 配置

复制示例配置：

```bat
copy .env.example .env
```

必须设置：

```env
MYSQL_PASSWORD=<strong-password>
MYSQL_ROOT_PASSWORD=<different-strong-password>
AUTH_SECRET_KEY=<random-string-at-least-32-characters>
AUTH_ADMIN_PASSWORD=<admin-password>
AUTH_ENGINEER_PASSWORD=<engineer-password>
```

Windows 本地开发可直接运行 `02_ONE_CLICK_START_WIN11.cmd`：它会检测并启动 Docker Desktop，等待 Linux Engine 就绪，再通过 `scripts/ensure_local_env.py` 补齐缺失的随机本地凭据。生成的演示登录信息保存在 Git 已忽略的 `.devpilot-credentials.txt`。服务器和生产部署不要使用该自动生成流程，应通过 Secret Manager 或 CI/CD Secret 注入上述变量。

本地模型模式：

```env
LLM_MODE=openai_compatible
LOCAL_MODEL_BASE_URL=http://127.0.0.1:8000/v1
LOCAL_MODEL_API_KEY=EMPTY
LOCAL_MODEL_NAME=devpilot-qwen4b
ALLOW_CLOUD_INTERNAL_DATA=false
```

## 自动部署

首次执行：

```bat
00_PRECHECK_WIN11.cmd
01_ONE_CLICK_SETUP_WIN11.cmd
```

安装 vLLM：

```powershell
powershell -ExecutionPolicy Bypass -File wsl\01_SETUP_VLLM_WSL2.ps1
```

日常启动：

```bat
02_ONE_CLICK_START_WIN11.cmd
```

停止服务：

```bat
03_STOP_ALL_WIN11.cmd
```

## 验证

```bat
06_SMOKE_TEST_WIN11.cmd
```

也可以访问：

```text
GET http://127.0.0.1:8001/health
```

健康接口会实际检查 MySQL、Redis、Qdrant、必要 Collection 与本地模型，而不只是返回 Web 进程存活状态。

## 可选 GitHub MCP

DevPilot 只使用支持 Streamable HTTP 的外部 MCP Endpoint。内部 MySQL Tool 继续直接调用 Python，以避免不必要的网络开销。

```env
GITHUB_MCP_ENABLED=true
GITHUB_MCP_URL=<mcp-endpoint>
GITHUB_MCP_TOKEN=<read-only-token>
GITHUB_MCP_TOOL_ALLOWLIST=["get_commit"]
GITHUB_MCP_REPOSITORIES={"order-service":"owner/repository"}
```

安全要求：

1. Token 仅授予读取目标仓库所需的最小权限。
2. Endpoint 必须使用 HTTPS，生产环境不得关闭证书校验。
3. 允许调用的 Tool 必须同时存在于远端工具列表和本地白名单。
4. 不把 Token、完整工具异常或超长响应传入模型上下文。
5. MCP 不可用时继续使用内部事实与知识证据，最终答案必须声明证据缺失。

## 生产部署注意事项

1. 不要暴露 MySQL、Redis、Qdrant 和 vLLM 端口到公网。
2. 使用反向代理启用 HTTPS，并限制请求体大小与超时。
3. 使用 Secret Manager 或部署平台密钥管理，不要把 `.env` 烘焙进镜像。
4. 为数据库使用最小权限账号，定期备份 MySQL 与 Qdrant Volume。
5. 使用企业 IdP/OIDC 替代演示账号，并启用 Token 吊销与密钥轮换。
6. 保持 `ALLOW_CLOUD_INTERNAL_DATA=false`，除非完成明确的数据合规评估。
7. 在真实生产接入前扩展对抗评测、无答案评测和权限测试。
