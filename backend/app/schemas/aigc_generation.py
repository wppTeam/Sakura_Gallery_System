"""站内 AI 生图（AI 创作台）请求 / 响应模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AigcSizeOption(BaseModel):
    """一个尺寸档位。"""

    key: str
    label: str
    width: int
    height: int
    ratio: str


class AigcQuotaResponse(BaseModel):
    """当前用户的生图额度：每日基础 + 管理员赠送池。"""

    unlimited: bool = False
    daily_limit: int = 0
    daily_used: int = 0
    daily_remaining: int = 0
    bonus_total: int = 0
    bonus_used: int = 0
    bonus_remaining: int = 0
    total_remaining: int = 0


class AigcConfigResponse(BaseModel):
    """创作台配置：前端据此渲染尺寸选择与额度提示。"""

    enabled: bool
    model: str
    sizes: list[AigcSizeOption]
    prompt_max: int = 300
    daily_limit: int
    est_seconds: int = 60


class AigcGenerationCreate(BaseModel):
    """发起一次生成。"""

    prompt: str = Field(..., min_length=2, max_length=300)
    size: str = Field("square", description="尺寸档位：square / landscape / portrait")


class AigcGenerationResponse(BaseModel):
    """生成任务状态。"""

    id: str
    prompt: str
    size: str
    width: Optional[int] = None
    height: Optional[int] = None
    status: Literal["queued", "running", "succeeded", "failed"]
    model: str
    quota_source: Literal["daily", "bonus", "unlimited"] = "daily"
    image_url: Optional[str] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None
    cost_usd: float = 0.0
    created_at: datetime
    finished_at: Optional[datetime] = None


class AigcGenerationListResponse(BaseModel):
    items: list[AigcGenerationResponse]
    total: int
    quota: AigcQuotaResponse
