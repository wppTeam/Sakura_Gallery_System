"""add portrait privacy level and redacted media paths

人像隐私分级（2026-11-24）：
- photos.privacy_level: normal | sensitive，sensitive 默认不公开展示
- photos.redacted_path / redacted_thumb_path: 强模糊脱敏图（对外展示用）
- 索引 ix_photos_privacy_level 便于公共列表过滤

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-11-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c2d3e4f5a6b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("privacy_level", sa.String(length=16), nullable=False, server_default="normal"),
    )
    op.add_column("photos", sa.Column("redacted_path", sa.Text(), nullable=True))
    op.add_column("photos", sa.Column("redacted_thumb_path", sa.Text(), nullable=True))
    op.create_index("ix_photos_privacy_level", "photos", ["privacy_level"])


def downgrade() -> None:
    op.drop_index("ix_photos_privacy_level", table_name="photos")
    op.drop_column("photos", "redacted_thumb_path")
    op.drop_column("photos", "redacted_path")
    op.drop_column("photos", "privacy_level")
