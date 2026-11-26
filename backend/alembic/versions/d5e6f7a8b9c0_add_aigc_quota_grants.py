"""add aigc quota grants and generation quota_source

AI 生图额度：每日基础额度（默认 3 张，管理员不限）+ 管理员赠送池。
赠送台账只记「送了多少」，剩余由「总量 − 非 failed 的 bonus 生成数」推导。

Revision ID: d5e6f7a8b9c0
Revises: c9d0e1f2a3b4
Create Date: 2026-11-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "aigc_quota_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column(
            "granted_by",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_aigc_quota_grants_user_id", "aigc_quota_grants", ["user_id"])
    op.create_index("ix_aigc_quota_grants_created_at", "aigc_quota_grants", ["created_at"])
    op.create_index(
        "ix_aigc_quota_grants_user_created", "aigc_quota_grants", ["user_id", "created_at"]
    )
    op.add_column(
        "aigc_generations",
        sa.Column(
            "quota_source", sa.String(10), nullable=False, server_default="daily"
        ),
    )


def downgrade() -> None:
    op.drop_column("aigc_generations", "quota_source")
    op.drop_index("ix_aigc_quota_grants_user_created", table_name="aigc_quota_grants")
    op.drop_index("ix_aigc_quota_grants_created_at", table_name="aigc_quota_grants")
    op.drop_index("ix_aigc_quota_grants_user_id", table_name="aigc_quota_grants")
    op.drop_table("aigc_quota_grants")