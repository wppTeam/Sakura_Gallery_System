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

# 小时区间：左闭右开；start >= end 表示跨零点（夜 19:00–05:00）。
# 与上面的 time_range 文案必须保持一致，检索层的 period 过滤直接读这张表，
# 避免「时段过滤」与「策展分桶」在边界上各写一套。
PERIOD_HOUR_RANGES: dict[str, tuple[int, int]] = {
    "dawn": (5, 9),
    "noon": (9, 15),
    "dusk": (15, 19),
    "night": (19, 5),
}

# 用户口语 / 英文 key → 规范 period key。检索层与 planner 共用。
PERIOD_ALIASES: dict[str, str] = {
    "dawn": "dawn",
    "晨": "dawn",
    "清晨": "dawn",
    "早晨": "dawn",
    "早上": "dawn",
    "拂晓": "dawn",
    "黎明": "dawn",
    "日出": "dawn",
    "noon": "noon",
    "昼": "noon",
    "白天": "noon",
    "中午": "noon",
    "正午": "noon",
    "午间": "noon",
    "dusk": "dusk",
    "暮": "dusk",
    "傍晚": "dusk",
    "黄昏": "dusk",
    "日落": "dusk",
    "日暮": "dusk",
    "night": "night",
    "夜": "night",
    "夜晚": "night",
    "晚上": "night",
    "夜间": "night",
    "深夜": "night",
    "午夜": "night",
}


def normalize_period(value: object) -> str | None:
    """把中文/英文时段写法规范成 dawn / noon / dusk / night，无法识别返回 None。"""
    if value is None:
        return None
    key = str(value).strip().lower()
    if not key:
        return None
    return PERIOD_ALIASES.get(key)


def period_for_hour(hour: int) -> LightPeriod:
    """按本地小时返回当前时段：05–09 晨 / 09–15 昼 / 15–19 暮 / 其余夜。"""
    hour = hour % 24
    for period in LIGHT_PERIODS:
        start, end = PERIOD_HOUR_RANGES[period.key]
        if start <= end:
            if start <= hour < end:
                return period
        elif hour >= start or hour < end:
            return period
    return LIGHT_PERIODS[3]


def period_for_slug(slug: str) -> LightPeriod | None:
    return LIGHT_PERIOD_BY_SLUG.get(slug)
