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


# ── 光的一日（按时段自动策展）────────────────────────────────────────


class LightPeriodResponse(BaseModel):
    """单个光时段：晨 / 昼 / 暮 / 夜。

    `photos` 只含已发布且非敏感作品（公开序列化），最多 `per_period` 张；
    没有专题或专题为空时 `photos=[]`、`photo_count=0`，前端据此展示「整理中」。
    """

    key: str
    slug: str
    label: str
    time_range: str
    title: str
    subtitle: str | None = None
    intro: str | None = None
    photo_count: int = 0
    photos: list[PhotoResponse] = Field(default_factory=list)


class LightPeriodsResponse(BaseModel):
    periods: list[LightPeriodResponse]
    total: int


# ── AI 策展助手（一句话从自己的作品里挑一组）────────────────────────


class CuratorAssistRequest(BaseModel):
    """作者的一句话策展主题，例如「雨天的校园」「黄昏的操场」。"""

    prompt: str = Field(..., min_length=2, max_length=200)


class CuratorPickItem(BaseModel):
    photo: PhotoResponse
    reason: str | None = None


class CuratorAssistResponse(BaseModel):
    """只读提案：前端确认后才创建专辑，不会自动落库。"""

    title: str
    subtitle: str | None = None
    description: str | None = None
    photo_ids: list[str] = Field(default_factory=list)
    picks: list[CuratorPickItem] = Field(default_factory=list)
    note: str | None = None
    candidates: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    model_id: str | None = None
