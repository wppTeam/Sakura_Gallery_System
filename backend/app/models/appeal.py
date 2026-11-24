"""
审核复核（申诉）模型

被驳回的作品，作者可以提交一次复核申请；管理员/审核员受理后：
- 接受 → 作品回到 pending，重新进入审核流程（AI 审核 + 人工终判）；
- 驳回 → 保持 rejected，并告知作者结论。

设计要点：
- 仅作者本人可对自己的 rejected 作品发起；
- 同一作品同时只允许一条 pending 申请（代码层校验，SQLite 测试也可覆盖）；
- 受理必须写 audit_logs；作者通过站内通知获知结果。
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


APPEAL_STATUSES = ("pending", "accepted", "rejected")


class PhotoAppeal(Base):
    """
    审核复核申请

    Attributes:
        photo_id: 被驳回的作品
        user_id: 发起人（必须等于 photo.uploader_id）
        reason: 作者陈述（为什么认为驳回有误 / 补交说明）
        status: pending | accepted | rejected
        handled_by: 受理人（admin/auditor）
        note: 受理结论说明（接受原因/驳回原因，会展示给作者）
    """

    __tablename__ = "photo_appeals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    photo_id = Column(
        String(36), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason = Column(Text, nullable=False, comment="作者申诉理由")

    status = Column(String(16), nullable=False, default="pending", index=True)
    handled_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at = Column(DateTime, nullable=True)
    note = Column(Text, nullable=True, comment="受理结论说明")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    photo = relationship("Photo", lazy="selectin")
    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    handler = relationship("User", foreign_keys=[handled_by], lazy="selectin")

    __table_args__ = (
        Index("ix_photo_appeals_status_created", "status", "created_at"),
        Index("ix_photo_appeals_photo_status", "photo_id", "status"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<PhotoAppeal(photo_id='{self.photo_id}', status='{self.status}')>"
