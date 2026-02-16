# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LLMConversationCreateReq(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, description="会话标题")
    provider: str | None = Field(default=None, description="模型厂商: deepseek/openai/gemini")
    model: str | None = Field(default=None, description="模型名称")
    system_prompt: str | None = Field(default=None, description="系统提示词")
    skill_name: str | None = Field(default=None, description="技能名称")
    extra_config: dict[str, Any] = Field(default_factory=dict, description="扩展配置")


class LLMChatReq(BaseModel):
    model_config = ConfigDict(extra="ignore")

    conversation_id: str | None = Field(default=None, description="会话ID，不传则创建新会话")
    message: str = Field(description="用户消息", min_length=1, max_length=20000)
    provider: str | None = Field(default=None, description="模型厂商")
    model: str | None = Field(default=None, description="模型名称")
    temperature: float | None = Field(default=None, ge=0, le=2, description="温度")
    tool_names: list[str] = Field(default_factory=list, description="工具名称列表，不传默认全量工具")
    use_tools: bool = Field(default=True, description="是否启用工具调用")
    max_tool_steps: int | None = Field(default=None, ge=1, le=8, description="最大工具调用轮次")
    system_prompt: str | None = Field(default=None, description="覆盖会话系统提示词")
    skill_name: str | None = Field(default=None, description="运行时技能")
    use_rag: bool = Field(default=False, description="是否启用RAG")
    rag_top_k: int = Field(default=3, ge=1, le=20, description="RAG召回数量")


class LLMConversationDetailResp(BaseModel):
    conversation_id: str
    title: str | None
    provider: str
    model: str
    system_prompt: str | None
    skill_name: str | None
    extra_config: dict[str, Any]


class LLMMessageResp(BaseModel):
    role: str
    content: str | None = None
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    provider: str | None = None
    model: str | None = None
    token_usage: dict[str, Any] | None = None


class LLMChatResp(BaseModel):
    conversation_id: str
    provider: str
    model: str
    assistant_message: str | None = None
    tool_runs: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] = Field(default_factory=dict)


class LLMSkillUpsertReq(BaseModel):
    model_config = ConfigDict(extra="ignore")

    skill_name: str = Field(description="Skill 名称", min_length=1, max_length=128)
    description: str | None = Field(default=None, description="描述")
    system_prompt: str = Field(description="系统提示词", min_length=1)
    tool_names: list[str] = Field(default_factory=list, description="工具白名单")
    rag_enabled: bool = Field(default=False, description="是否启用RAG")
    mcp_server_ids: list[str] = Field(default_factory=list, description="MCP服务器ID列表")
    extra_config: dict[str, Any] = Field(default_factory=dict, description="扩展配置")


class MCPServerUpsertReq(BaseModel):
    model_config = ConfigDict(extra="ignore")

    server_id: str = Field(description="服务器ID", min_length=1, max_length=64)
    name: str = Field(description="服务器名称", min_length=1, max_length=128)
    transport: str = Field(default="http", description="传输方式:http/stdio/mock")
    endpoint: str | None = Field(default=None, description="HTTP endpoint")
    command: str | None = Field(default=None, description="stdio command")
    args: list[Any] = Field(default_factory=list, description="启动参数")
    env: dict[str, Any] = Field(default_factory=dict, description="环境变量")
    timeout_seconds: int = Field(default=30, ge=1, le=600, description="请求超时")
    enabled: bool = Field(default=True, description="是否启用")
    tool_definitions: list[dict[str, Any]] = Field(default_factory=list, description="工具定义")
    extra_config: dict[str, Any] = Field(default_factory=dict, description="扩展配置")


class RAGDocumentIngestReq(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = Field(description="文档标题", min_length=1, max_length=255)
    content: str = Field(description="文档内容", min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict, description="文档元数据")
    chunk_size: int = Field(default=800, ge=200, le=4000, description="切块大小")
    chunk_overlap: int = Field(default=120, ge=0, le=1000, description="切块重叠")
    embedding_provider: str | None = Field(default=None, description="向量厂商")
    embedding_model: str | None = Field(default=None, description="向量模型")


class RAGRetrieveReq(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str = Field(description="检索查询", min_length=1)
    top_k: int = Field(default=3, ge=1, le=20)
    embedding_provider: str | None = Field(default=None, description="向量厂商")
    embedding_model: str | None = Field(default=None, description="向量模型")
