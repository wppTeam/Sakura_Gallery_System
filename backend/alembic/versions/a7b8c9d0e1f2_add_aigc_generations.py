"""add aigc_generations table

站内 AI 生图（AI 创作台）：生成任务与草稿图元信息。

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aigc_generations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("size_key", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("provider", sa.String(50), nullable=False, server_default="dashscope"),
        sa.Column("model_id", sa.String(120), nullable=False),
        sa.Column("provider_task_id", sa.String(120), nullable=True),
        sa.Column("image_path", sa.String(500), nullable=True),
        sa.Column("image_format", sa.String(16), nullable=True),
        sa.Column("image_bytes", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_aigc_generations_user_id", "aigc_generations", ["user_id"])
    op.create_index("ix_aigc_generations_status", "aigc_generations", ["status"])
    op.create_index("ix_aigc_generations_created_at", "aigc_generations", ["created_at"])
    op.create_index(
        "ix_aigc_generations_user_created", "aigc_generations", ["user_id", "created_at"]
    )
    op.create_index(
        "ix_aigc_generations_status_created", "aigc_generations", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_aigc_generations_status_created", table_name="aigc_generations")
    op.drop_index("ix_aigc_generations_user_created", table_name="aigc_generations")
    op.drop_index("ix_aigc_generations_created_at", table_name="aigc_generations")
    op.drop_index("ix_aigc_generations_status", table_name="aigc_generations")
    op.drop_index("ix_aigc_generations_user_id", table_name="aigc_generations")
    op.drop_table("aigc_generations")
