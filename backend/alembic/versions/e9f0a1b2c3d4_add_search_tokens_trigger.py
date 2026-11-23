"""add DB-level search tokenizer function + photos trigger

``search_tokens`` 由数据库 trigger 自动维护，任何写入路径（上传、导入、种子脚本、
后台管理）都不会漏掉分词；``search_vector`` 是从 ``search_tokens`` 生成的生成列，
会自动重算。

分词规则（与 ``app/services/search_text.py`` 对齐）：

- 连续 CJK 段（汉字 / 假名 / 谚文）切成**字符二元组**（长度 1 保留单字）
- 拉丁字母 / 数字段按单词小写保留
- 结果以空格连接，供 ``to_tsvector('simple', ...)`` 使用

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-11-23
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_CJK_CLASS = "一-龥ぁ-んァ-ヶ가-힣"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION sakura_search_tokens(input text)
        RETURNS text
        LANGUAGE plpgsql
        IMMUTABLE PARALLEL SAFE
        AS $$
        DECLARE
            parts text[] := ARRAY[]::text[];
            chunk text;
            i int;
        BEGIN
            IF input IS NULL OR btrim(input) = '' THEN
                RETURN '';
            END IF;

            -- 连续 CJK 段 → 字符二元组
            FOR chunk IN
                SELECT m[1] FROM regexp_matches(input, '([{_CJK_CLASS}]+)', 'g') AS m
            LOOP
                IF length(chunk) = 1 THEN
                    parts := parts || chunk;
                ELSE
                    FOR i IN 1 .. length(chunk) - 1 LOOP
                        parts := parts || substr(chunk, i, 2);
                    END LOOP;
                END IF;
            END LOOP;

            -- 拉丁 / 数字词
            FOR chunk IN
                SELECT lower(m[1]) FROM regexp_matches(input, '([A-Za-z0-9_]+)', 'g') AS m
            LOOP
                parts := parts || chunk;
            END LOOP;

            RETURN array_to_string(parts, ' ');
        END;
        $$
        """
    )

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
        DROP TRIGGER IF EXISTS trg_photos_search_tokens ON photos;
        CREATE TRIGGER trg_photos_search_tokens
        BEFORE INSERT OR UPDATE OF title, description ON photos
        FOR EACH ROW EXECUTE FUNCTION sakura_photos_sync_search_tokens();
        """
    )

    # 已有数据回填（新库为空，保留幂等）
    op.execute(
        """
        UPDATE photos
        SET search_tokens = sakura_search_tokens(
            coalesce(title, '') || ' ' || coalesce(description, '')
        )
        WHERE search_tokens IS NULL OR search_tokens = ''
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("DROP TRIGGER IF EXISTS trg_photos_search_tokens ON photos")
    op.execute("DROP FUNCTION IF EXISTS sakura_photos_sync_search_tokens()")
    op.execute("DROP FUNCTION IF EXISTS sakura_search_tokens(text)")
