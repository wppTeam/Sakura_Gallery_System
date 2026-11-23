"""审核即打标（auto_tagging）测试。

覆盖：

1. 模型输出的脏数据（重复/超长/噪音/黑名单/数组 facet）在归一化阶段被收敛；
2. 分类目录从平台 taxonomy 种子生成，且只含 active + selectable 节点；
3. ``apply_prefilter_tags`` 会把标签落成 ``tags``/``photo_tags``、把 facets 解析成
   ``photo_classifications`` 并同步 legacy 的 ``photo.season`` / ``photo.campus``；
4. 重复调用幂等（不重复加关联、不重复加 usage_count）；
5. 无法解析的 facet 值安静跳过；
6. 审核流水线（``moderate_photo``）在快筛返回打标字段时落库，并把摘要写进
   ``review.rules["auto_tagging"]``。
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core import config as app_config
from app.models import ModerationReview, Photo, PhotoTag, Tag
from app.models.taxonomy import PhotoClassification
from app.services import auto_tagging, moderation_rules
from app.services import moderation as moderation_service
from app.services.ai_client import AIJSONResult
from app.services.taxonomy import ensure_default_taxonomy


def _photo(photo_id: str = "p-auto", *, status: str = "pending") -> Photo:
    return Photo(
        id=photo_id,
        uploader_id="owner",
        filename=f"{photo_id}.jpg",
        title="樱花小径",
        author="王海翔",
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=1200,
        height=800,
        file_size=200_000,
        mime_type="image/jpeg",
        status=status,
        processing_status="completed",
        views=0,
    )


@pytest.fixture()
def auto_tag_db(tmp_path: Path):
    """每个用例一个独立 SQLite 文件 + 平台默认 taxonomy 种子。"""
    import asyncio

    database_path = tmp_path / "auto_tag.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _bootstrap() -> None:
        from app.core.database import Base

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            await ensure_default_taxonomy(session)
            await session.commit()

    asyncio.run(_bootstrap())
    auto_tagging.clear_catalog_cache()
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())
        auto_tagging.clear_catalog_cache()


def _run(coro):
    import asyncio

    return asyncio.run(coro)


# ---------------------------------------------------------------- 归一化 ----


def test_normalize_suggestions_cleans_model_output():
    raw = {
        "caption": "  一棵盛开的樱花树，树下有自行车。" + "很长的补充" * 40,
        "tags": ["樱花", "樱花", "校园 春天", "摄影", "照片", "《北化》", "", "x" * 30],
        "facets": {
            "season": "春季",
            "campus": ["昌平校区"],
            "photo_type": "不确定",
            "plant": None,
            "unknown_facet": "忽略",
            "landscape": "   ",
        },
    }
    out = auto_tagging.normalize_suggestions(raw, max_tags=6)

    assert out["tags"] == ["樱花", "校园 春天", "北化"]
    assert out["facets"] == {"season": "春季", "campus": "昌平校区"}
    assert out["caption"].startswith("一棵盛开的樱花树")

    # 非 dict / 空值不抛异常
    assert auto_tagging.normalize_suggestions(None)["tags"] == []
    assert auto_tagging.normalize_suggestions({"tags": "单标签"})["tags"] == ["单标签"]


# ---------------------------------------------------------------- 目录 ----


def test_build_taxonomy_catalog_lists_seeded_facets(auto_tag_db):
    async def _check():
        async with auto_tag_db() as session:
            catalog = await auto_tagging.build_taxonomy_catalog(session)
        return catalog

    catalog = _run(_check())
    assert "- 季节(season)：春季 / 夏季 / 秋季 / 冬季" in catalog
    assert "- 校区(campus)：" in catalog
    assert "北化八景" in catalog or "景观/地点(landscape)" in catalog
    # 只列白名单 facet，不把 facility / documentary_topic 带进来
    assert "设施(facility)" not in catalog


# ---------------------------------------------------------- 落库 + 幂等 ----


def test_apply_prefilter_tags_writes_relations(auto_tag_db):
    async def _check():
        async with auto_tag_db() as session:
            photo = _photo()
            session.add(photo)
            await session.commit()

            summary = await auto_tagging.apply_prefilter_tags(
                session,
                photo,
                {
                    "caption": "春天教学楼前的樱花",
                    "tags": ["樱花", "校园", "摄影"],
                    "facets": {"season": "春季", "campus": "昌平校区", "plant": "不存在植物"},
                },
            )
            await session.commit()

            tags = (await session.execute(select(Tag.name).order_by(Tag.name))).scalars().all()
            links = (
                await session.execute(select(func.count()).select_from(PhotoTag))
            ).scalar_one()
            classifications = (
                await session.execute(select(func.count()).select_from(PhotoClassification))
            ).scalar_one()
            await session.refresh(photo)
            return summary, list(tags), links, classifications, photo

    summary, tags, links, classifications, photo = _run(_check())
    assert summary["applied"] is True
    assert set(summary["tags"]) == {"樱花", "校园"}  # 「摄影」是黑名单噪音
    assert summary["facets"] == {"season": "春季", "campus": "昌平校区"}
    assert tags == ["校园", "樱花"]
    assert links == 2
    assert classifications == 2
    # legacy 字段同步（旧枚举保留英文：Spring/Summer/Autumn/Winter）
    assert photo.season == "Spring"
    assert photo.campus == "昌平校区"
    assert photo.exif_data["_ai_caption"] == "春天教学楼前的樱花"
    assert photo.exif_data["_ai_tagging"]["tags"] == ["樱花", "校园"]

    # 第二次调用幂等：不新增关联/分类，usage_count 不变
    async def _again():
        async with auto_tag_db() as session:
            photo2 = await session.get(Photo, photo.id)
            before_usage = (
                await session.execute(select(Tag.usage_count).order_by(Tag.name))
            ).scalars().all()
            summary2 = await auto_tagging.apply_prefilter_tags(
                session,
                photo2,
                {"tags": ["樱花", "校园"], "facets": {"season": "春季", "campus": "昌平校区"}},
            )
            await session.commit()
            links2 = (
                await session.execute(select(func.count()).select_from(PhotoTag))
            ).scalar_one()
            classes2 = (
                await session.execute(select(func.count()).select_from(PhotoClassification))
            ).scalar_one()
            after_usage = (
                await session.execute(select(Tag.usage_count).order_by(Tag.name))
            ).scalars().all()
            return summary2, links2, classes2, before_usage, after_usage

    summary2, links2, classes2, before_usage, after_usage = _run(_again())
    assert summary2["applied"] is False
    assert summary2["tags"] == []
    assert summary2["facets"] == {"season": "春季", "campus": "昌平校区"}
    assert links2 == 2
    assert classes2 == 2
    assert list(before_usage) == list(after_usage)


def test_unknown_facet_value_is_skipped(auto_tag_db):
    async def _check():
        async with auto_tag_db() as session:
            photo = _photo("p-unknown")
            session.add(photo)
            await session.commit()
            summary = await auto_tagging.apply_prefilter_tags(
                session,
                photo,
                {"facets": {"landscape": "根本不存在的景观", "season": "春季"}},
            )
            await session.commit()
            classifications = (
                await session.execute(select(func.count()).select_from(PhotoClassification))
            ).scalar_one()
            return summary, classifications

    summary, classifications = _run(_check())
    assert summary["facets"] == {"season": "春季"}
    assert classifications == 1


# -------------------------------------------------------------- 流水线 ----


def test_moderate_photo_persists_auto_tags(auto_tag_db, monkeypatch):
    """快筛带打标字段时，审核流水线把标签落库并写入审核记录（不额外调模型）。"""

    async def _fake_rules(db, photo):
        return moderation_rules.RuleResult(checked=True)

    async def _fake_image(photo):
        return None, "image/jpeg"

    async def _fake_chat(db=None, **kwargs):
        return AIJSONResult(
            data={
                "has_identifiable_person": False,
                "likely_aigc": False,
                "sensitive_content": False,
                "copyright_risk": "none",
                "watermark": False,
                "text_in_image": False,
                "suggested_tier": "L0",
                "confidence": 0.95,
                "reason": "普通校园风景",
                "caption": "春日教学楼前的樱花与自行车",
                "tags": ["樱花", "校园", "春天"],
                "facets": {"season": "春季", "campus": "昌平校区", "photo_type": "自然生态"},
            },
            text="{}",
            provider="fake",
            model_id="fake-vlm",
        )

    monkeypatch.setattr(moderation_rules, "run_rules", _fake_rules)
    monkeypatch.setattr(moderation_service, "_load_image_for_ai", _fake_image)
    monkeypatch.setattr(moderation_service, "chat_json", _fake_chat)
    monkeypatch.setattr(app_config.get_settings(), "MODERATION_AUTO_TAGGING", True)
    monkeypatch.setattr(app_config.get_settings(), "MODERATION_AUTO_APPROVE_L0", True)

    async def _check():
        async with auto_tag_db() as session:
            photo = _photo("p-pipeline")
            session.add(photo)
            await session.commit()
            review = await moderation_service.moderate_photo(session, photo)
            await session.commit()
            links = (
                await session.execute(select(func.count()).select_from(PhotoTag))
            ).scalar_one()
            await session.refresh(photo)
            # 直接从数据库读回 rules（JSON 列必须真的落库，不能只在 identity map 里可见）
            stored_rules = (
                await session.execute(
                    select(ModerationReview.rules).where(
                        ModerationReview.id == review.id
                    )
                )
            ).scalar_one()
            review.rules = stored_rules
            return review, links, photo

    review, links, photo = _run(_check())
    assert review.status == "completed"
    assert "auto_tagging" in review.rules, sorted(review.rules)
    assert review.rules["auto_tagging"]["applied"] is True
    assert review.rules["auto_tagging"]["facets"]["season"] == "春季"
    assert links == 3
    # L0 + 高置信度 + 非 AIGC → 免审即发
    assert photo.status == "approved"
    assert photo.published_at is not None
    assert photo.season == "Spring"
