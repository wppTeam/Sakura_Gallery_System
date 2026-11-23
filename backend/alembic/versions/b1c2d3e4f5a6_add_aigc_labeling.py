"""add AIGC legal labeling fields to photos

Revision ID: a1b2c3d4e5f6
Revises: f0a1b2c3d4e5
Create Date: 2026-11-23

《人工智能生成合成内容标识办法》（2025-09-01 施行）要求：
1. 上传时强制声明是否 AI 生成；
2. 展示显式标识；
3. 下载文件写入隐式标识（XMP/EXIF）；
4. 图生图 / 换脸类需额外限制与授权声明。

本迁移只加列，审核与标识写入由应用层完成。
"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b1c2d3e4f5a6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "photos",
        sa.Column("is_aigc", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("photos", sa.Column("aigc_label", sa.String(length=32), nullable=True))
    op.add_column("photos", sa.Column("aigc_meta", sa.JSON(), nullable=True))
    op.add_column(
        "photos",
        sa.Column("label_written", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_photos_is_aigc", "photos", ["is_aigc"])
    # 存量数据统一视为「非 AIGC」；若审核历史已标记疑似，由后台按需回填。
    op.execute("UPDATE photos SET is_aigc = false WHERE is_aigc IS NULL")
    op.execute("UPDATE photos SET label_written = false WHERE label_written IS NULL")


def downgrade() -> None:
    op.drop_index("ix_photos_is_aigc", table_name="photos")
    op.drop_column("photos", "label_written")
    op.drop_column("photos", "aigc_meta")
    op.drop_column("photos", "aigc_label")
    op.drop_column("photos", "is_aigc")
