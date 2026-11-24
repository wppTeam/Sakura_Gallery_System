"""add reports table

内容举报 / 侵权投诉（通知—删除渠道）

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("reason_code", sa.String(32), nullable=False),
        sa.Column("reason_text", sa.Text(), nullable=True),
        sa.Column("contact", sa.String(200), nullable=True),
        sa.Column(
            "reporter_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reporter_ip", sa.String(45), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column(
            "handled_by", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("handled_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("action_taken", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index("ix_reports_created_at", "reports", ["created_at"])
    op.create_index("ix_reports_reporter_id", "reports", ["reporter_id"])
    op.create_index("ix_reports_status_created", "reports", ["status", "created_at"])
    op.create_index("ix_reports_target", "reports", ["target_type", "target_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_target", table_name="reports")
    op.drop_index("ix_reports_status_created", table_name="reports")
    op.drop_index("ix_reports_reporter_id", table_name="reports")
    op.drop_index("ix_reports_created_at", table_name="reports")
    op.drop_index("ix_reports_status", table_name="reports")
    op.drop_table("reports")
