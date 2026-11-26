"""add user bio and avatar

公开创作者主页装修：作者简介 + 头像（本地 uploads/avatars/，与 AI 草稿同口径）。

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f7a8b9c0d1"
down_revision: Union[str, Sequence[str], None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("bio", sa.String(200), nullable=True))
    op.add_column("users", sa.Column("avatar_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "avatar_path")
    op.drop_column("users", "bio")