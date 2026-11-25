"""photos.search_document：AI 画面描述等补充检索语料

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-25

背景
----
``search_tokens`` 由 trigger 从 title + description 生成，AI 快筛写下的
``exif_data["_ai_caption"]``（画面描述）此前只用于 sitemap / 分享卡，
检索不到。新增 ``search_document`` 列存「补充检索文本」（AI 描述、标签等），
trigger 把它并入分词；应用层在 AI 打标/自由标签变更后刷新该列。

只改 trigger 函数体与触发事件，已有数据做一次回填（此时 search_document
为空，等价于旧行为）。
"""
from alembic import op
import sqlalchemy as sa


revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.add_column(
        "photos",
        sa.Column(
            "search_document",
            sa.Text(),
            nullable=True,
            comment="补充检索语料（AI 画面描述/标签等，应用层维护）",
        ),
    )

    if dialect != "postgresql":
        return

    # 分词来源：title + description + search_document
    op.execute(
        """
        CREATE OR REPLACE FUNCTION sakura_photos_sync_search_tokens()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.search_tokens := sakura_search_tokens(
                coalesce(NEW.title, '') || ' ' ||
                coalesce(NEW.description, '') || ' ' ||
                coalesce(NEW.search_document, '')
            );
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute("DROP TRIGGER IF EXISTS trg_photos_search_tokens ON photos")
    op.execute(
        """
        CREATE TRIGGER trg_photos_search_tokens
        BEFORE INSERT OR UPDATE OF title, description, search_document ON photos
        FOR EACH ROW EXECUTE FUNCTION sakura_photos_sync_search_tokens();
        """
    )

    # 回填（新列刚加，值全为 NULL，等价重算一次旧语料，保证幂等）
    op.execute(
        """
        UPDATE photos
        SET search_tokens = sakura_search_tokens(
            coalesce(title, '') || ' ' ||
            coalesce(description, '') || ' ' ||
            coalesce(search_document, '')
        )
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_photos_search_tokens ON photos")
        op.execute(
            """
            CREATE OR REPLACE FUNCTION sakura_photos_sync_search_tokens()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.search_tokens := sakura_search_tokens(
                    coalesce(NEW.title, '') || ' ' || coalesce(NEW.description, '')
                );
                RETURN NEW;
            END;
            $$
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_photos_search_tokens
            BEFORE INSERT OR UPDATE OF title, description ON photos
            FOR EACH ROW EXECUTE FUNCTION sakura_photos_sync_search_tokens();
            """
        )

    op.drop_column("photos", "search_document")
