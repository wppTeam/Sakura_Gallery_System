"""策展专题（collections / collection_photos）

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-11-23 23:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "collections",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("subtitle", sa.String(length=200), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cover_photo_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="editorial"),
        sa.Column("owner_id", sa.String(length=36), nullable=True),
        sa.Column("visibility", sa.String(length=20), nullable=False, server_default="public"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="published"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["cover_photo_id"], ["photos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_collections_slug", "collections", ["slug"], unique=True)
    op.create_index("ix_collections_status_sort", "collections", ["status", "sort_order"], unique=False)

    op.create_table(
        "collection_photos",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("photo_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("collection_id", "photo_id", name="uq_collection_photo"),
    )
    op.create_index(
        "ix_collection_photos_collection_id", "collection_photos", ["collection_id"], unique=False
    )
    op.create_index("ix_collection_photos_photo_id", "collection_photos", ["photo_id"], unique=False)
    op.create_index(
        "ix_collection_photos_collection_position",
        "collection_photos",
        ["collection_id", "position"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_collection_photos_collection_position", table_name="collection_photos")
    op.drop_index("ix_collection_photos_photo_id", table_name="collection_photos")
    op.drop_index("ix_collection_photos_collection_id", table_name="collection_photos")
    op.drop_table("collection_photos")
    op.drop_index("ix_collections_status_sort", table_name="collections")
    op.drop_index("ix_collections_slug", table_name="collections")
    op.drop_table("collections")
