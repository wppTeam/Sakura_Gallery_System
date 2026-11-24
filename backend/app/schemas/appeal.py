"""
审核复核（申诉）相关的请求 / 响应模型
"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AppealCreate(BaseModel):
    """作者发起复核申请"""

    reason: str = Field(..., min_length=10, max_length=2000, description="申诉理由（10–2000 字）")


class AppealResponse(BaseModel):
    """作者本人 / 管理员查看的复核申请"""

    id: str
    photo_id: str
    status: Literal["pending", "accepted", "rejected"]
    reason: str
    note: Optional[str] = None
    created_at: datetime
    handled_at: Optional[datetime] = None


class AppealReceipt(BaseModel):
    """提交成功回执"""

    ok: bool = True
    id: str
    status: str
    message: str


class AppealAdminOut(BaseModel):
    """管理后台列表项"""

    id: str
    photo_id: str
    photo_title: Optional[str] = None
    thumb_url: Optional[str] = None
    uploader_username: Optional[str] = None
    uploader_display_name: Optional[str] = None
    reason: str
    status: Literal["pending", "accepted", "rejected"]
    note: Optional[str] = None
    created_at: datetime
    handled_at: Optional[datetime] = None


class AppealListResponse(BaseModel):
    items: list[AppealAdminOut]
    total: int


class AppealStats(BaseModel):
    total: int
    pending: int
    accepted: int
    rejected: int
    last_7_days: int


class AppealResolveRequest(BaseModel):
    """管理员受理复核"""

    decision: Literal["accept", "reject"]
    note: Optional[str] = Field(None, max_length=1000, description="结论说明（会通知作者）")


class AppealResolveResponse(BaseModel):
    ok: bool = True
    status: str
    message: str
