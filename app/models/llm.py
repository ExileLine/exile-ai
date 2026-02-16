# -*- coding: utf-8 -*-

from __future__ import annotations

from sqlalchemy import BigInteger, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import CustomBaseModel


class LLMConversation(CustomBaseModel):
    """大模型会话"""

    __tablename__ = "exile_llm_conversation"

    conversation_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False, comment="会话ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="会话所属用户ID")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="会话标题")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, comment="模型厂商")
    model: Mapped[str] = mapped_column(String(128), nullable=False, comment="模型名称")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True, comment="系统提示词")
    skill_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="技能名称")
    extra_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="扩展配置")

    __table_args__ = (
        Index("idx_llm_conversation_owner", "owner_id"),
    )


class LLMMessage(CustomBaseModel):
    """大模型会话消息"""

    __tablename__ = "exile_llm_message"

    conversation_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="会话ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="消息所属用户ID")
    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="消息角色:system/user/assistant/tool")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="消息内容")
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="工具名称")
    tool_call_id: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="工具调用ID")
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True, comment="assistant 的工具调用列表")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="模型厂商")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="模型名称")
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="token 使用统计")
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="扩展数据")

    __table_args__ = (
        Index("idx_llm_message_conversation_id", "conversation_id"),
        Index("idx_llm_message_owner_id", "owner_id"),
    )


class LLMSkill(CustomBaseModel):
    """Skill 配置"""

    __tablename__ = "exile_llm_skill"

    skill_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Skill 名称")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="所属用户ID，空表示全局")
    description: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="描述")
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, comment="系统提示词")
    tool_names: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="工具白名单")
    rag_enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否启用RAG:0/1")
    mcp_server_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="MCP服务器ID列表")
    is_builtin: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否内置")
    extra_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="扩展配置")

    __table_args__ = (
        Index("idx_llm_skill_name", "skill_name"),
        Index("idx_llm_skill_owner_id", "owner_id"),
    )


class MCPServer(CustomBaseModel):
    """MCP 服务器配置"""

    __tablename__ = "exile_mcp_server"

    server_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="服务器ID")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="所属用户ID，空表示全局")
    name: Mapped[str] = mapped_column(String(128), nullable=False, comment="服务器名称")
    transport: Mapped[str] = mapped_column(String(32), nullable=False, default="http", comment="传输方式:http/stdio/mock")
    endpoint: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="HTTP endpoint")
    command: Mapped[str | None] = mapped_column(String(512), nullable=True, comment="stdio command")
    args: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="启动参数")
    env: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="环境变量")
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30, comment="请求超时")
    enabled: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否启用:0/1")
    tool_definitions: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="工具定义列表")
    extra_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="扩展配置")

    __table_args__ = (
        Index("idx_mcp_server_owner_id", "owner_id"),
        Index("idx_mcp_server_enabled", "enabled"),
    )


class RAGDocument(CustomBaseModel):
    """RAG 文档"""

    __tablename__ = "exile_rag_document"

    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="文档ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属用户ID")
    title: Mapped[str] = mapped_column(String(255), nullable=False, comment="标题")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="原始内容")
    meta_info: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict, comment="元数据")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="切块数量")

    __table_args__ = (
        Index("idx_rag_document_owner_id", "owner_id"),
    )


class RAGChunk(CustomBaseModel):
    """RAG 切块"""

    __tablename__ = "exile_rag_chunk"

    doc_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="文档ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="所属用户ID")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="切块索引")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="切块内容")
    embedding: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="向量")
    meta_info: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict, comment="元数据")

    __table_args__ = (
        Index("idx_rag_chunk_doc_id", "doc_id"),
        Index("idx_rag_chunk_owner_id", "owner_id"),
    )


class LLMRequestMetric(CustomBaseModel):
    """LLM 请求观测指标"""

    __tablename__ = "exile_llm_request_metric"

    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True, comment="请求ID")
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="会话ID")
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, comment="用户ID")
    provider: Mapped[str] = mapped_column(String(32), nullable=False, comment="实际模型厂商")
    model: Mapped[str] = mapped_column(String(128), nullable=False, comment="实际模型名称")
    is_stream: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="是否流式:0/1")
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="是否成功:0/1")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="端到端耗时(ms)")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="错误码")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    fallback_from: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="回退来源provider")
    fallback_chain: Mapped[list] = mapped_column(JSON, nullable=False, default=list, comment="回退尝试链路")
    usage_prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输入token")
    usage_completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输出token")
    usage_total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="总token")
    usage_raw: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="原始usage")
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, comment="扩展信息")

    __table_args__ = (
        Index("idx_llm_metric_owner_time", "owner_id", "create_time"),
        Index("idx_llm_metric_provider_model", "provider", "model"),
        Index("idx_llm_metric_success", "success"),
    )
