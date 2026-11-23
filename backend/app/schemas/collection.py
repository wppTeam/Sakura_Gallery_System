"""策展专题（album）响应模型。

公开接口只返回已发布专题；作品仍复用 `PhotoResponse`（含 LQIP / 响应式变体 /
AIGC 标识等公开字段），保证前端与列表页一致。
"""

from pydantic import BaseModel, ConfigDict

from app.schemas.photo import PhotoResponse


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
