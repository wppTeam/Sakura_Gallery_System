"""后台全局搜索（admin + auditor）。

顶栏一个框搜三类对象：用户 / 作品 / 专题，分组返回，供前端做直达跳转。
auditor 也能搜，但用户结果只给公开身份（username / display_name），
学号与邮箱仅 admin 可见。
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_auditor_user, get_db
from app.models.collection import Collection, CollectionPhoto
from app.models.photo import Photo
from app.models.user import User

router = APIRouter(tags=["后台搜索"])

MAX_PER_GROUP = 8


class SearchUserHit(BaseModel):
    id: str
    username: Optional[str] = None
    display_name: Optional[str] = None
    role: str
    is_active: bool
    email: Optional[str] = None
    student_id: Optional[str] = None


class SearchPhotoHit(BaseModel):
    id: str
    title: Optional[str] = None
    status: str
    uploader_username: Optional[str] = None
    thumb_url: str


class SearchCollectionHit(BaseModel):
    slug: str
    title: str
    kind: str
    photo_count: int = 0


class AdminSearchResponse(BaseModel):
    query: str
    users: List[SearchUserHit]
    photos: List[SearchPhotoHit]
    collections: List[SearchCollectionHit]


@router.get("/search", response_model=AdminSearchResponse, summary="后台全局搜索")
async def admin_search(
    q: str = Query(..., min_length=1, max_length=60),
    limit: int = Query(5, ge=1, le=MAX_PER_GROUP),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
) -> AdminSearchResponse:
    term = q.strip()
    if not term:
        return AdminSearchResponse(query=q, users=[], photos=[], collections=[])
    like = f"%{term}%"
    is_admin = current_user.role == "admin"

    user_filters = [
        User.username.ilike(like),
        User.display_name.ilike(like),
    ]
    if is_admin:
        user_filters += [User.email.ilike(like), User.student_id.ilike(like)]
    user_rows = (
        (
            await db.execute(
                select(User).where(or_(*user_filters)).order_by(User.created_at.desc()).limit(limit)
            )
        )
        .scalars()
        .all()
    )

    photo_rows = (
        (
            await db.execute(
                select(Photo, User.username)
                .join(User, User.id == Photo.uploader_id)
                .where(
                    Photo.status != "deleted",
                    or_(Photo.title.ilike(like), Photo.filename.ilike(like), Photo.search_document.ilike(like)),
                )
                .order_by(Photo.created_at.desc())
                .limit(limit)
            )
        )
        .all()
    )

    collection_rows = (
        (
            await db.execute(
                select(Collection)
                .where(or_(Collection.title.ilike(like), Collection.slug.ilike(like)))
                .order_by(Collection.created_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    counts: dict[str, int] = {}
    if collection_rows:
        count_rows = (
            await db.execute(
                select(CollectionPhoto.collection_id, func.count(CollectionPhoto.photo_id))
                .where(CollectionPhoto.collection_id.in_([c.id for c in collection_rows]))
                .group_by(CollectionPhoto.collection_id)
            )
        ).all()
        counts = {row[0]: int(row[1]) for row in count_rows}

    return AdminSearchResponse(
        query=term,
        users=[
            SearchUserHit(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                role=user.role,
                is_active=bool(user.is_active),
                email=user.email if is_admin else None,
                student_id=user.student_id if is_admin else None,
            )
            for user in user_rows
        ],
        photos=[
            SearchPhotoHit(
                id=photo.id,
                title=photo.title,
                status=photo.status,
                uploader_username=username,
                thumb_url=f"/api/v1/photos/{photo.id}/image/thumbnail",
            )
            for photo, username in photo_rows
        ],
        collections=[
            SearchCollectionHit(
                slug=collection.slug,
                title=collection.title,
                kind=collection.kind,
                photo_count=counts.get(collection.id, 0),
            )
            for collection in collection_rows
        ],
    )