"""add skill mcp rag tables

Revision ID: 41a6615da940
Revises: 9f5e9a4a0a2b
Create Date: 2026-02-16 20:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "41a6615da940"
down_revision: Union[str, Sequence[str], None] = "9f5e9a4a0a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exile_llm_skill",
        sa.Column("skill_name", sa.String(length=128), nullable=False, comment="Skill 名称"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True, comment="所属用户ID，空表示全局"),
        sa.Column("description", sa.String(length=255), nullable=True, comment="描述"),
        sa.Column("system_prompt", sa.Text(), nullable=False, comment="系统提示词"),
        sa.Column("tool_names", sa.JSON(), nullable=False, comment="工具白名单"),
        sa.Column("rag_enabled", sa.Integer(), nullable=False, comment="是否启用RAG:0/1"),
        sa.Column("mcp_server_ids", sa.JSON(), nullable=False, comment="MCP服务器ID列表"),
        sa.Column("is_builtin", sa.Integer(), nullable=False, comment="是否内置"),
        sa.Column("extra_config", sa.JSON(), nullable=False, comment="扩展配置"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_llm_skill_name", "exile_llm_skill", ["skill_name"], unique=False)
    op.create_index("idx_llm_skill_owner_id", "exile_llm_skill", ["owner_id"], unique=False)

    op.create_table(
        "exile_mcp_server",
        sa.Column("server_id", sa.String(length=64), nullable=False, comment="服务器ID"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True, comment="所属用户ID，空表示全局"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="服务器名称"),
        sa.Column("transport", sa.String(length=32), nullable=False, comment="传输方式:http/stdio/mock"),
        sa.Column("endpoint", sa.String(length=512), nullable=True, comment="HTTP endpoint"),
        sa.Column("command", sa.String(length=512), nullable=True, comment="stdio command"),
        sa.Column("args", sa.JSON(), nullable=False, comment="启动参数"),
        sa.Column("env", sa.JSON(), nullable=False, comment="环境变量"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, comment="请求超时"),
        sa.Column("enabled", sa.Integer(), nullable=False, comment="是否启用:0/1"),
        sa.Column("tool_definitions", sa.JSON(), nullable=False, comment="工具定义列表"),
        sa.Column("extra_config", sa.JSON(), nullable=False, comment="扩展配置"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("server_id"),
    )
    op.create_index("idx_mcp_server_owner_id", "exile_mcp_server", ["owner_id"], unique=False)
    op.create_index("idx_mcp_server_enabled", "exile_mcp_server", ["enabled"], unique=False)

    op.create_table(
        "exile_rag_document",
        sa.Column("doc_id", sa.String(length=64), nullable=False, comment="文档ID"),
        sa.Column("owner_id", sa.BigInteger(), nullable=False, comment="所属用户ID"),
        sa.Column("title", sa.String(length=255), nullable=False, comment="标题"),
        sa.Column("content", sa.Text(), nullable=False, comment="原始内容"),
        sa.Column("metadata", sa.JSON(), nullable=False, comment="元数据"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, comment="切块数量"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("doc_id"),
    )
    op.create_index("idx_rag_document_owner_id", "exile_rag_document", ["owner_id"], unique=False)

    op.create_table(
        "exile_rag_chunk",
        sa.Column("doc_id", sa.String(length=64), nullable=False, comment="文档ID"),
        sa.Column("owner_id", sa.BigInteger(), nullable=False, comment="所属用户ID"),
        sa.Column("chunk_index", sa.Integer(), nullable=False, comment="切块索引"),
        sa.Column("content", sa.Text(), nullable=False, comment="切块内容"),
        sa.Column("embedding", sa.JSON(), nullable=False, comment="向量"),
        sa.Column("metadata", sa.JSON(), nullable=False, comment="元数据"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_rag_chunk_doc_id", "exile_rag_chunk", ["doc_id"], unique=False)
    op.create_index("idx_rag_chunk_owner_id", "exile_rag_chunk", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_rag_chunk_owner_id", table_name="exile_rag_chunk")
    op.drop_index("idx_rag_chunk_doc_id", table_name="exile_rag_chunk")
    op.drop_table("exile_rag_chunk")

    op.drop_index("idx_rag_document_owner_id", table_name="exile_rag_document")
    op.drop_table("exile_rag_document")

    op.drop_index("idx_mcp_server_enabled", table_name="exile_mcp_server")
    op.drop_index("idx_mcp_server_owner_id", table_name="exile_mcp_server")
    op.drop_table("exile_mcp_server")

    op.drop_index("idx_llm_skill_owner_id", table_name="exile_llm_skill")
    op.drop_index("idx_llm_skill_name", table_name="exile_llm_skill")
    op.drop_table("exile_llm_skill")
