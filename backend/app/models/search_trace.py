"""Agent 检索轨迹模型。

记录一次 Agent 驱动检索的意图解析、各工具调用步骤、解释与澄清，
用于管理端排障、效果回放与后续评测集构建。
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Index, Integer, JSON, String, Text

from app.core.database import Base


class AgentSearchTrace(Base):
    """一次 Agent 检索的完整轨迹。"""

    __tablename__ = "agent_search_traces"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    trace_id = Column(String(64), nullable=False, unique=True, index=True)
    query = Column(Text, nullable=False)

    intent = Column(JSON, nullable=True, comment="意图解析：keywords/filters/semantic_query")
    facets = Column(JSON, nullable=True, comment="facet 聚合结果与计数")
    steps = Column(JSON, nullable=True, comment="工具调用步骤与延迟")

    result_count = Column(Integer, default=0, nullable=False)
    clarify = Column(Text, nullable=True, comment="需要澄清时给用户的追问")
    explanation = Column(Text, nullable=True, comment="结果解释")

    model_id = Column(String(120), nullable=True)
    latency_ms = Column(Integer, default=0, nullable=False)
    total_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Float, default=0.0, nullable=False)
    error = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index("ix_agent_search_traces_created", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<AgentSearchTrace(trace='{self.trace_id}', q='{self.query[:24]}', "
            f"n={self.result_count})>"
        )
