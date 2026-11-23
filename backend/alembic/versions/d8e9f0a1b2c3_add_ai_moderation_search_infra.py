"""add AI moderation / usage / agent search infra

新增三张表与检索索引：

- ``moderation_reviews``：照片 AI 审核结论（规则 / 快筛 / 复核 / 人工终判 / 用量）
- ``ai_usage_events``：每次 AI 调用的用量与成本事件
- ``agent_search_traces``：Agent 检索轨迹（意图 / 工具步骤 / 解释）

同时在 PostgreSQL 上：

- 启用 ``pg_trgm`` 扩展，给 ``photos.title`` / ``photos.description`` /
  ``tags.name`` 建 GIN trigram 索引（中文模糊检索走 similarity / ILIKE）
- 给 ``photos`` 增加 ``search_tokens``（应用层中文二元组分词写入）与生成列
  ``search_vector``（``to_tsvector('simple', search_tokens)``）+ GIN 索引
- 补 ``photos(status, created_at)`` 与 ``photos(captured_at)`` 索引（公共端列表/时间线）

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-11-23
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _is_postgresql() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. moderation_reviews
    # ------------------------------------------------------------------
    op.create_table(
        "moderation_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("photo_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("tier", sa.String(length=8), nullable=True),
        sa.Column("suggested_tier", sa.String(length=8), nullable=True),
        sa.Column("rules", sa.JSON(), nullable=True),
        sa.Column("prefilter", sa.JSON(), nullable=True),
        sa.Column("escalation", sa.JSON(), nullable=True),
        sa.Column("final_decision", sa.String(length=20), nullable=True),
        sa.Column("final_tier", sa.String(length=8), nullable=True),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["photo_id"], ["photos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_moderation_reviews_photo_id", "moderation_reviews", ["photo_id"])
    op.create_index("ix_moderation_reviews_status", "moderation_reviews", ["status"])
    op.create_index("ix_moderation_reviews_tier", "moderation_reviews", ["tier"])
    op.create_index("ix_moderation_reviews_reviewer_id", "moderation_reviews", ["reviewer_id"])
    op.create_index("ix_moderation_reviews_created_at", "moderation_reviews", ["created_at"])
    op.create_index(
        "ix_moderation_reviews_photo_created", "moderation_reviews", ["photo_id", "created_at"]
    )
    op.create_index(
        "ix_moderation_reviews_status_tier", "moderation_reviews", ["status", "tier"]
    )

    # ------------------------------------------------------------------
    # 2. ai_usage_events
    # ------------------------------------------------------------------
    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=True),
        sa.Column("ref_type", sa.String(length=50), nullable=True),
        sa.Column("ref_id", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_events_operation", "ai_usage_events", ["operation"])
    op.create_index("ix_ai_usage_events_created_at", "ai_usage_events", ["created_at"])
    op.create_index("ix_ai_usage_events_op_created", "ai_usage_events", ["operation", "created_at"])
    op.create_index("ix_ai_usage_events_ref", "ai_usage_events", ["ref_type", "ref_id"])

    # ------------------------------------------------------------------
    # 3. agent_search_traces
    # ------------------------------------------------------------------
    op.create_table(
        "agent_search_traces",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("intent", sa.JSON(), nullable=True),
        sa.Column("facets", sa.JSON(), nullable=True),
        sa.Column("steps", sa.JSON(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clarify", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("model_id", sa.String(length=120), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_search_traces_trace_id", "agent_search_traces", ["trace_id"], unique=True)
    op.create_index("ix_agent_search_traces_created_at", "agent_search_traces", ["created_at"])
    op.create_index("ix_agent_search_traces_created", "agent_search_traces", ["created_at"])

    if not _is_postgresql():
        return

    # ------------------------------------------------------------------
    # 4. PostgreSQL：pg_trgm + 中文分词检索列
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_index(
        "ix_photos_title_trgm",
        "photos",
        ["title"],
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_photos_description_trgm",
        "photos",
        ["description"],
        postgresql_using="gin",
        postgresql_ops={"description": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_tags_name_trgm",
        "tags",
        ["name"],
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )

    op.add_column("photos", sa.Column("search_tokens", sa.Text(), nullable=True, comment="应用层中文二元组分词结果"))
    op.add_column(
        "photos",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', coalesce(search_tokens, ''))", persisted=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_photos_search_vector",
        "photos",
        ["search_vector"],
        postgresql_using="gin",
    )
    op.create_index("ix_photos_status_created", "photos", ["status", "created_at"])
    op.create_index("ix_photos_captured_at", "photos", ["captured_at"])


def downgrade() -> None:
    if _is_postgresql():
        op.drop_index("ix_photos_captured_at", table_name="photos")
        op.drop_index("ix_photos_status_created", table_name="photos")
        op.drop_index("ix_photos_search_vector", table_name="photos")
        op.drop_column("photos", "search_vector")
        op.drop_column("photos", "search_tokens")
        op.drop_index("ix_tags_name_trgm", table_name="tags")
        op.drop_index("ix_photos_description_trgm", table_name="photos")
        op.drop_index("ix_photos_title_trgm", table_name="photos")
        # 扩展保留（可能被其它模块使用），不主动 DROP EXTENSION

    op.drop_index("ix_agent_search_traces_created", table_name="agent_search_traces")
    op.drop_index("ix_agent_search_traces_created_at", table_name="agent_search_traces")
    op.drop_index("ix_agent_search_traces_trace_id", table_name="agent_search_traces")
    op.drop_table("agent_search_traces")

    op.drop_index("ix_ai_usage_events_ref", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_op_created", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_created_at", table_name="ai_usage_events")
    op.drop_index("ix_ai_usage_events_operation", table_name="ai_usage_events")
    op.drop_table("ai_usage_events")

    op.drop_index("ix_moderation_reviews_status_tier", table_name="moderation_reviews")
    op.drop_index("ix_moderation_reviews_photo_created", table_name="moderation_reviews")
    op.drop_index("ix_moderation_reviews_created_at", table_name="moderation_reviews")
    op.drop_index("ix_moderation_reviews_reviewer_id", table_name="moderation_reviews")
    op.drop_index("ix_moderation_reviews_tier", table_name="moderation_reviews")
    op.drop_index("ix_moderation_reviews_status", table_name="moderation_reviews")
    op.drop_index("ix_moderation_reviews_photo_id", table_name="moderation_reviews")
    op.drop_table("moderation_reviews")
