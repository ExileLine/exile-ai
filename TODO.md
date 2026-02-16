# LLM 基建设计与实施 TODO

## 目标
- 支持多模型厂商：`DeepSeek / OpenAI / Gemini`
- 环境策略：
- 开发环境默认使用 `DeepSeek`
- 生产环境默认使用 `OpenAI`，可按业务切换 `Gemini`
- 实现能力：
- 多轮对话
- MCP
- Function Calling
- RAG
- Skill

## 技术选型
- 后端框架：沿用现有 `FastAPI + SQLAlchemy + Alembic + Redis + Celery`
- 模型网关层：自研统一适配器（OpenAI-compatible 协议优先），通过配置动态选择厂商
- 对话存储：MySQL/PostgreSQL（已有 DB）持久化会话与消息，Redis 可做热缓存（后续）
- 工具调用：统一 Tool Registry（JSON Schema 描述 + 执行器）
- MCP：实现 MCP Server Registry + MCP Tool Adapter（将 MCP 工具映射为 Function Calling Tool）
- RAG：
- P1 先实现“小规模可用版”：文档切块 + 向量入库 + 余弦召回
- P2 演进为外部向量库（Qdrant/pgvector 二选一）
- Skill：Skill 配置化（系统提示词 + 工具白名单 + RAG 策略 + MCP 服务器集合）

## 架构设计
- `app/services/llm/providers.py`
- 统一模型客户端（按 provider 组装 `base_url/api_key/model`）
- `app/services/llm/tool_registry.py`
- 工具注册、参数校验、执行、错误封装
- `app/services/llm/chat_service.py`
- 会话编排（历史消息 -> 模型 -> tool calls -> 工具执行 -> 模型总结）
- `app/services/llm/rag_service.py`（P2）
- 文档切块、embedding、检索、上下文注入
- `app/services/llm/mcp_service.py`（P2）
- MCP server 生命周期管理与工具桥接
- `app/services/llm/skill_service.py`（P2）
- Skill 装载、运行时上下文拼装

## 数据模型规划
- `exile_llm_conversation`
- 会话主表（owner、provider、model、system_prompt、skill_name）
- `exile_llm_message`
- 消息表（role、content、tool_call_id、tool_name、tool_calls）
- `exile_llm_skill`（P2）
- Skill 配置表（prompt、tools、rag_config、mcp_servers）
- `exile_rag_document` / `exile_rag_chunk`（P2）
- RAG 文档与切块向量
- `exile_mcp_server`（P2）
- MCP 服务器配置（command、args、env、enabled）

## 分阶段实施

### P0（当前）
- [x] 增加 LLM 配置项（DeepSeek/OpenAI/Gemini）
- [x] 实现统一模型客户端（基础对话）
- [x] 创建 `TODO.md`（本文件）

### P1（当前优先）
- [x] 增加会话/消息模型与 Alembic 迁移
- [x] 实现多轮对话 API
- [x] 实现 Tool Registry + Function Calling 闭环
- [x] 新增工具查询 API（便于前端动态展示）
- [x] 新增 Web Console（登录、会话管理、多轮消息操作）

### P2（下一阶段）
- [x] MCP Server Registry 与执行通道
- [x] MCP Tool Adapter 接入 Function Calling
- [x] RAG（文档入库、切块、向量化、召回）
- [x] Skill（配置化 + 对话时装载）
- [x] 编排模式切换基座（legacy/langgraph）
- [x] LLM协议规范与能力矩阵接口

### P3（生产增强）
- [x] 流式输出（SSE）
- [x] 观测性（token 用量、延迟、错误率）
- [x] 限流与配额（按用户/模型）
- [x] 会话摘要与长期记忆
- [x] 自动回退策略（主模型失败自动切换备用模型）

## 验收标准
- [x] 可通过配置在 `deepseek/openai/gemini` 间切换
- [x] 可创建会话并进行多轮对话（含持久化）
- [x] Function Calling 至少 2 个内置工具可用
- [x] MCP/RAG/Skill 提供可运行的最小版本
- [x] 提供基础 API 文档与示例请求
