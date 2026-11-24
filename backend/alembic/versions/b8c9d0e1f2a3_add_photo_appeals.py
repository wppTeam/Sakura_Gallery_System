"""add photo_appeals table

审核复核（申诉）通道：被驳回作品的作者可以提交一次复核申请，
管理员受理 accept 后作品回到 pending 重新审核。

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_appeals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "photo_id",
            sa.String(36),
            sa.ForeignKey("photos.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "handled_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_photo_appeals_photo_id", "photo_appeals", ["photo_id"])
    op.create_index("ix_photo_appeals_user_id", "photo_appeals", ["user_id"])
    op.create_index("ix_photo_appeals_status", "photo_appeals", ["status"])
    op.create_index("ix_photo_appeals_created_at", "photo_appeals", ["created_at"])
    op.create_index(
        "ix_photo_appeals_status_created", "photo_appeals", ["status", "created_at"]
    )
    op.create_index(
        "ix_photo_appeals_photo_status", "photo_appeals", ["photo_id", "status"]
    )
    # 同一作品只允许一条 pending 申请：PG 用部分唯一索引兜底（SQLite 测试由代码层校验）
    op.execute(
        "CREATE UNIQUE INDEX uq_photo_appeals_pending "
        "ON photo_appeals (photo_id) WHERE status = 'pending'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_photo_appeals_pending")
    op.drop_index("ix_photo_appeals_photo_status", table_name="photo_appeals")
    op.drop_index("ix_photo_appeals_status_created", table_name="photo_appeals")
    op.drop_index("ix_photo_appeals_created_at", table_name="photo_appeals")
    op.drop_index("ix_photo_appeals_status", table_name="photo_appeals")
    op.drop_index("ix_photo_appeals_user_id", table_name="photo_appeals")
    op.drop_index("ix_photo_appeals_photo_id", table_name="photo_appeals")
    op.drop_table("photo_appeals")
