"""AI 策展助手（一句话挑作品）测试。

覆盖：
1. 短编号解析：``P02`` / ``p2`` 都能映射，未知编号与重复编号被丢弃，顺序保留；
2. 目录只含作者本人已通过、非敏感作品（待审、他人、敏感作品不进模型上下文）；
3. 模型输出经规范化：标题/副标题/简介裁剪，picks 数量与顺序正确；
4. 没有作品时返回空提案（接口 400 引导投稿）；
5. 接口鉴权（401）、AI 失败降级 503、限流路径不抛 500。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.v1.endpoints import collections as collections_api
from app.core import deps
from app.core.database import Base
from app.models import Photo, Tag, User
from app.services import curation_assistant
from app.services.ai_client import AIError, AIJSONResult


def _photo(
    photo_id: str,
    *,
    title: str,
    uploader: str = "owner",
    status: str = "approved",
    sensitive: bool = False,
    hour: int | None = 17,
    published_hour: int = 10,
) -> Photo:
    exif: dict[str, Any] = {}
    if title.startswith("黄昏"):
        exif["_ai_caption"] = "夕阳把操场照成金色，人影被拉长"
    return Photo(
        id=photo_id,
        uploader_id=uploader,
        filename=f"{photo_id}.jpg",
        title=title,
        original_path=f"originals/{photo_id}.jpg",
        thumb_path=f"thumbnails/{photo_id}_thumb.jpg",
        width=1200,
        height=800,
        file_size=200_000,
        mime_type="image/jpeg",
        status=status,
        processing_status="completed",
        privacy_level="sensitive" if sensitive else "normal",
        season="Spring",
        campus="昌平校区",
        captured_at=datetime(2025, 4, 18, hour) if hour else None,
        published_at=datetime(2025, 4, 20, published_hour, 0),
        exif_data=exif,
        views=0,
    )


def _ai_result(data: dict[str, Any]) -> AIJSONResult:
    return AIJSONResult(
        data=data,
        text="",
        provider="test",
        model_id="deepseek-v4.1-flash-1017",
        prompt_tokens=900,
        completion_tokens=120,
        total_tokens=1020,
        cost_usd=0.0004,
        latency_ms=1234,
    )


@pytest.fixture()
def assistant_env(tmp_path: Path):
    db_path = tmp_path / "assistant.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path.as_posix()}", future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    owner = User(
        id="owner",
        student_id="20260001",
        username="jackwpp",
        display_name="王海翔",
        full_name="真实姓名不该公开",
        hashed_password="x",
        role="user",
        is_active=True,
    )
    other = User(
        id="other",
        student_id="20260002",
        username="viewer",
        display_name="路人",
        hashed_password="x",
        role="user",
        is_active=True,
    )

    async def init_database() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add_all([owner, other])
            session.add_all(
                [
                    _photo("p1", title="黄昏的操场", published_hour=12),
                    _photo("p2", title="雨后的教学楼", hour=13, published_hour=11),
                    _photo("p3", title="黄昏 · 宿舍楼下", published_hour=10),
                    _photo("p4", title="待审作品", status="pending"),
                    _photo("p5", title="他人作品", uploader="other"),
                    _photo("p6", title="人像作品", sensitive=True),
                ]
            )
            session.add_all([Tag(name="黄昏"), Tag(name="操场"), Tag(name="雨后")])
            await session.commit()
            # 给 p1/p3 打上黄昏标签
            from sqlalchemy import select

            from app.models.tag import PhotoTag

            tag_rows = (await session.execute(select(Tag))).scalars().all()
            tag_by_name = {tag.name: tag for tag in tag_rows}
            session.add_all(
                [
                    PhotoTag(photo_id="p1", tag_id=tag_by_name["黄昏"].id),
                    PhotoTag(photo_id="p3", tag_id=tag_by_name["黄昏"].id),
                    PhotoTag(photo_id="p2", tag_id=tag_by_name["雨后"].id),
                ]
            )
            await session.commit()

    asyncio.run(init_database())

    async def override_db():
        async with session_factory() as session:
            yield session

    api = FastAPI()
    api.include_router(collections_api.router, prefix="/api/v1/collections")
    api.dependency_overrides[deps.get_db] = override_db

    async def override_current_user():
        return owner

    api.dependency_overrides[deps.get_current_user] = override_current_user

    client = TestClient(api)
    client.owner = owner  # type: ignore[attr-defined]
    client.other = other  # type: ignore[attr-defined]
    client.session_factory = session_factory  # type: ignore[attr-defined]
    yield client
    asyncio.run(engine.dispose())


def _run(coro):
    return asyncio.run(coro)


def _seed_session(client, coro_factory):
    async def _run_it():
        async with client.session_factory() as db:
            return await coro_factory(db)

    return asyncio.run(_run_it())


def test_normalize_picks_maps_refs_and_dedupes() -> None:
    photos = {f"p{i}": _photo(f"p{i}", title=f"t{i}") for i in range(1, 4)}
    by_ref = {"P01": photos["p1"], "P02": photos["p2"], "P03": photos["p3"]}
    picks = curation_assistant._normalize_picks(
        {
            "picks": [
                {"ref": "P02", "reason": "起势"},
                {"ref": "p1", "reason": "展开"},
                {"ref": "P02", "reason": "重复"},
                {"ref": "P99", "reason": "不存在"},
                {"ref": "abc", "reason": "非法"},
            ]
        },
        by_ref,
    )
    assert [str(p.photo.id) for p in picks] == ["p2", "p1"]
    assert [p.reason for p in picks] == ["起势", "展开"]
    assert curation_assistant._normalize_picks({"picks": "oops"}, by_ref) == []
    assert curation_assistant._normalize_picks({}, by_ref) == []


def test_propose_collection_excludes_pending_others_and_sensitive(assistant_env) -> None:
    captured: dict[str, str] = {}

    async def fake_chat_json(db=None, **kwargs):
        captured["user"] = kwargs.get("user", "")
        captured["system"] = kwargs.get("system", "")
        captured["operation"] = kwargs.get("operation", "")
        return _ai_result(
            {
                "title": " 黄昏散场以后 ",
                "subtitle": " 一天里最软的一小时 ",
                "description": " 从操场到宿舍楼下，光一点点收起来。 ",
                "picks": [
                    {"ref": "P01", "reason": "开场"},
                    {"ref": "P02", "reason": "收束"},
                ],
                "note": "",
            }
        )

    async def call(db):
        return await curation_assistant.propose_collection(db, assistant_env.owner, "黄昏的校园")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(curation_assistant, "chat_json", fake_chat_json)
        proposal = _seed_session(assistant_env, call)

    assert proposal.candidates == 3  # p1/p2/p3；p4 pending、p5 他人、p6 敏感 排除
    assert proposal.title == "黄昏散场以后"
    assert proposal.subtitle == "一天里最软的一小时"
    assert proposal.description == "从操场到宿舍楼下，光一点点收起来。"
    assert [str(p.photo.id) for p in proposal.picks] == ["p1", "p2"]
    assert proposal.cost_usd == pytest.approx(0.0004)
    assert captured["operation"] == "collection.assist"
    prompt = captured["user"]
    assert "黄昏的校园" in prompt
    assert "P01 |" in prompt
    assert "标签：黄昏" in prompt
    assert "夕阳把操场照成金色" in prompt  # AI caption 进目录
    assert "待审作品" not in prompt
    assert "他人作品" not in prompt
    assert "人像作品" not in prompt
    # 候选按上线时间倒序 → p1 是 P01
    assert "P01 | 黄昏的操场" in prompt


def test_propose_collection_without_photos_returns_empty(tmp_path: Path) -> None:
    async def _noop():
        raise AssertionError("不应调用模型")

    # 直接构造空用户：SQLite 引擎里没有作品时返回空提案
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def _run_case(db_path: Path):
        engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            async with session_factory() as db:
                user = User(
                    id="lonely",
                    student_id="20260009",
                    username="lonely",
                    display_name="空账号",
                    hashed_password="x",
                    role="user",
                    is_active=True,
                )
                db.add(user)
                await db.commit()
                return await curation_assistant.propose_collection(db, user, "随便看看")
        finally:
            await engine.dispose()

    proposal = asyncio.run(_run_case(tmp_path / "curation-empty.db"))
    assert proposal.candidates == 0
    assert proposal.picks == []


def test_assistant_endpoint_returns_proposal(assistant_env) -> None:
    async def fake_chat_json(db=None, **kwargs):
        return _ai_result(
            {
                "title": "黄昏之后",
                "subtitle": "光收起来之前",
                "description": "操场与宿舍楼下的两帧黄昏。",
                "picks": [
                    {"ref": "P01", "reason": "起势"},
                    {"ref": "P03", "reason": "收束"},
                ],
                "note": "只挑到两张，可以放宽主题再试。",
            }
        )

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(curation_assistant, "chat_json", fake_chat_json)
        response = assistant_env.post(
            "/api/v1/collections/assistant", json={"prompt": "黄昏的校园"}
        )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "黄昏之后"
    assert data["photo_ids"] == ["p1", "p3"]
    assert [item["reason"] for item in data["picks"]] == ["起势", "收束"]
    assert data["picks"][0]["photo"]["id"] == "p1"
    # 公开序列化：不得暴露学号 / 真实姓名
    assert data["picks"][0]["photo"]["uploader_student_id"] is None
    assert data["picks"][0]["photo"]["uploader_name"] is None
    assert data["candidates"] == 3
    assert data["cost_usd"] == pytest.approx(0.0004)
    assert data["latency_ms"] == 1234


def test_assistant_endpoint_validates_prompt(assistant_env) -> None:
    assert assistant_env.post("/api/v1/collections/assistant", json={"prompt": ""}).status_code == 422
    assert assistant_env.post("/api/v1/collections/assistant", json={}).status_code == 422
    assert (
        assistant_env.post(
            "/api/v1/collections/assistant", json={"prompt": "x" * 201}
        ).status_code
        == 422
    )


def test_assistant_endpoint_503_when_ai_fails(assistant_env) -> None:
    async def boom(db=None, **kwargs):
        raise AIError("upstream down")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(curation_assistant, "chat_json", boom)
        response = assistant_env.post(
            "/api/v1/collections/assistant", json={"prompt": "雨天的校园"}
        )

    assert response.status_code == 503
    assert "暂时不可用" in response.json()["detail"]


def test_assistant_endpoint_requires_login(assistant_env) -> None:
    api = FastAPI()
    api.include_router(collections_api.router, prefix="/api/v1/collections")
    client = TestClient(api)
    response = client.post("/api/v1/collections/assistant", json={"prompt": "雨天的校园"})
    assert response.status_code == 401
