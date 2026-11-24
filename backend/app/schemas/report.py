"""举报 / 侵权投诉的请求与响应模型。"""
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.report import REPORT_REASON_LABELS


ReportReasonCode = Literal["copyright", "portrait", "illegal", "misinformation", "spam", "other"]
ReportTargetType = Literal["photo", "collection"]
ReportDecision = Literal["accept", "reject"]
ReportAction = Literal["takedown", "none"]


class ReportCreate(BaseModel):
    """匿名或登录用户都能提交。"""

    target_type: ReportTargetType
    target_id: str = Field(..., min_length=1, max_length=64)
    reason_code: ReportReasonCode
    reason_text: str = Field(..., min_length=5, max_length=2000, description="请说明具体问题，至少 5 个字")
    contact: Optional[str] = Field(None, max_length=200, description="邮箱/微信等，便于我们回复处理结果")

    @field_validator("reason_text")
    @classmethod
    def _strip_reason(cls, value: str) -> str:
        text = value.strip()
        if len(text) < 5:
            raise ValueError("请说明具体问题，至少 5 个字")
        return text


class ReportReceipt(BaseModel):
    ok: bool = True
    id: str
    status: str = "pending"
    message: str = "投诉已提交，我们会在 3 个工作日内受理"


class ReportReporterBrief(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None


class ReportAdminOut(BaseModel):
    id: str
    target_type: str
    target_id: str
    target_title: Optional[str] = None
    target_url: Optional[str] = None
    reason_code: str
    reason_label: str
    reason_text: Optional[str] = None
    contact: Optional[str] = None
    reporter: Optional[ReportReporterBrief] = None
    reporter_ip: Optional[str] = None
    status: str
    handled_by: Optional[str] = None
    handled_at: Optional[datetime] = None
    resolution_note: Optional[str] = None
    action_taken: Optional[str] = None
    created_at: datetime

    @staticmethod
    def reason_label_for(code: str) -> str:
        return REPORT_REASON_LABELS.get(code, code)


class ReportListResponse(BaseModel):
    items: list[ReportAdminOut]
    total: int
    limit: int
    offset: int


class ReportResolveRequest(BaseModel):
    decision: ReportDecision
    note: Optional[str] = Field(None, max_length=1000)
    action: ReportAction = "none"


class ReportResolveResponse(BaseModel):
    ok: bool = True
    id: str
    status: str
    action_taken: Optional[str] = None


class ReportStats(BaseModel):
    total: int
    pending: int
    accepted: int
    rejected: int
    by_reason: dict[str, int] = Field(default_factory=dict)
    last_7_days: int = 0
