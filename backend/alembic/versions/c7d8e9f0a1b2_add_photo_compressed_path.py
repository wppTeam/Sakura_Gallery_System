"""add photo compressed_path

模型 Photo.compressed_path 早已存在，但此前没有任何迁移添加该列，
导致全新数据库在查询 photos 时报 UndefinedColumn，新克隆无法直接跑起来。
线上历史部署靠手工脚本补列，此迁移把这一步补进迁移链。

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-11-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # 历史部署可能已手工补过该列，幂等处理
    if not _has_column("photos", "compressed_path"):
        op.add_column("photos", sa.Column("compressed_path", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("photos", "compressed_path"):
        op.drop_column("photos", "compressed_path")