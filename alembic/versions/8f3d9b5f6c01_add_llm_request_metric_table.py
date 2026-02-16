"""add llm request metric table

Revision ID: 8f3d9b5f6c01
Revises: 41a6615da940
Create Date: 2026-02-16 22:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8f3d9b5f6c01"
down_revision: Union[str, Sequence[str], None] = "41a6615da940"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exile_llm_request_metric",
        sa.Column("request_id", sa.String(length=64), nullable=False, comment="请求ID"),
        sa.Column("conversation_id", sa.String(length=64), nullable=True, comment="会话ID"),
        sa.Column("owner_id", sa.BigInteger(), nullable=False, comment="用户ID"),
        sa.Column("provider", sa.String(length=32), nullable=False, comment="实际模型厂商"),
        sa.Column("model", sa.String(length=128), nullable=False, comment="实际模型名称"),
        sa.Column("is_stream", sa.Integer(), nullable=False, comment="是否流式:0/1"),
        sa.Column("success", sa.Integer(), nullable=False, comment="是否成功:0/1"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, comment="端到端耗时(ms)"),
        sa.Column("error_code", sa.String(length=64), nullable=True, comment="错误码"),
        sa.Column("error_message", sa.Text(), nullable=True, comment="错误信息"),
        sa.Column("fallback_from", sa.String(length=32), nullable=True, comment="回退来源provider"),
        sa.Column("fallback_chain", sa.JSON(), nullable=False, comment="回退尝试链路"),
        sa.Column("usage_prompt_tokens", sa.Integer(), nullable=False, comment="输入token"),
        sa.Column("usage_completion_tokens", sa.Integer(), nullable=False, comment="输出token"),
        sa.Column("usage_total_tokens", sa.Integer(), nullable=False, comment="总token"),
        sa.Column("usage_raw", sa.JSON(), nullable=False, comment="原始usage"),
        sa.Column("extra", sa.JSON(), nullable=False, comment="扩展信息"),
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="id"),
        sa.Column("create_time", sa.DateTime(timezone=True), nullable=False, comment="创建时间(结构化时间)"),
        sa.Column("create_timestamp", sa.BigInteger(), nullable=False, comment="创建时间(时间戳)"),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=False, comment="更新时间(结构化时间)"),
        sa.Column("update_timestamp", sa.BigInteger(), nullable=True, comment="更新时间(时间戳)"),
        sa.Column("is_deleted", sa.BigInteger(), nullable=True, comment="0正常;其他:已删除"),
        sa.Column("status", sa.Integer(), nullable=True, comment="状态"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index("idx_llm_metric_owner_time", "exile_llm_request_metric", ["owner_id", "create_time"], unique=False)
    op.create_index("idx_llm_metric_provider_model", "exile_llm_request_metric", ["provider", "model"], unique=False)
    op.create_index("idx_llm_metric_success", "exile_llm_request_metric", ["success"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_llm_metric_success", table_name="exile_llm_request_metric")
    op.drop_index("idx_llm_metric_provider_model", table_name="exile_llm_request_metric")
    op.drop_index("idx_llm_metric_owner_time", table_name="exile_llm_request_metric")
    op.drop_table("exile_llm_request_metric")
