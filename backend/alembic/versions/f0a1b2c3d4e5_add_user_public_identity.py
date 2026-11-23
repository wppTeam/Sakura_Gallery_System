"""add user public identity columns (username / display_name)

公开端只能展示公开身份：AGENTS.md §5 要求公开响应不得包含学号与真实姓名，
因此为 users 增加 username / display_name 两列。二者均可空，旧数据回填一个
确定性的 username，避免唯一索引冲突。

Revision ID: f0a1b2c3d4e5
Revises: e9f0a1b2c3d4
Create Date: 2026-11-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "f0a1b2c3d4e5"
down_revision = "e9f0a1b2c3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "username",
            sa.String(length=32),
            nullable=True,
            comment="公开用户名，唯一；缺省时前端回退到展示名",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "display_name",
            sa.String(length=64),
            nullable=True,
            comment="公开昵称，展示用",
        ),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # 旧数据回填确定性公开用户名：u<id 去掉横线后的前 12 位>，只补 NULL 行
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "postgresql":
        bind.execute(
            sa.text(
                "UPDATE users SET username = 'u' || substr(replace(id, '-', ''), 1, 12) "
                "WHERE username IS NULL"
            )
        )
    else:  # sqlite / 其他
        bind.execute(
            sa.text(
                "UPDATE users SET username = 'u' || substr(replace(id, '-', ''), 1, 12) "
                "WHERE username IS NULL"
            )
        )


def downgrade() -> None:
    op.drop_index("ix_users_username", table_name="users")
    op.drop_column("users", "display_name")
    op.drop_column("users", "username")
