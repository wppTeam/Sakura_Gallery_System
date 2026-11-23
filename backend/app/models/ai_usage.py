"""AI 调用用量事件模型。

每发生一次 AI 调用（审核快筛/复核、检索意图解析、结果解释等）记录一条，
用于成本核算、预算闸门、延迟观测与排障。

约定：
- 只记录用量与元信息，**绝不记录 prompt / 用户图片内容 / 密钥**。
- 写入由 `app.services.ai_client` 负责（flush 不 commit），随调用方事务提交。
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text

from app.core.database import Base


class AIUsageEvent(Base):
    """AI 调用用量事件。"""

    __tablename__ = "ai_usage_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    operation = Column(String(100), nullable=False, index=True, comment="调用场景，如 moderation.prefilter")
    provider = Column(String(50), nullable=True, comment="provider 类型：openai_compatible/ollama/dashscope")
    model_id = Column(String(120), nullable=True, comment="实际调用的模型 ID")
    source = Column(String(20), nullable=True, comment="provider 来源：db / env")
    ref_type = Column(String(50), nullable=True, comment="关联资源类型：photo/search/moderation")
    ref_id = Column(String(100), nullable=True, comment="关联资源 ID")

    prompt_tokens = Column(Integer, default=0, nullable=False)
    completion_tokens = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Float, default=0.0, nullable=False, comment="估算成本，价格表缺失时为 0")
    latency_ms = Column(Integer, default=0, nullable=False)
    success = Column(Boolean, default=True, nullable=False)
    error = Column(Text, nullable=True, comment="失败原因（截断，不含敏感内容）")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_ai_usage_events_op_created", "operation", "created_at"),
        Index("ix_ai_usage_events_ref", "ref_type", "ref_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AIUsageEvent(op='{self.operation}', model='{self.model_id}', "
            f"tokens={self.total_tokens}, ok={self.success})>"
        )
