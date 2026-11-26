"""AI 生图额度赠送台账。

一行 = 管理员给某位作者赠送的一批张数。剩余额度不单独存列，而是由
「赠送总量 - 已消耗的赠送张数」推导（消耗记录在 ``aigc_generations.quota_source``），
这样生成失败时不需要退款逻辑，与每日额度「失败不计」的口径一致。
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String

from app.core.database import Base


class AigcQuotaGrant(Base):
    """管理员赠送的生图额度。"""

    __tablename__ = "aigc_quota_grants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="受赠作者",
    )
    amount = Column(Integer, nullable=False, comment="赠送张数（正整数）")
    reason = Column(String(200), nullable=True, comment="赠送理由，会展示给作者")
    granted_by = Column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        comment="操作管理员；账号注销后置空，台账保留",
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_aigc_quota_grants_user_created", "user_id", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<AigcQuotaGrant(user_id='{self.user_id}', amount={self.amount})>"