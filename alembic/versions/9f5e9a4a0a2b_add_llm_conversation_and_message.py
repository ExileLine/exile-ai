"""add llm conversation and message

Revision ID: 9f5e9a4a0a2b
Revises: 5398d2e18834
Create Date: 2026-02-16 18:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f5e9a4a0a2b"
down_revision: Union[str, Sequence[str], None] = "5398d2e18834"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exile_llm_conversation",
        sa.Column("conversation_id", sa.String(length=64), nullable=False, comment="会话ID"),
        sa.Column("owner_id", sa.BigInteger(), nullable=False, comment="会话所属用户ID"),
        sa.Column("title", sa.String(length=255), nullable=True, comment="会话标题"),
        sa.Column("provider", sa.String(length=32), nullable=False, comment="模型厂商"),
        sa.Column("model", sa.String(length=128), nullable=False, comment="模型名称"),
        sa.Column("system_prompt", sa.Text(), nullable=True, comment="系统提示词"),
        sa.Column("skill_name", sa.String(length=128), nullable=True, comment="技能名称"),
        sa.Column("extra_config", sa.JSON(), nullable=False, comment="扩展配置"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("conversation_id"),
    )
    op.create_index(
        "idx_llm_conversation_owner",
        "exile_llm_conversation",
        ["owner_id"],
        unique=False,
    )

    op.create_table(
        "exile_llm_message",
        sa.Column("conversation_id", sa.String(length=64), nullable=False, comment="会话ID"),
        sa.Column("owner_id", sa.BigInteger(), nullable=False, comment="消息所属用户ID"),
        sa.Column("role", sa.String(length=16), nullable=False, comment="消息角色:system/user/assistant/tool"),
        sa.Column("content", sa.Text(), nullable=True, comment="消息内容"),
        sa.Column("tool_name", sa.String(length=128), nullable=True, comment="工具名称"),
        sa.Column("tool_call_id", sa.String(length=128), nullable=True, comment="工具调用ID"),
        sa.Column("tool_calls", sa.JSON(), nullable=True, comment="assistant 的工具调用列表"),
        sa.Column("provider", sa.String(length=32), nullable=True, comment="模型厂商"),
        sa.Column("model", sa.String(length=128), nullable=True, comment="模型名称"),
        sa.Column("token_usage", sa.JSON(), nullable=True, comment="token 使用统计"),
        sa.Column("extra", sa.JSON(), nullable=False, comment="扩展数据"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_llm_message_conversation_id",
        "exile_llm_message",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "idx_llm_message_owner_id",
        "exile_llm_message",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_llm_message_owner_id", table_name="exile_llm_message")
    op.drop_index("idx_llm_message_conversation_id", table_name="exile_llm_message")
    op.drop_table("exile_llm_message")
    op.drop_index("idx_llm_conversation_owner", table_name="exile_llm_conversation")
    op.drop_table("exile_llm_conversation")
