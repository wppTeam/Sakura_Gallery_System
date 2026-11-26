"""公开创作者主页的响应模型。

隐私约定：这里只暴露 username / display_name（以及由公开作品聚合出的计数），
绝不包含 student_id、email、full_name 等身份信息。
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.photo import PhotoNeighborItem, PhotoResponse


class CreatorProfile(BaseModel):
    username: str
    display_name: Optional[str] = None
    bio: Optional[str] = None
    avatar_url: Optional[str] = None
    joined_at: Optional[datetime] = None
    works_count: int = 0
    views_total: int = 0
    favorites_total: int = 0
    collections_count: int = 0


class CreatorWorkList(BaseModel):
    items: list[PhotoResponse] = Field(default_factory=list)
    total: int = 0
    limit: int = 12
    offset: int = 0


class CreatorCollectionCard(BaseModel):
    slug: str
    title: str
    subtitle: Optional[str] = None
    photo_count: int = 0
    cover: Optional[PhotoResponse] = None


class CreatorResponse(BaseModel):
    profile: CreatorProfile
    works: CreatorWorkList
    collections: list[CreatorCollectionCard] = Field(default_factory=list)


class CreatorCard(BaseModel):
    """创作者名录卡片：资料 + 聚合计数 + 最多 3 张作品封面。"""

    username: str
    display_name: Optional[str] = None
    joined_at: Optional[datetime] = None
    works_count: int = 0
    views_total: int = 0
    covers: list[PhotoNeighborItem] = Field(default_factory=list)


class CreatorListResponse(BaseModel):
    items: list[CreatorCard] = Field(default_factory=list)
    total: int = 0
    limit: int = 12
    offset: int = 0
