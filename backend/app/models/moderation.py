"""AI 审核结论模型。

一张照片对应多条审核记录（可重跑）：每次运行产生一条，保留规则层、
快筛 VLM、复核推理三层的原始结论与用量，供管理端展示依据、人工终判使用。

层级约定（见 AGENTS.md §4）：
- L0：免审即发
- L1：进精选/搜索加权，需人工或社区评审
- L2：涉可识别人物、疑似侵权或深伪，强制前审
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class ModerationReview(Base):
    """一次照片审核的完整结论。"""

    __tablename__ = "moderation_reviews"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    photo_id = Column(
        String(36),
        ForeignKey("photos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 运行状态：queued / running / completed / failed
    status = Column(String(20), default="queued", nullable=False, index=True)
    # Agent 合并建议级别，管理端队列按此排序：L0 / L1 / L2
    tier = Column(String(8), nullable=True, index=True)
    suggested_tier = Column(String(8), nullable=True, comment="快筛/复核给出的建议级别")

    # 三层结论（JSON，结构由各层自行定义，管理端只读展示）
    rules = Column(JSON, nullable=True, comment="规则前置层：命中列表与是否硬拦截")
    prefilter = Column(JSON, nullable=True, comment="快筛 VLM 结构化结论")
    escalation = Column(JSON, nullable=True, comment="复核推理结论（仅难例）")

    # 人工终判
    final_decision = Column(String(20), nullable=True, comment="approve / reject / hold")
    final_tier = Column(String(8), nullable=True)
    reviewer_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at = Column(DateTime, nullable=True, comment="人工终判时间")

    # 模型与用量（便于成本核算与排障）
    provider = Column(String(50), nullable=True)
    model_id = Column(String(120), nullable=True)
    latency_ms = Column(Integer, default=0, nullable=False)
    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Float, default=0.0, nullable=False)
    error = Column(Text, nullable=True, comment="失败原因（降级为 rules-only 时写入）")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    photo = relationship("Photo", lazy="selectin")
    reviewer = relationship("User", lazy="selectin")

    __table_args__ = (
        Index("ix_moderation_reviews_photo_created", "photo_id", "created_at"),
        Index("ix_moderation_reviews_status_tier", "status", "tier"),
    )

    def __repr__(self) -> str:
        return (
            f"<ModerationReview(photo='{self.photo_id}', status='{self.status}', "
            f"tier='{self.tier}')>"
        )
