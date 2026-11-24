"""
AI 成本与用量观测 API

`ai_usage_events` 里记录着每次模型调用的 token 与成本（只记元信息，不含
prompt / 图片内容）。这里给管理员一个低成本的聚合视图，用于：
- 看每天花了多少、哪条链路最贵（审核快筛 / 复核 / 检索规划 / 解释）；
- 核对某个模型的实际单价（`cost_usd / total_tokens`）；
- 排查失败率与延迟。

实现用三条聚合 SQL（按日 / 按 operation / 按 model）+ 一条最近事件查询，
不做 N+1；`days` 上限 90 天，避免大表全扫。
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_admin_user, get_db
from app.models.ai_usage import AIUsageEvent
from app.models.user import User

router = APIRouter(prefix="/ai", tags=["AI 成本"])


class AIUsageTotals(BaseModel):
    calls: int
    success: int
    failed: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    avg_latency_ms: float


class AIUsageBucket(BaseModel):
    key: str
    calls: int
    total_tokens: int
    cost_usd: float


class AIUsageEventOut(BaseModel):
    id: str
    operation: str
    provider: Optional[str] = None
    model_id: Optional[str] = None
    ref_type: Optional[str] = None
    ref_id: Optional[str] = None
    total_tokens: int
    cost_usd: float
    latency_ms: int
    success: bool
    error: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AIUsageResponse(BaseModel):
    days: int
    since: datetime
    generated_at: datetime
    totals: AIUsageTotals
    by_day: List[AIUsageBucket]
    by_operation: List[AIUsageBucket]
    by_model: List[AIUsageBucket]
    recent: List[AIUsageEventOut]


@router.get("/usage", response_model=AIUsageResponse)
async def get_ai_usage(
    days: int = Query(7, ge=1, le=90, description="统计最近多少天"),
    recent_limit: int = Query(20, ge=1, le=100, description="最近事件条数"),
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_admin_user),
):
    """AI 调用总量、按日/链路/模型分布与最近事件（仅超级管理员）。"""
    since = datetime.utcnow() - timedelta(days=days)
    window = AIUsageEvent.created_at >= since

    totals_row = (
        await db.execute(
            select(
                func.count(AIUsageEvent.id),
                func.coalesce(func.sum(case((AIUsageEvent.success.is_(True), 1), else_=0)), 0),
                func.coalesce(func.sum(case((AIUsageEvent.success.is_(False), 1), else_=0)), 0),
                func.coalesce(func.sum(AIUsageEvent.prompt_tokens), 0),
                func.coalesce(func.sum(AIUsageEvent.completion_tokens), 0),
                func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
                func.coalesce(func.sum(AIUsageEvent.cost_usd), 0.0),
                func.coalesce(func.sum(AIUsageEvent.latency_ms), 0),
            ).where(window)
        )
    ).one()
    calls = int(totals_row[0] or 0)
    prompt_tokens = int(totals_row[3] or 0)
    completion_tokens = int(totals_row[4] or 0)
    total_tokens = int(totals_row[5] or 0)
    cost_usd = float(totals_row[6] or 0.0)
    latency_sum = int(totals_row[7] or 0)
    totals = AIUsageTotals(
        calls=calls,
        success=int(totals_row[1] or 0),
        failed=int(totals_row[2] or 0),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_usd=round(cost_usd, 6),
        avg_latency_ms=round(latency_sum / calls, 1) if calls else 0.0,
    )

    def _bucket_rows(rows) -> List[AIUsageBucket]:
        out: List[AIUsageBucket] = []
        for key, count, tokens, cost in rows:
            out.append(
                AIUsageBucket(
                    key=str(key) if key is not None else "unknown",
                    calls=int(count or 0),
                    total_tokens=int(tokens or 0),
                    cost_usd=round(float(cost or 0.0), 6),
                )
            )
        return out

    day_rows = (
        await db.execute(
            select(
                func.date(AIUsageEvent.created_at).label("day"),
                func.count(AIUsageEvent.id),
                func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
                func.coalesce(func.sum(AIUsageEvent.cost_usd), 0.0),
            )
            .where(window)
            .group_by("day")
            .order_by("day")
        )
    ).all()
    by_day = _bucket_rows([(str(r[0])[:10], r[1], r[2], r[3]) for r in day_rows])

    operation_rows = (
        await db.execute(
            select(
                AIUsageEvent.operation,
                func.count(AIUsageEvent.id),
                func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
                func.coalesce(func.sum(AIUsageEvent.cost_usd), 0.0),
            )
            .where(window)
            .group_by(AIUsageEvent.operation)
            .order_by(func.sum(AIUsageEvent.cost_usd).desc(), func.count(AIUsageEvent.id).desc())
        )
    ).all()
    by_operation = _bucket_rows(operation_rows)

    model_rows = (
        await db.execute(
            select(
                func.coalesce(AIUsageEvent.model_id, "unknown"),
                func.count(AIUsageEvent.id),
                func.coalesce(func.sum(AIUsageEvent.total_tokens), 0),
                func.coalesce(func.sum(AIUsageEvent.cost_usd), 0.0),
            )
            .where(window)
            .group_by(AIUsageEvent.model_id)
            .order_by(func.sum(AIUsageEvent.cost_usd).desc(), func.count(AIUsageEvent.id).desc())
        )
    ).all()
    by_model = _bucket_rows(model_rows)

    recent_rows = (
        await db.execute(
            select(AIUsageEvent)
            .where(window)
            .order_by(AIUsageEvent.created_at.desc())
            .limit(recent_limit)
        )
    ).scalars().all()

    return AIUsageResponse(
        days=days,
        since=since,
        generated_at=datetime.utcnow(),
        totals=totals,
        by_day=by_day,
        by_operation=by_operation,
        by_model=by_model,
        recent=[AIUsageEventOut.model_validate(e) for e in recent_rows],
    )
