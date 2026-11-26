"""AI 生图额度：每日基础额度 + 管理员赠送池。

口径（与 ``aigc_generations`` 的统计保持一致，失败一律不计）：

- 管理员不限额度，落 ``quota_source=unlimited``；
- 其他人每天 ``AIGC_IMAGE_DAILY_LIMIT`` 张，按东八区日切重置；
- 每日额度用完后自动消耗赠送池（终身有效，不随日重置）；
- 赠送剩余 = 赠送总量 − 非 failed 的 bonus 生成数。**不存可变余额列**，
  因此生成失败无需退款，撤销赠送也只是减少总量。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.aigc_generation import AIGCGeneration
from app.models.aigc_quota import AigcQuotaGrant
from app.models.user import User

settings = get_settings()


class QuotaExhausted(RuntimeError):
    """每日额度与赠送池都用尽。"""


def is_unlimited(user: User) -> bool:
    return getattr(user, "role", "") == "admin"


def base_daily_limit() -> int:
    return max(0, int(settings.AIGC_IMAGE_DAILY_LIMIT))


@dataclass(frozen=True)
class QuotaState:
    unlimited: bool
    daily_limit: int
    daily_used: int
    bonus_total: int
    bonus_used: int

    @property
    def daily_remaining(self) -> int:
        return max(0, self.daily_limit - self.daily_used)

    @property
    def bonus_remaining(self) -> int:
        return max(0, self.bonus_total - self.bonus_used)

    @property
    def total_remaining(self) -> int:
        return self.daily_remaining + self.bonus_remaining


def _today_start_utc() -> datetime:
    """按东八区「今天」换算成 UTC naive（数据库统一存 UTC）。"""
    now_utc8 = datetime.utcnow() + timedelta(hours=8)
    local_midnight = datetime(now_utc8.year, now_utc8.month, now_utc8.day)
    return local_midnight - timedelta(hours=8)


async def _count_used(db: AsyncSession, user_id: str, source: str, *, today_only: bool) -> int:
    stmt = (
        select(func.count())
        .select_from(AIGCGeneration)
        .where(
            AIGCGeneration.user_id == user_id,
            AIGCGeneration.quota_source == source,
            AIGCGeneration.status != "failed",
        )
    )
    if today_only:
        stmt = stmt.where(AIGCGeneration.created_at >= _today_start_utc())
    return int((await db.execute(stmt)).scalar_one() or 0)


async def get_quota(db: AsyncSession, user: User) -> QuotaState:
    unlimited = is_unlimited(user)
    daily_limit = base_daily_limit()
    daily_used = await _count_used(db, user.id, "daily", today_only=True)
    bonus_total = int(
        (
            await db.execute(
                select(func.coalesce(func.sum(AigcQuotaGrant.amount), 0)).where(
                    AigcQuotaGrant.user_id == user.id
                )
            )
        ).scalar_one()
        or 0
    )
    bonus_used = await _count_used(db, user.id, "bonus", today_only=False)
    return QuotaState(
        unlimited=unlimited,
        daily_limit=daily_limit,
        daily_used=daily_used,
        bonus_total=bonus_total,
        bonus_used=bonus_used,
    )


async def resolve_quota_source(db: AsyncSession, user: User) -> str:
    """返回本次生成该扣哪份额度；都用尽时抛 :class:`QuotaExhausted`。"""
    if is_unlimited(user):
        return "unlimited"
    state = await get_quota(db, user)
    if state.daily_remaining > 0:
        return "daily"
    if state.bonus_remaining > 0:
        return "bonus"
    raise QuotaExhausted(
        f"今天的 {state.daily_limit} 张基础额度已用完，赠送额度也用尽了。"
        "基础额度每天 0 点重置，也可以联系管理员申请额外额度。"
    )