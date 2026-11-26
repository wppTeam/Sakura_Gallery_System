"""站内 AI 生图（AI 创作台）任务模型。

一次生成 = 一行记录：用户在创作台写一句提示词，后台调用 DashScope 异步生图，
成功后把图片临时落在本地 ``uploads/generated/``，前端预览满意后再走普通上传
（含 AIGC 强制声明、审核、隐式标识）发布为作品。

约定：
- **只保存提示词与生成结果元信息**，不保存模型返回的原始响应；
- 生成图是「草稿态」临时文件，不直接进作品表，也不对外公开；
- 失败不消耗额度（每日额度与赠送池都只算非 failed 的行）。
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from app.core.database import Base


class AIGCGeneration(Base):
    """站内 AI 生图任务。"""

    __tablename__ = "aigc_generations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="发起生成的用户",
    )

    prompt = Column(Text, nullable=False, comment="用户提示词（原样保存，用于回填 AIGC 声明）")
    size_key = Column(String(20), nullable=False, comment="尺寸档位：square/landscape/portrait")
    status = Column(
        String(20),
        nullable=False,
        default="queued",
        index=True,
        comment="queued / running / succeeded / failed",
    )

    provider = Column(String(50), nullable=False, default="dashscope")
    model_id = Column(String(120), nullable=False, comment="生图模型 ID，如 qwen-image-3.0-pro")
    provider_task_id = Column(String(120), nullable=True, comment="DashScope 异步任务 id")
    quota_source = Column(
        String(10),
        nullable=False,
        default="daily",
        server_default="daily",
        comment="额度来源：daily=每日基础额度，bonus=管理员赠送池，unlimited=管理员不限",
    )

    image_path = Column(String(500), nullable=True, comment="相对 UPLOAD_DIR 的草稿路径")
    image_format = Column(String(16), nullable=True, comment="png / jpeg / webp")
    image_bytes = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)

    latency_ms = Column(Integer, nullable=True)
    cost_usd = Column(Float, nullable=False, default=0.0)
    error = Column(Text, nullable=True, comment="失败原因（截断，不含提示词以外的敏感信息）")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_aigc_generations_user_created", "user_id", "created_at"),
        Index("ix_aigc_generations_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<AIGCGeneration(id='{self.id}', status='{self.status}', model='{self.model_id}')>"
