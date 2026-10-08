# DevPilot V2 多 Agent / 多模型架构

## 目标与边界

V2 在现有 FastAPI、LangGraph、MySQL、Redis、Qdrant 与 vLLM 工程上增量升级，不重建项目。核心目标是把“一个路由器加一段通用回答”拆成可审计的 Manager–Specialist 协作，同时保持 `POST /api/v1/chat` 向后兼容。

## 执行架构

```text
Chat API
  └─ Semantic Router
      ├─ Fast Direct    → Direct Agent (LOCAL)
      ├─ Fast Knowledge → Knowledge Agent (LOCAL + RAG)
      ├─ Fast Ops       → Ops Agent (LOCAL + allowlisted tools)
      └─ Complex        → Ops → Knowledge → Diagnosis → Supervisor
                                      STRONG*       STRONG*

* 企业上下文默认 LOCAL_ONLY；未明确允许上传时自动由 STRONG 降级到 LOCAL，并记录原因。
```

语义路由优先使用确定性规则，明确区分“怎么部署”（知识流程）和“最近部署了什么”（实时事实）。只有无法判定的请求才调用本地模型做受限 JSON 分类。服务中文别名在路由层统一归一化。

## Agent Registry 与模型角色

| Agent | 职责 | 模型角色 | 可用工具 |
|---|---|---|---|
| `direct_agent` | 简单对话 | LOCAL | 无 |
| `knowledge_agent` | 企业知识、SOP、RAG | LOCAL | `rag_search` |
| `ops_agent` | 实时服务、发布、故障、工单 | LOCAL | 四个只读参数化工具 |
| `diagnosis_agent` | 多来源诊断 | STRONG | 无 |
| `supervisor_agent` | 复杂任务综合 | STRONG | 无 |

Registry 是模型绑定和工具权限的唯一声明位置。工具不会接受任意 SQL，也不会由模型动态扩权。

## 状态与上下文隔离

共享 `AgentState` 分为请求身份、规范化实体、会话投影、当前工作流结果和可观测数据。Redis 保存短期消息与独立的会话状态（当前服务、主题、摘要）；具体 RAG 块、工具原始结果和 Specialist 中间状态不会写入长期会话摘要。

`ContextProjector` 为每个 Specialist 生成最小上下文：Knowledge 只看到检索任务和紧凑失败事实；Ops 只看到规范服务名、动作和时间范围；Diagnosis 只看到已确认事实与知识证据；Supervisor 只看到结构化 Agent 结果和引用。

## 模型网关、隐私与降级

- LOCAL 使用本机 OpenAI-compatible vLLM。
- STRONG 使用配置的 ModelScope OpenAI-compatible API。
- `ALLOW_CLOUD_INTERNAL_DATA=false` 是默认值。包含 DB/RAG/会话上下文的 STRONG 请求以 `LOCAL_ONLY` 发出，因此网关直接改由 LOCAL 服务。
- STRONG 未配置、隐私不允许或服务异常时，仅降级一次；本地失败后停止，避免无限重试。
- 每次模型调用记录 requested/served role、模型、provider、fallback reason、延迟和 token usage 到 `model_call_log`。

只有业务明确允许把内部上下文发往云端时，才可把 `ALLOW_CLOUD_INTERNAL_DATA` 显式改为 `true`。

## API 兼容与观测

原响应字段 `intent`、`answer`、`citations`、`tools_used` 保留。V2 新增 `selected_path`、`selected_agents` 和 `model_info`。前端会把路径、Agent、工具和模型降级以 trace 标签显示。MySQL 保留消息、工具调用和模型调用审计。

## 测试

```powershell
conda run -n agentdev python -m pytest -q
conda run -n agentdev python scripts\eval_agent_v2.py
```

30 条评测集位于 `data/eval/agent_v2_cases.jsonl`，覆盖 direct、knowledge、ops、mixed 和 multi-turn。端到端报告输出到 `reports/agent_v2_eval.json`。

## 已知限制

- Complex 路径目前是有界顺序编排，优先保证状态合并确定性；后续可在独立状态分支成熟后并行执行 Ops 与 Knowledge。
- 会话摘要当前是确定性短摘要，未做长期语义记忆。
- 云端 STRONG 的可用性不等于允许发送企业数据；二者由独立配置控制。
- RAG 效果仍受已索引文档质量和嵌入模型影响。
