"""策展专题（album）响应模型。

公开接口只返回已发布专题；作品仍复用 `PhotoResponse`（含 LQIP / 响应式变体 /
AIGC 标识等公开字段），保证前端与列表页一致。
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.photo import PhotoResponse


class CollectionOwnerBrief(BaseModel):
    """公开作者信息（username / display_name，绝不包含学号或真实姓名）。"""

    username: str | None = None
    display_name: str | None = None


class CollectionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    title: str
    subtitle: str | None = None
    kind: str = "editorial"
    sort_order: int = 0
    photo_count: int = 0
    cover: PhotoResponse | None = None
    status: str = "published"
    owner: CollectionOwnerBrief | None = None


class CollectionListResponse(BaseModel):
    items: list[CollectionSummary]
    total: int
    limit: int
    offset: int


class CollectionDetail(BaseModel):
    id: str
    slug: str
    title: str
    subtitle: str | None = None
    description: str | None = None
    kind: str = "editorial"
    sort_order: int = 0
    photo_count: int = 0
    cover: PhotoResponse | None = None
    photos: list[PhotoResponse] = []
    prev_slug: str | None = None
    next_slug: str | None = None
    status: str = "published"
    owner: CollectionOwnerBrief | None = None


# ── 作者手账（用户自建专辑）请求模型 ─────────────────────────────────


class CollectionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    subtitle: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)


class CollectionUpdate(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=120)
    subtitle: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=5000)
    cover_photo_id: str | None = Field(None, max_length=36)
    status: Literal["published", "draft"] | None = None


class CollectionPhotosUpdate(BaseModel):
    """整体替换专辑作品顺序；最多 100 件，只能放本人已审核作品。"""

    photo_ids: list[str] = Field(default_factory=list, max_length=100)


class CollectionMineResponse(BaseModel):
    items: list[CollectionSummary]
    total: int


# ── 樱色光谱（按主色自动策展）────────────────────────────────────────


class SpectrumSwatch(BaseModel):
    key: str
    name: str
    hex: str
    description: str
    slug: str | None = None
    photo_count: int = 0
    cover: PhotoResponse | None = None


class SpectrumResponse(BaseModel):
    palettes: list[SpectrumSwatch]
    total: int
