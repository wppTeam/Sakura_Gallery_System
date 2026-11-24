"""光的一日：按拍摄时段自动策展的四个专题（晨 / 昼 / 暮 / 夜）。

这里只放「时段元数据」，专题内容与作品归属由
``scripts/seed_curation.py`` 生成、``app.services.spectrum`` 无关。
前端首页「今日之光」hero 与「光的一日」区块、专题接口共用这一份定义，
避免时段边界在脚本 / API / 前端三处各写一遍。
"""

from __future__ import annotations

from typing import NamedTuple


class LightPeriod(NamedTuple):
    key: str
    slug: str
    label: str
    time_range: str
    hint: str


LIGHT_PERIODS: tuple[LightPeriod, ...] = (
    LightPeriod("dawn", "light-dawn", "晨", "05:00–09:00", "光比人先到"),
    LightPeriod("noon", "light-noon", "昼", "09:00–15:00", "影子最短的时刻"),
    LightPeriod("dusk", "light-dusk", "暮", "15:00–19:00", "光开始变软"),
    LightPeriod("night", "light-night", "夜", "19:00–05:00", "灯与星"),
)

LIGHT_SLUGS: tuple[str, ...] = tuple(period.slug for period in LIGHT_PERIODS)
LIGHT_PERIOD_BY_SLUG: dict[str, LightPeriod] = {p.slug: p for p in LIGHT_PERIODS}


def period_for_hour(hour: int) -> LightPeriod:
    """按本地小时返回当前时段：05–09 晨 / 09–15 昼 / 15–19 暮 / 其余夜。"""
    if 5 <= hour < 9:
        return LIGHT_PERIODS[0]
    if 9 <= hour < 15:
        return LIGHT_PERIODS[1]
    if 15 <= hour < 19:
        return LIGHT_PERIODS[2]
    return LIGHT_PERIODS[3]


def period_for_slug(slug: str) -> LightPeriod | None:
    return LIGHT_PERIOD_BY_SLUG.get(slug)
