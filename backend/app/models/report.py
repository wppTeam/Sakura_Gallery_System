"""
内容举报 / 侵权投诉模型

公开站点需要「通知—删除」渠道（《信息网络传播权保护条例》《民法典》第 1195 条）：
任何访客都可以对作品提出侵权/肖像/违规投诉，站方在管理后台受理并决定是否下架。

设计要点：
- 匿名也可提交（contact 字段留联系方式），登录用户会记录 reporter_id
- 只保存投诉文本，不保存原始证据文件；证据可通过 contact 后续沟通
- 受理结果写 reports 行，同时必须写 audit_logs（谁在何时下架了什么）
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


#: 投诉原因码 → 中文说明（前端展示与校验共用）
REPORT_REASON_LABELS = {
    "copyright": "侵犯著作权 / 未经授权转载",
    "portrait": "侵犯肖像权 / 未获被摄者同意",
    "illegal": "违法违规内容",
    "misinformation": "虚假信息 / 误导性内容",
    "spam": "垃圾广告 / 引流",
    "other": "其他问题",
}

REPORT_STATUSES = ("pending", "accepted", "rejected")
REPORT_TARGET_TYPES = ("photo", "collection")


class Report(Base):
    """
    内容举报 / 侵权投诉

    Attributes:
        target_type: photo | collection
        target_id: 被投诉对象 ID
        reason_code: REPORT_REASON_LABELS 的键
        reason_text: 投诉人补充说明
        contact: 投诉人联系方式（邮箱/微信等，可选；匿名投诉时建议填写）
        status: pending | accepted | rejected
        handled_by: 处理人（admin/auditor）
        resolution_note: 处理说明（对外可不展示，仅内部留痕）
        action_taken: 实际处置，如 photo.takedown / none
    """

    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    target_type = Column(String(20), nullable=False, comment="photo|collection")
    target_id = Column(String(36), nullable=False, comment="被投诉对象ID")
    reason_code = Column(String(32), nullable=False, comment="投诉原因码")
    reason_text = Column(Text, nullable=True, comment="投诉人补充说明")
    contact = Column(String(200), nullable=True, comment="投诉人联系方式（可选）")

    reporter_id = Column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reporter_ip = Column(String(45), nullable=True, comment="提交IP（限流与滥用排查）")

    status = Column(String(16), nullable=False, default="pending", index=True)
    handled_by = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    handled_at = Column(DateTime, nullable=True)
    resolution_note = Column(Text, nullable=True, comment="处理说明")
    action_taken = Column(String(50), nullable=True, comment="如 photo.takedown")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    reporter = relationship("User", foreign_keys=[reporter_id], lazy="selectin")
    handler = relationship("User", foreign_keys=[handled_by], lazy="selectin")

    __table_args__ = (
        Index("ix_reports_status_created", "status", "created_at"),
        Index("ix_reports_target", "target_type", "target_id"),
    )

    def __repr__(self):
        return (
            f"<Report(target={self.target_type}:{self.target_id}, "
            f"reason={self.reason_code}, status={self.status})>"
        )
