# DevPilot：企业研发知识库与运维协同 Agent 平台

这是一个面向 **AI Agent / 大模型应用开发日常实习** 的本地完整项目，目标不是“跑通一个聊天 Demo”，而是把后端工程、RAG、Agent、Tool、MCP、缓存、数据库和评测串成一套可讲清楚、可量化、可部署的系统。

当前版本已升级为 V2 Manager–Specialist 多 Agent / 多模型架构，详见 [多 Agent 架构、隐私与测试说明](docs/MULTI_AGENT_V2.md)。

上下文窗口、滚动摘要、知识库更新和多用户多会话设计见 [上下文、RAG 与会话设计](docs/CONTEXT_RAG_SESSION_DESIGN.md)。

从业务背景、整体架构、请求流程、RAG、上下文、可靠性到高频问答的完整复习材料见 [项目学习与面试指南](docs/INTERVIEW_STUDY_GUIDE.md)。
面试前快速复习可直接查看 [面试速查表](docs/INTERVIEW_CHEATSHEET.md)。

当前会话链路还包含结构化 SessionMemory、指代补全、按会话串行执行和 request_id 幂等去重；
RAG 证据按不可信输入处理，并使用实际检索 chunk 生成引用。前端可直接查看本会话提取出的服务、环境、时间范围、用户事实和当前目标。

当前版本还包含数据库用户、Bearer 登录、租户隔离与知识库文档级 ACL。缓存键包含租户和用户身份，避免把私有知识答案复用给其他成员。

## 你会真正完成什么

用户可以询问：

- “订单服务怎么部署？”
- “user/login 接口密码错误的错误码是什么？”
- “order-service 最近 7 天有几次部署失败？”
- “现在有哪些 P1/P2 未解决故障？”
- “结合最近一次失败发布和部署 SOP 给我排查建议。”

系统会根据问题类型选择不同执行链路：

```text
User
  |
  v
FastAPI Gateway
  |-- Redis: Session / Cache / Rate Limit
  |
  v
LangGraph Agent
  |
  +--> RAG --------> Dense(Qdrant) + BM25 ----> RRF ----> optional Rerank
  |
  +--> MySQL Tool --> service / deployment / incident / ticket
  |
  +--> MCP Server --> standardized read-only ops tools
  |
  v
LLM (OpenAI-compatible API)
  |
  +--> 开发阶段：Qwen3-4B-Instruct-2507 via vLLM
  +--> 后续：你的 1.07B Instruct/SFT 模型
```

## 本项目覆盖的面试技术点

- FastAPI：REST API、Pydantic、异常处理、SSE 事件流
- MySQL：表设计、PK/FK、索引、JOIN/GROUP BY、只读 Tool
- Redis：Session、Cache、Rate Limit、临时 Trace 状态
- RAG：Chunk、Embedding、Qdrant、BM25、Hybrid Search、RRF、Rerank、Citation
- Agent：LangGraph Router、Knowledge/Database/Mixed 分流、有界工作流
- Tool Calling：参数化只读业务 Tool，不让 LLM 任意执行 SQL
- MCP：官方 Python SDK v2，暴露 service/deployment/incident/ticket 工具
- vLLM：WSL2 下本地 OpenAI-compatible LLM 服务
- Evaluation：Recall@K、MRR、Intent Accuracy、Tool Success Rate、Citation Hit、P50/P95 Latency

## 目录

```text
app/                 FastAPI + Agent + RAG + Tool
sql/                 MySQL schema / seed
scripts/             一键部署、启动、评测脚本
data/sample_docs/    示例企业文档
data/eval/           检索/Agent测试集
wsl/                 WSL2 + vLLM脚本
docs/                架构、学习路线、面试提纲
```

## 推荐部署方式（Windows 11 + RTX 4090）

- Windows Conda `agentdev`：FastAPI、LangGraph、RAG、MCP Client/Server
- Docker Desktop：MySQL、Redis、Qdrant
- WSL2 Ubuntu：vLLM + Qwen3-4B-Instruct-2507
- RTX 4090 24GB：本地 LLM 推理

> **不要**把本项目依赖安装进你的 `bilingual1b` 训练环境。

## 最快启动

### 第 1 次：基础环境

```bat
00_PRECHECK_WIN11.cmd
01_ONE_CLICK_SETUP_WIN11.cmd
```

这一步会：

1. 检查 Conda、Docker、WSL、NVIDIA；
2. 创建 `agentdev` Conda 环境；
3. 安装 Python 依赖；
4. 启动 MySQL / Redis / Qdrant；
5. MySQL 首次启动时自动执行建表和 Seed SQL；
6. 创建 `.env`。

安装脚本也会执行认证/ACL 迁移并创建演示租户。首次登录账号为 `admin` 或 `engineer`，密码由 `.env` 中的 `AUTH_ADMIN_PASSWORD`、`AUTH_ENGINEER_PASSWORD` 控制；部署到生产前必须更换默认密码和 `AUTH_SECRET_KEY`。

### 第 2 次：安装本地 LLM（一次性）

以 PowerShell 打开：

```powershell
powershell -ExecutionPolicy Bypass -File wsl\01_SETUP_VLLM_WSL2.ps1
```

如果 WSL2/Ubuntu 尚未安装，脚本会提示先完成 Windows 组件安装/重启。完成后再次执行即可。

### 平时一键启动

```bat
02_ONE_CLICK_START_WIN11.cmd
```

它会启动：

- Docker 基础设施
- WSL2 vLLM（如果已安装）
- FastAPI（新 CMD 窗口）

Swagger：

```text
http://127.0.0.1:8001/docs
```

Web 控制台：

```text
http://127.0.0.1:8001/
```

控制台包含运行总览、Agent 智能协同、发布记录、故障与工单、知识库上传五个页面，直接由 FastAPI 托管，无需单独安装 Node.js。

Qdrant Dashboard：

```text
http://127.0.0.1:6333/dashboard
```

### 导入样例文档

```bat
05_INGEST_SAMPLE_DOCS_WIN11.cmd
```

### 冒烟测试

```bat
06_SMOKE_TEST_WIN11.cmd
```

### 评测

```bat
07_EVAL_RETRIEVAL_WIN11.cmd
08_EVAL_AGENT_WIN11.cmd
13_EVAL_CONVERSATION_WIN11.cmd
14_EVAL_AGENT_AB_WIN11.cmd
15_BUILD_ENTERPRISE_KB_WIN11.cmd
16_EVAL_SECURITY_WIN11.cmd
```

`14` 会在同一批问题上对比 `single` 与 `multi`，并明确输出是否观察到质量增益；`16` 覆盖未认证访问、伪造 Token、跨用户会话、私有文档 ACL、无答案、提示注入、秘密提取和破坏性命令。

## 无 vLLM 时也能先学基础设施

`.env` 默认 `LLM_MODE=mock`，所以 MySQL / Redis / Qdrant / RAG 基础链路可以先跑通。
安装 vLLM 后把 `.env` 改为：

```env
LLM_MODE=openai_compatible
```

即可切换到本地模型。

## 项目阶段建议

1. **先理解 MySQL 表**，自己在 DataGrip 写查询；
2. **再理解 FastAPI** 的请求、响应、异常；
3. 学 Redis Session / Cache / Rate Limit；
4. 学 Dense Retrieval；
5. 加 BM25 + RRF；
6. 再开 Reranker；
7. 学 LangGraph Router 和 Tool；
8. 学 MCP；
9. 部署 vLLM；
10. 最后做 Evaluation 和性能实验。

## 简历指标不要预编

最终只写真实结果，例如：

```text
Dense-only Recall@5             XX%
Hybrid Recall@5                 XX%
Hybrid + Rerank Recall@5        XX%
Intent Accuracy                 XX%
Tool Success Rate               XX%
Citation Hit Rate               XX%
P95 Latency (cache off/on)      XX ms -> XX ms
```

这些数字由 `07/08` 评测脚本实际产生后再写。
