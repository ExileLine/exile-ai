# LLM Agent Architecture Baseline

## Target

最终能力目标：`Agent + FunctionCalling + MCP + Skill + RAG`

## Orchestrator

- 配置项：`LLM_ORCHESTRATOR=legacy|langgraph`
- 默认：`legacy`
- 当切换到 `langgraph` 时，编排层由 LangGraph 驱动。

## Protocol Contracts

统一协议定义在：`app/services/llm/contracts.py`

- 编排模式：`OrchestratorMode`
- 运行状态：`AgentRunStatus`
- 流式事件：`SSEEventType`
- 能力矩阵：`CapabilityMatrix`
- 状态封装：`AgentStateEnvelope`

## API Conventions

- 对话：`POST /api/llm/chat`
- 流式：`POST /api/llm/chat/stream`（SSE）
- 能力矩阵：`GET /api/llm/capabilities`
- 观测汇总：`GET /api/llm/metrics/summary`
- 最近观测：`GET /api/llm/metrics/recent`
- 配额快照：`GET /api/llm/quota`

SSE 事件规范：

- `meta`: 开始信息（conversation_id/provider/model/warning）
- `delta`: 增量文本
- `done`: 结束信息（usage/finish_reason）
- `error`: 错误信息

## Next Milestones

1. Agent run 持久化（run_id + state checkpoint）
2. Human approval API（pause/resume/reject）
3. LangGraph 节点化：并行分支、可恢复执行、审批门禁
4. MCP stdio 传输支持（当前仅 http/mock）
5. RAG 向量库演进（Qdrant/pgvector）
