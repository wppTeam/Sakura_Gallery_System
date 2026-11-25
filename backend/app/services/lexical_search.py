"""纯 SQL 词法检索层（不依赖 torch / Milvus）。

设计约束（2c4g 小机器）：

- **一条 SQL 完成打分 + 过滤 + 分页**：候选集先用 pg_trgm ILIKE / GIN 索引收敛，
  再在 SQL 内算加权分并排序分页；详情（tags / 分类）用相关子查询只对当前页
  （≤100 行）求值，全程无 N+1。
- **facet 用一条聚合 SQL**：``WITH matched AS (…)`` + ``UNION ALL`` 一次拿回
  season / category / campus / tag 的计数与命中总数。
- **中文优先 pg_trgm**：CJK 没有词边界，``tsvector`` 只有在 ``photos.search_tokens``
  （由 DB trigger 写入的中文二元组）存在后才有效，因此这里把它当作**加分项**
  （``ts_rank_cd``），主力是 ``ILIKE`` + ``similarity``；两者都走 GIN trgm 索引。
- **SQLite 降级**：仅用于测试/本地无 PG 场景，用 ``instr/like`` 近似打分。
- 运行期能力探测：pg_trgm 扩展 / ``photos.search_vector`` 列缺失时自动降级，
  绝不因为迁移未跑而 500。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping, Optional, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.light_of_day import PERIOD_HOUR_RANGES, normalize_period
from app.services.search_text import build_or_tsquery

logger = logging.getLogger(__name__)

# 检索只暴露已通过审核的照片
APPROVED_STATUS = "approved"
# 分页硬上限（与 AGENTS.md 约定一致）
LIMIT_MAX = 100
# 查询词上限：SQL 体积与相关子查询数量随词数线性增长
MAX_TERMS = 6
# 每个结果最多返回的标签数
MAX_TAGS_PER_HIT = 12

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SPLIT_RE = re.compile(r"[\s,，、;；:：!?！？·\-\|/\\()（）\[\]【】\"'“”‘’]+")
# 仅由这些虚词/高频字组成的二元组不单独作为检索词
_STOP_CHARS = frozenset(
    "的了里在中和与或及从到被把让给向往上下大小多少新旧好美是就都也还很最个一这那有为对以于而之其"
)

# photos 上可直接做等值过滤的列（其余 key 视为 taxonomy facet）
_PHOTO_EXACT_COLUMNS: frozenset[str] = frozenset(
    {"season", "category", "campus", "uploader_id", "status"}
)
# 时间区间过滤
_TIME_RANGE_COLUMNS: dict[str, tuple[str, str]] = {
    "captured_from": ("captured_at", ">="),
    "captured_to": ("captured_at", "<="),
    "published_from": ("published_at", ">="),
    "published_to": ("published_at", "<="),
}
# 端点兼容参数 → 真实列名
_FILTER_ALIASES: dict[str, str] = {
    "uploader": "uploader_id",
}
# 明确忽略的过滤键（当前 photos 表没有对应列；忽略而不是报错）
_IGNORED_FILTER_KEYS: frozenset[str] = frozenset({"kind", "landmark_facet", "mode"})
# 历史遗留值 → 库内可能存储的多种写法（照片列是 legacy 值，taxonomy 用中文名）
_SEASON_SYNONYMS: dict[str, tuple[str, ...]] = {
    "春季": ("春季", "Spring", "春"),
    "春": ("春季", "Spring", "春"),
    "春天": ("春季", "Spring", "春"),
    "春日": ("春季", "Spring", "春"),
    "Spring": ("春季", "Spring"),
    "夏季": ("夏季", "Summer", "夏"),
    "夏": ("夏季", "Summer", "夏"),
    "夏天": ("夏季", "Summer", "夏"),
    "夏日": ("夏季", "Summer", "夏"),
    "Summer": ("夏季", "Summer"),
    "秋季": ("秋季", "Autumn", "秋"),
    "秋": ("秋季", "Autumn", "秋"),
    "秋天": ("秋季", "Autumn", "秋"),
    "秋日": ("秋季", "Autumn", "秋"),
    "Autumn": ("秋季", "Autumn"),
    "冬季": ("冬季", "Winter", "冬"),
    "冬": ("冬季", "Winter", "冬"),
    "冬天": ("冬季", "Winter", "冬"),
    "冬日": ("冬季", "Winter", "冬"),
    "Winter": ("冬季", "Winter"),
}
_CATEGORY_SYNONYMS: dict[str, tuple[str, ...]] = {
    "风光": ("风光", "风光类", "校园风光", "Landscape"),
    "风景": ("风光", "风光类", "校园风光", "Landscape"),
    "建筑": ("建筑楼宇", "风光", "Landscape"),
    "人像": ("人像", "Portrait"),
    "活动": ("活动", "Activity"),
    "纪实": ("纪实", "纪实类", "人文纪实", "Documentary"),
    "自然生态": ("自然生态", "Landscape"),
    "Landscape": ("Landscape", "风光", "风光类"),
    "Portrait": ("Portrait", "人像"),
    "Activity": ("Activity", "活动"),
    "Documentary": ("Documentary", "纪实"),
}
_CAMPUS_SYNONYMS: dict[str, tuple[str, ...]] = {
    "昌平": ("昌平校区", "昌平"),
    "昌平校区": ("昌平校区", "昌平"),
    "朝阳": ("朝阳校区", "朝阳"),
    "朝阳校区": ("朝阳校区", "朝阳"),
    "海淀": ("海淀校区", "海淀"),
    "海淀校区": ("海淀校区", "海淀"),
}


@dataclass(slots=True)
class LexicalWeights:
    """混合打分权重（sum 应为 1.0，保证 score ∈ [0, 1]）。

    - term_best: 各检索词在 标题/描述/标签/分类 中的最佳命中（含模糊相似度）
    - full_match: 完整 query 的整串匹配 / 相似度
    - fulltext: tsvector 排名（中文需 DB trigger 写入 search_tokens 才有效）
    """

    term_best: float = 0.55
    full_match: float = 0.30
    fulltext: float = 0.15
    # pg_trgm 相似度阈值：低于该值不进入候选集
    similarity_threshold: float = 0.30
    # 标签/分类的模糊相似度阈值（标签通常很短，略放宽）
    taxonomy_similarity_threshold: float = 0.35

    def total(self) -> float:
        return self.term_best + self.full_match + self.fulltext


DEFAULT_WEIGHTS = LexicalWeights()


@dataclass
class SearchHit:
    """统一检索命中。"""

    photo_id: str
    score: float
    matched_fields: list[str] = field(default_factory=list)
    match_reason: Optional[str] = None
    title: Optional[str] = None
    filename: Optional[str] = None
    author: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    season: Optional[str] = None
    category: Optional[str] = None
    campus: Optional[str] = None
    description: Optional[str] = None
    # 补充检索语料（AI 画面描述等），用于解释「画面描述匹配」
    search_document: Optional[str] = None
    created_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    is_aigc: bool = False
    aigc_label: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    classifications: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "photo_id": self.photo_id,
            "score": self.score,
            "matched_fields": list(self.matched_fields),
            "match_reason": self.match_reason,
            "title": self.title,
            "filename": self.filename,
            "author": self.author,
            "width": self.width,
            "height": self.height,
            "season": self.season,
            "category": self.category,
            "campus": self.campus,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "is_aigc": self.is_aigc,
            "kind": "aigc" if self.is_aigc else "photo",
            "aigc_label": self.aigc_label,
            "tags": list(self.tags),
            "classifications": dict(self.classifications),
        }


@dataclass
class FacetValue:
    value: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "label": self.value, "count": self.count}


@dataclass
class FacetResult:
    """facet 聚合结果。"""

    seasons: list[FacetValue] = field(default_factory=list)
    categories: list[FacetValue] = field(default_factory=list)
    campuses: list[FacetValue] = field(default_factory=list)
    tags: list[FacetValue] = field(default_factory=list)
    total: int = 0

    def to_dict(self) -> dict[str, Any]:
        """输出前端 `SearchFacets` 契约（单数 key + value/label/count）。"""
        return {
            "season": [item.to_dict() for item in self.seasons],
            "category": [item.to_dict() for item in self.categories],
            "campus": [item.to_dict() for item in self.campuses],
            "tag": [item.to_dict() for item in self.tags],
            "total": self.total,
        }


# ---------------------------------------------------------------------------
# 查询词 / 分词
# ---------------------------------------------------------------------------

def build_search_tokens(value: Optional[str]) -> str:
    """保留给入库链路的分词 helper（与 DB trigger 规则一致，可做校验/回填）。

    实际写库由 DB trigger 负责；返回空串表示没有可用 token。
    """
    from app.services.search_text import search_tokens_text

    return search_tokens_text(value)


def build_search_terms(
    query: Optional[str],
    keywords: Optional[Sequence[str]] = None,
    *,
    max_terms: int = MAX_TERMS,
) -> list[str]:
    """把自然语言 query + planner 关键词整理成有限个检索词。

    - 按标点/空白切分，整串与各片段都作为检索词；
    - 若只有一段较长的中文（planner 不可用时的 fast 路径），补二元组提升召回；
    - 词数封顶 ``max_terms``，保证 SQL 体积可控。
    """
    raw_parts: list[str] = []
    for source in (query, *(keywords or ())):
        if not isinstance(source, str):
            continue
        source = source.strip()
        if not source:
            continue
        raw_parts.extend(p.strip() for p in _SPLIT_RE.split(source) if p.strip())

    terms: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        token = token.strip()[:24]
        if not token:
            return
        key = token.casefold()
        if key in seen:
            return
        seen.add(key)
        terms.append(token)

    for part in raw_parts:
        add(part)

    # fast 路径兜底：单个长中文片段 => 用二元组召回（planner 给的关键词通常已够好）
    if len(raw_parts) == 1 and len(terms) == 1:
        segment = terms[0]
        if len(segment) >= 4 and _CJK_RE.search(segment):
            # 很长的整句中文整串几乎不可能直接命中，直接换二元组，避免稀释打分
            if len(segment) > 8:
                terms.clear()
                seen.clear()
            for i in range(len(segment) - 1):
                bigram = segment[i : i + 2]
                if all(ch in _STOP_CHARS for ch in bigram):
                    continue
                add(bigram)
                if len(terms) >= max_terms:
                    break

    return terms[:max_terms]


# ---------------------------------------------------------------------------
# 过滤条件归一化
# ---------------------------------------------------------------------------

def _coerce_datetime(value: Any) -> Optional[datetime]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if isinstance(value, str):
        candidate = value.strip()
        try:
            return datetime.fromisoformat(candidate.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            try:
                return datetime.strptime(candidate[:10], "%Y-%m-%d")
            except ValueError:
                logger.debug("lexical_search: ignore unparsable datetime filter %r", value)
                return None
    return None


def _expand_photo_filter(key: str, value: str) -> list[str]:
    """season/category/campus 的历史值兼容展开（legacy 英文 vs taxonomy 中文）。"""
    if key == "season":
        return list(_SEASON_SYNONYMS.get(value, (value,)))
    if key == "category":
        return list(_CATEGORY_SYNONYMS.get(value, (value,)))
    if key == "campus":
        return list(_CAMPUS_SYNONYMS.get(value, (value,)))
    return [value]


def normalize_filters(filters: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """端点多渠道 filter 参数 → 规范化字典（别名、时间、多值、同义词展开）。"""
    if not filters:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in filters.items():
        if value is None or value == "":
            continue
        if key in _IGNORED_FILTER_KEYS:
            continue
        real_key = _FILTER_ALIASES.get(key, key)
        if real_key in _TIME_RANGE_COLUMNS:
            coerced = _coerce_datetime(value)
            if coerced is not None:
                normalized[real_key] = coerced
            continue

        values: list[str] = []
        if isinstance(value, (list, tuple, set, frozenset)):
            for item in value:
                if item not in (None, ""):
                    values.append(str(item).strip())
        else:
            values.append(str(value).strip())
        values = [item for item in values if item]
        if not values:
            continue
        if real_key == "period":
            # 拍摄时段（晨/昼/暮/夜）：中英文口语都收敛到一个规范 key；
            # 无法识别的值直接丢弃，避免静默返回全量结果。
            canonical = normalize_period(values[0])
            if canonical:
                normalized["period"] = canonical
            continue
        if real_key in {"season", "category", "campus"}:
            expanded: list[str] = []
            for item in values:
                for candidate in _expand_photo_filter(real_key, item):
                    if candidate not in expanded:
                        expanded.append(candidate)
            normalized[real_key] = expanded
        elif len(values) == 1:
            normalized[real_key] = values[0]
        else:
            normalized[real_key] = values
    return normalized


def _build_filter_sql(
    filters: Mapping[str, Any], params: dict[str, Any], caps: "_DialectCaps"
) -> list[str]:
    """构造结构化过滤 SQL 片段（照片列等值 + tag + taxonomy facet + 时间区间）。

    所有值都走绑定参数。
    """
    conditions: list[str] = []
    idx = 0
    for key, value in filters.items():
        if key == "period":
            # 本地拍摄小时落在哪个时段。夜跨零点，因此走「>= start 或 < end」。
            period_key = normalize_period(value)
            if not period_key:
                continue
            start, end = PERIOD_HOUR_RANGES[period_key]
            name = f"ph{idx}"
            idx += 1
            params[f"{name}_start"] = start
            params[f"{name}_end"] = end
            hour_sql = (
                "EXTRACT(HOUR FROM p.captured_at)"
                if caps.is_postgres
                else "CAST(strftime('%H', p.captured_at) AS INTEGER)"
            )
            if start <= end:
                conditions.append(
                    f"p.captured_at IS NOT NULL AND {hour_sql} >= :{name}_start AND {hour_sql} < :{name}_end"
                )
            else:
                conditions.append(
                    f"p.captured_at IS NOT NULL AND ({hour_sql} >= :{name}_start OR {hour_sql} < :{name}_end)"
                )
            continue

        if key in _TIME_RANGE_COLUMNS:
            column, operator = _TIME_RANGE_COLUMNS[key]
            name = f"tf{idx}"
            idx += 1
            conditions.append(f"p.{column} {operator} :{name}")
            params[name] = value
            continue

        if key == "tag":
            value_list = value if isinstance(value, list) else [value]
            for item in value_list:
                name = f"tg{idx}"
                idx += 1
                params[name] = item
                conditions.append(
                    "EXISTS ("
                    "SELECT 1 FROM photo_tags ptg JOIN tags tg ON tg.id = ptg.tag_id "
                    "LEFT JOIN tag_aliases tga ON tga.tag_id = tg.id "
                    f"WHERE ptg.photo_id = p.id AND (tg.name = :{name} OR tga.alias = :{name})"
                    ")"
                )
            continue

        if key in _PHOTO_EXACT_COLUMNS:
            column = key
            values = value if isinstance(value, list) else [value]
            names = []
            for item in values:
                name = f"fv{idx}"
                idx += 1
                params[name] = item
                names.append(f":{name}")
            if len(names) == 1:
                conditions.append(f"p.{column} = {names[0]}")
            else:
                conditions.append(f"p.{column} IN ({', '.join(names)})")
            continue

        # 其余 key 按 taxonomy facet 处理（兼容端点既有的 building/landscape/photo_type 等参数）
        facet_keys: list[str] = ["building", "landscape"] if key == "landmark" else [key]
        value_list = value if isinstance(value, list) else [value]
        for item in value_list:
            fv_name = f"fvv{idx}"
            fk_name_lit = f"fkl{idx}"
            idx += 1
            params[fv_name] = item
            params[fk_name_lit] = str(item).lower().replace(" ", "-")
            # 每个 facet key 单独绑定：asyncpg 不接受 `IN :list` 这种把列表绑到
            # 单个占位符的写法（会报语法错误），必须展开成 `IN (:k0, :k1)`。
            facet_placeholders: list[str] = []
            for facet_key in facet_keys:
                key_param = f"fk{idx}"
                idx += 1
                params[key_param] = facet_key
                facet_placeholders.append(f":{key_param}")
            conditions.append(
                "EXISTS ("
                "SELECT 1 FROM photo_classifications pcf "
                "JOIN taxonomy_facets tff ON tff.id = pcf.facet_id "
                "JOIN taxonomy_nodes tnf ON tnf.id = pcf.node_id "
                "LEFT JOIN taxonomy_aliases taf ON taf.node_id = tnf.id "
                f"WHERE pcf.photo_id = p.id AND tff.key IN ({', '.join(facet_placeholders)}) "
                "AND tff.is_active = TRUE AND tnf.is_active = TRUE AND tnf.is_selectable = TRUE "
                f"AND (tnf.name = :{fv_name} OR tnf.key = :{fk_name_lit} OR taf.alias = :{fv_name})"
                ")"
            )
    return conditions


# ---------------------------------------------------------------------------
# 方言 / 能力探测
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class _DialectCaps:
    dialect: str
    trgm: bool = False
    search_vector: bool = False
    search_tokens: bool = False

    @property
    def is_postgres(self) -> bool:
        return self.dialect == "postgresql"


_CAPS_CACHE: dict[Any, _DialectCaps] = {}


def _engine_cache_key(db: AsyncSession) -> Any:
    try:
        bind = db.get_bind()
    except Exception:  # noqa: BLE001 - 探测失败时退回 sqlite 语义
        return None
    engine = getattr(bind, "engine", bind)
    return id(engine)


def _dialect_of(db: AsyncSession) -> str:
    try:
        bind = db.get_bind()
        engine = getattr(bind, "engine", bind)
        return str(engine.dialect.name)
    except Exception:  # noqa: BLE001
        return "sqlite"


async def get_dialect_caps(db: AsyncSession) -> _DialectCaps:
    """探测当前连接的方言与 PG 能力（pg_trgm / search_vector），并缓存。"""
    if _dialect_of(db) != "postgresql":
        return _DialectCaps(dialect="sqlite")

    key = _engine_cache_key(db)
    cached = _CAPS_CACHE.get(key)
    if cached is not None:
        return cached

    caps = _DialectCaps(dialect="postgresql")
    try:
        row = (
            await db.execute(
                text(
                    "SELECT "
                    "(SELECT count(*) FROM pg_extension WHERE extname = 'pg_trgm') AS trgm, "
                    "(SELECT count(*) FROM information_schema.columns "
                    " WHERE table_schema = current_schema() AND table_name = 'photos' "
                    " AND column_name = 'search_vector') AS search_vector, "
                    "(SELECT count(*) FROM information_schema.columns "
                    " WHERE table_schema = current_schema() AND table_name = 'photos' "
                    " AND column_name = 'search_tokens') AS search_tokens"
                )
            )
        ).first()
        if row is not None:
            caps.trgm = bool(row[0])
            caps.search_vector = bool(row[1])
            caps.search_tokens = bool(row[2])
    except Exception:  # noqa: BLE001 - 探测本身不应导致检索失败
        logger.warning("lexical_search: capability probe failed, degrade to ILIKE only", exc_info=True)

    if key is not None:
        _CAPS_CACHE[key] = caps
    return caps


def clear_capability_cache() -> None:
    """测试用：清空能力探测缓存。"""
    _CAPS_CACHE.clear()


async def index_version(db: AsyncSession) -> str:
    """返回当前索引实现标识，写进 API 响应用于排障。"""
    caps = await get_dialect_caps(db)
    if not caps.is_postgres:
        return "sqlite-like"
    if not caps.trgm:
        return "postgres-like"
    return "pg_trgm+tsvector" if caps.search_vector else "pg_trgm"


# ---------------------------------------------------------------------------
# SQL 片段构造（PG / SQLite 两套打分表达式）
# ---------------------------------------------------------------------------

def _pg_term_score(term_index: int) -> str:
    q = f":q{term_index}"
    like = f":like{term_index}"
    title = (
        f"COALESCE(CASE WHEN p.title ILIKE {like} THEN 1.0 "
        f"ELSE COALESCE(similarity(p.title, {q}), 0) END, 0)"
    )
    description = (
        f"COALESCE(CASE WHEN p.description ILIKE {like} THEN 0.80 "
        f"ELSE 0.80 * COALESCE(similarity(p.description, {q}), 0) END, 0)"
    )
    # 补充检索语料：AI 画面描述/标签等，命中说明「画面内容」吻合
    document = (
        f"COALESCE(CASE WHEN p.search_document ILIKE {like} THEN 0.85 "
        f"ELSE 0.85 * COALESCE(similarity(p.search_document, {q}), 0) END, 0)"
    )
    tag = (
        "COALESCE(("
        "SELECT MAX(CASE WHEN t.name ILIKE " + like + " THEN 0.95 "
        "ELSE 0.95 * COALESCE(similarity(t.name, " + q + "), 0) END) "
        "FROM photo_tags pt JOIN tags t ON t.id = pt.tag_id "
        "WHERE pt.photo_id = p.id), 0)"
    )
    taxonomy = (
        "COALESCE(("
        "SELECT MAX(CASE WHEN tn.name ILIKE " + like + " THEN 0.90 "
        "ELSE 0.90 * COALESCE(similarity(tn.name, " + q + "), 0) END) "
        "FROM photo_classifications pc "
        "JOIN taxonomy_facets tf ON tf.id = pc.facet_id "
        "JOIN taxonomy_nodes tn ON tn.id = pc.node_id "
        "WHERE pc.photo_id = p.id AND tf.is_active = TRUE "
        "AND tn.is_active = TRUE AND tn.is_selectable = TRUE), 0)"
    )
    return f"COALESCE(GREATEST({title}, {description}, {document}, {tag}, {taxonomy}), 0)"


def _pg_term_condition(term_index: int, caps: _DialectCaps, weights: LexicalWeights) -> str:
    q = f":q{term_index}"
    like = f":like{term_index}"
    parts = [
        f"p.title ILIKE {like}",
        f"p.description ILIKE {like}",
        f"COALESCE(p.search_document, '') ILIKE {like}",
        f"EXISTS (SELECT 1 FROM photo_tags pt2 JOIN tags t2 ON t2.id = pt2.tag_id "
        f"WHERE pt2.photo_id = p.id AND t2.name ILIKE {like})",
        "EXISTS (SELECT 1 FROM photo_classifications pc2 "
        "JOIN taxonomy_facets tf2 ON tf2.id = pc2.facet_id "
        "JOIN taxonomy_nodes tn2 ON tn2.id = pc2.node_id "
        "LEFT JOIN taxonomy_aliases ta2 ON ta2.node_id = tn2.id "
        f"WHERE pc2.photo_id = p.id AND tf2.is_active = TRUE "
        f"AND tn2.is_active = TRUE AND tn2.is_selectable = TRUE "
        f"AND (tn2.name ILIKE {like} OR tn2.key ILIKE {like} OR ta2.alias ILIKE {like}))",
    ]
    if caps.search_vector:
        parts.append(f"p.search_vector @@ plainto_tsquery('simple', {q})")
    if caps.trgm:
        parts.extend(
            [
                f"COALESCE(similarity(p.title, {q}), 0) >= {weights.similarity_threshold}",
                f"COALESCE(similarity(p.description, {q}), 0) >= {weights.similarity_threshold}",
                f"COALESCE(similarity(p.search_document, {q}), 0) >= {weights.similarity_threshold}",
                f"EXISTS (SELECT 1 FROM photo_tags pt3 JOIN tags t3 ON t3.id = pt3.tag_id "
                f"WHERE pt3.photo_id = p.id AND COALESCE(similarity(t3.name, {q}), 0) >= "
                f"{weights.taxonomy_similarity_threshold})",
                "EXISTS (SELECT 1 FROM photo_classifications pc3 "
                "JOIN taxonomy_facets tf3 ON tf3.id = pc3.facet_id "
                "JOIN taxonomy_nodes tn3 ON tn3.id = pc3.node_id "
                "LEFT JOIN taxonomy_aliases ta3 ON ta3.node_id = tn3.id "
                f"WHERE pc3.photo_id = p.id AND tf3.is_active = TRUE "
                f"AND tn3.is_active = TRUE AND tn3.is_selectable = TRUE "
                f"AND (COALESCE(similarity(tn3.name, {q}), 0) >= "
                f"{weights.taxonomy_similarity_threshold} "
                f"OR COALESCE(similarity(ta3.alias, {q}), 0) >= "
                f"{weights.taxonomy_similarity_threshold}))",
            ]
        )
    return "(" + " OR ".join(parts) + ")"


def _pg_score_sql(
    terms: Sequence[str], caps: _DialectCaps, weights: LexicalWeights, has_tsquery: bool
) -> str:
    if not terms:
        return "0.0"
    term_scores = " + ".join(_pg_term_score(i) for i in range(len(terms)))
    avg = f"(({term_scores}) / {len(terms)}.0)"

    full_title = "COALESCE(similarity(p.title, :qfull), 0)"
    full_desc = "0.80 * COALESCE(similarity(p.description, :qfull), 0)"
    full_document = "0.75 * COALESCE(similarity(p.search_document, :qfull), 0)"
    full_substr = (
        "CASE WHEN p.title ILIKE :likefull THEN 1.0 "
        "WHEN p.description ILIKE :likefull THEN 0.80 "
        "WHEN COALESCE(p.search_document, '') ILIKE :likefull THEN 0.75 "
        "ELSE 0 END"
    )
    full_best = f"COALESCE(GREATEST({full_title}, {full_desc}, {full_document}, {full_substr}), 0)"

    if caps.search_vector and has_tsquery:
        # 中文 tsvector 依赖 DB trigger 写入 search_tokens（二元组）；缺失时 rank 为 0，无副作用
        fulltext = "COALESCE(ts_rank_cd(p.search_vector, to_tsquery('simple', :tq), 32), 0)"
    else:
        fulltext = "0.0"

    return (
        f"({weights.term_best} * {avg} "
        f"+ {weights.full_match} * {full_best} "
        f"+ {weights.fulltext} * {fulltext})"
    )


def _sqlite_term_score(term_index: int) -> str:
    like = f":like{term_index}"
    title = f"CASE WHEN lower(COALESCE(p.title, '')) LIKE {like} THEN 1.0 ELSE 0.0 END"
    description = (
        f"CASE WHEN lower(COALESCE(p.description, '')) LIKE {like} THEN 0.80 ELSE 0.0 END"
    )
    document = (
        f"CASE WHEN lower(COALESCE(p.search_document, '')) LIKE {like} THEN 0.85 ELSE 0.0 END"
    )
    tag = (
        "COALESCE(("
        "SELECT MAX(CASE WHEN lower(t.name) LIKE " + like + " THEN 0.95 ELSE 0.0 END) "
        "FROM photo_tags pt JOIN tags t ON t.id = pt.tag_id "
        "WHERE pt.photo_id = p.id), 0)"
    )
    taxonomy = (
        "COALESCE(("
        "SELECT MAX(CASE WHEN lower(tn.name) LIKE " + like + " THEN 0.90 ELSE 0.0 END) "
        "FROM photo_classifications pc "
        "JOIN taxonomy_facets tf ON tf.id = pc.facet_id "
        "JOIN taxonomy_nodes tn ON tn.id = pc.node_id "
        "WHERE pc.photo_id = p.id AND tf.is_active = 1 "
        "AND tn.is_active = 1 AND tn.is_selectable = 1), 0)"
    )
    return f"MAX({title}, {description}, {document}, {tag}, {taxonomy})"


def _sqlite_term_condition(term_index: int) -> str:
    like = f":like{term_index}"
    return (
        "(lower(COALESCE(p.title, '')) LIKE " + like +
        " OR lower(COALESCE(p.description, '')) LIKE " + like +
        " OR lower(COALESCE(p.search_document, '')) LIKE " + like +
        " OR EXISTS (SELECT 1 FROM photo_tags pt2 JOIN tags t2 ON t2.id = pt2.tag_id "
        "WHERE pt2.photo_id = p.id AND lower(t2.name) LIKE " + like + ")"
        " OR EXISTS (SELECT 1 FROM photo_classifications pc2 "
        "JOIN taxonomy_facets tf2 ON tf2.id = pc2.facet_id "
        "JOIN taxonomy_nodes tn2 ON tn2.id = pc2.node_id "
        "LEFT JOIN taxonomy_aliases ta2 ON ta2.node_id = tn2.id "
        "WHERE pc2.photo_id = p.id AND tf2.is_active = 1 "
        "AND tn2.is_active = 1 AND tn2.is_selectable = 1 "
        "AND (lower(tn2.name) LIKE " + like +
        " OR lower(tn2.key) LIKE " + like +
        " OR lower(ta2.alias) LIKE " + like + ")))"
    )


def _sqlite_score_sql(terms: Sequence[str], weights: LexicalWeights) -> str:
    if not terms:
        return "0.0"
    term_scores = " + ".join(f"({_sqlite_term_score(i)})" for i in range(len(terms)))
    avg = f"(({term_scores}) / {len(terms)}.0)"
    full = (
        "CASE WHEN lower(COALESCE(p.title, '')) LIKE :likefull THEN 1.0 "
        "WHEN lower(COALESCE(p.description, '')) LIKE :likefull THEN 0.80 "
        "WHEN lower(COALESCE(p.search_document, '')) LIKE :likefull THEN 0.75 "
        "ELSE 0.0 END"
    )
    return f"({weights.term_best} * {avg} + {weights.full_match} * {full})"


@dataclass(slots=True)
class _QueryParts:
    caps: _DialectCaps
    terms: list[str]
    full_query: str
    params: dict[str, Any]
    where_sql: str


def _prepare_query(
    caps: _DialectCaps,
    query: Optional[str],
    keywords: Optional[Sequence[str]],
    filters: Optional[Mapping[str, Any]],
    weights: LexicalWeights,
) -> _QueryParts:
    normalized_filters = normalize_filters(filters)
    terms = build_search_terms(query, keywords)
    full_query = (query or "").strip() or (terms[0] if terms else "")

    params: dict[str, Any] = {"status": APPROVED_STATUS}
    conditions = _build_filter_sql(normalized_filters, params, caps)

    tsquery: Optional[str] = None
    if terms:
        for i, term in enumerate(terms):
            params[f"q{i}"] = term
            params[f"like{i}"] = f"%{term}%"
        params["qfull"] = full_query
        params["likefull"] = f"%{full_query}%"
        tsquery = build_or_tsquery(full_query) or build_or_tsquery(" ".join(terms))
        if tsquery:
            params["tq"] = tsquery

        if caps.is_postgres:
            match_sql = " OR ".join(
                _pg_term_condition(i, caps, weights) for i in range(len(terms))
            )
        else:
            match_sql = " OR ".join(_sqlite_term_condition(i) for i in range(len(terms)))
        conditions.append(f"({match_sql})")

    where_sql = " AND ".join(
        [
            "p.status = :status",
            # 人像隐私：sensitive 作品不进公开检索（脱敏图也不进，避免被索引扩散）
            "(p.privacy_level IS NULL OR p.privacy_level <> 'sensitive')",
            *conditions,
        ]
    )
    return _QueryParts(
        caps=caps,
        terms=terms,
        full_query=full_query,
        params=params,
        where_sql=where_sql,
    )


# ---------------------------------------------------------------------------
# 主检索：打分 + 过滤 + 分页（一条 SQL）
# ---------------------------------------------------------------------------

async def search_photos(
    db: AsyncSession,
    query: Optional[str] = None,
    *,
    keywords: Optional[Sequence[str]] = None,
    filters: Optional[Mapping[str, Any]] = None,
    limit: int = 20,
    offset: int = 0,
    weights: Optional[LexicalWeights] = None,
) -> list[SearchHit]:
    """执行词法检索。

    Args:
        query: 原始查询串（可为空，此时只按 filters 过滤并按时间倒序）。
        keywords: planner 解析出的关键词（可选，会与 query 一起参与检索）。
        filters: 结构化过滤，见 :func:`normalize_filters`。
        limit: 硬上限 100。
        offset: 偏移量。
        weights: 打分权重。
    """
    weights = weights or DEFAULT_WEIGHTS
    caps = await get_dialect_caps(db)
    query_parts = _prepare_query(caps, query, keywords, filters, weights)

    limit = max(1, min(int(limit or 20), LIMIT_MAX))
    offset = max(0, int(offset or 0))
    params = dict(query_parts.params)
    params["limit"] = limit
    params["offset"] = offset

    if caps.is_postgres:
        sql = _build_pg_search_sql(query_parts, weights)
    else:
        sql = _build_sqlite_search_sql(query_parts, weights)
    sql = sql.replace("/* FILTERS */", query_parts.where_sql)

    started = datetime.utcnow()
    result = await db.execute(text(sql), params)
    rows = result.mappings().all()
    elapsed_ms = (datetime.utcnow() - started).total_seconds() * 1000
    if elapsed_ms > 500:
        logger.warning(
            "lexical_search slow: %.1fms terms=%s limit=%d offset=%d",
            elapsed_ms,
            query_parts.terms,
            limit,
            offset,
        )

    hits: list[SearchHit] = []
    for row in rows:
        raw_score = float(row.get("raw_score") or 0.0)
        tags = _decode_json_list(row.get("tags_json"))
        classifications = _decode_json_dict(row.get("classifications_json"))
        description = row.get("description")
        hit = SearchHit(
            photo_id=row["id"],
            score=round(max(0.0, min(1.0, raw_score)), 4),
            title=row.get("title"),
            filename=row.get("filename"),
            author=row.get("author"),
            width=row.get("width"),
            height=row.get("height"),
            season=row.get("season"),
            category=row.get("category"),
            campus=row.get("campus"),
            description=description,
            search_document=row.get("search_document"),
            created_at=row.get("created_at"),
            published_at=row.get("published_at"),
            is_aigc=bool(row.get("is_aigc")),
            aigc_label=row.get("aigc_label"),
            tags=tags,
            classifications=classifications,
        )
        if query_parts.terms:
            hit.matched_fields = _matched_fields(
                query_parts.terms,
                hit.title,
                description or "",
                tags,
                classifications,
                hit.search_document or "",
            )
            hit.match_reason = build_match_reason(hit, query_parts.terms)
        hits.append(hit)
    return hits


async def count_matched(
    db: AsyncSession,
    query: Optional[str] = None,
    *,
    keywords: Optional[Sequence[str]] = None,
    filters: Optional[Mapping[str, Any]] = None,
    weights: Optional[LexicalWeights] = None,
) -> int:
    """命中总数（与 :func:`search_photos` 同一套过滤/匹配条件，一条 SQL）。"""
    weights = weights or DEFAULT_WEIGHTS
    caps = await get_dialect_caps(db)
    query_parts = _prepare_query(caps, query, keywords, filters, weights)
    sql = f"SELECT COUNT(*) AS cnt FROM photos p WHERE {query_parts.where_sql}"
    row = (await db.execute(text(sql), query_parts.params)).first()
    return int(row[0] or 0) if row is not None else 0


async def get_hits_by_ids(
    db: AsyncSession,
    photo_ids: Sequence[str],
) -> dict[str, SearchHit]:
    """按 id 批量取详情（供向量融合使用，一条 SQL，≤100 条）。"""
    ids = [str(pid) for pid in photo_ids if pid][:LIMIT_MAX]
    if not ids:
        return {}
    caps = await get_dialect_caps(db)
    params: dict[str, Any] = {"status": APPROVED_STATUS}
    names: list[str] = []
    for i, photo_id in enumerate(ids):
        params[f"id{i}"] = photo_id
        names.append(f":id{i}")
    if caps.is_postgres:
        detail_columns = (
            ", LEFT(COALESCE(p.description, ''), 500) AS description"
            ", COALESCE(p.search_document, '') AS search_document"
            ", COALESCE(p.search_document, '') AS search_document"
            ", COALESCE(("
            "  SELECT json_agg(x.name) FROM ("
            "    SELECT t.name FROM photo_tags pt JOIN tags t ON t.id = pt.tag_id"
            "    WHERE pt.photo_id = p.id"
            f"    ORDER BY t.usage_count DESC, t.name LIMIT {MAX_TAGS_PER_HIT}"
            "  ) x), '[]'::json) AS tags_json"
            ", COALESCE(("
            "  SELECT json_object_agg(tf.key, tn.name)"
            "  FROM photo_classifications pc"
            "  JOIN taxonomy_facets tf ON tf.id = pc.facet_id"
            "  JOIN taxonomy_nodes tn ON tn.id = pc.node_id"
            "  WHERE pc.photo_id = p.id AND tf.is_active = TRUE"
            "  AND tn.is_active = TRUE AND tn.is_selectable = TRUE"
            "), '{}'::json) AS classifications_json"
        )
    else:
        detail_columns = (
            ", substr(COALESCE(p.description, ''), 1, 500) AS description"
            ", COALESCE(p.search_document, '') AS search_document"
            ", COALESCE(p.search_document, '') AS search_document"
            ", COALESCE(("
            "  SELECT group_concat(t.name, char(31)) FROM photo_tags pt"
            "  JOIN tags t ON t.id = pt.tag_id WHERE pt.photo_id = p.id"
            "), '[]') AS tags_json"
            ", '{}' AS classifications_json"
        )
    sql = (
        "SELECT p.id, p.filename, p.title, p.author, p.width, p.height, p.season, p.category,"
        " p.campus, p.created_at, p.published_at, p.is_aigc, p.aigc_label"
        f"{detail_columns}"
        f" FROM photos p WHERE p.status = :status AND p.id IN ({', '.join(names)})"
        " AND (p.privacy_level IS NULL OR p.privacy_level <> 'sensitive')"
    )
    rows = (await db.execute(text(sql), params)).mappings().all()
    hits: dict[str, SearchHit] = {}
    for row in rows:
        hits[row["id"]] = SearchHit(
            photo_id=row["id"],
            score=0.0,
            title=row.get("title"),
            filename=row.get("filename"),
            author=row.get("author"),
            width=row.get("width"),
            height=row.get("height"),
            season=row.get("season"),
            category=row.get("category"),
            campus=row.get("campus"),
            description=row.get("description"),
            search_document=row.get("search_document"),
            created_at=row.get("created_at"),
            published_at=row.get("published_at"),
            is_aigc=bool(row.get("is_aigc")),
            aigc_label=row.get("aigc_label"),
            tags=_decode_json_list(row.get("tags_json")),
            classifications=_decode_json_dict(row.get("classifications_json")),
        )
    return hits


def _build_pg_search_sql(query_parts: _QueryParts, weights: LexicalWeights) -> str:
    score_sql = _pg_score_sql(
        query_parts.terms, query_parts.caps, weights, has_tsquery="tq" in query_parts.params
    )
    detail_columns = (
        ", LEFT(COALESCE(p.description, ''), 500) AS description"
        ", COALESCE(p.search_document, '') AS search_document"
        ", COALESCE(("
        "  SELECT json_agg(x.name) FROM ("
        "    SELECT t.name FROM photo_tags pt JOIN tags t ON t.id = pt.tag_id"
        "    WHERE pt.photo_id = p.id"
        f"    ORDER BY t.usage_count DESC, t.name LIMIT {MAX_TAGS_PER_HIT}"
        "  ) x), '[]'::json) AS tags_json"
        ", COALESCE(("
        "  SELECT json_object_agg(tf.key, tn.name)"
        "  FROM photo_classifications pc"
        "  JOIN taxonomy_facets tf ON tf.id = pc.facet_id"
        "  JOIN taxonomy_nodes tn ON tn.id = pc.node_id"
        "  WHERE pc.photo_id = p.id AND tf.is_active = TRUE"
        "  AND tn.is_active = TRUE AND tn.is_selectable = TRUE"
        "), '{}'::json) AS classifications_json"
    )
    return f"""
WITH scored AS (
    SELECT p.id AS id,
           ({score_sql}) AS raw_score,
           p.published_at AS published_at,
           p.created_at AS created_at
    FROM photos p
    WHERE /* FILTERS */
),
paged AS (
    SELECT id, raw_score, published_at, created_at
    FROM scored
    ORDER BY raw_score DESC, published_at DESC NULLS LAST, created_at DESC
    LIMIT :limit OFFSET :offset
)
SELECT p.id, p.filename, p.title, p.author, p.width, p.height,
       p.season, p.category, p.campus, p.created_at, p.published_at,
       p.is_aigc, p.aigc_label, paged.raw_score{detail_columns}
FROM paged
JOIN photos p ON p.id = paged.id
ORDER BY paged.raw_score DESC, paged.published_at DESC NULLS LAST, paged.created_at DESC
"""


def _build_sqlite_search_sql(query_parts: _QueryParts, weights: LexicalWeights) -> str:
    score_sql = _sqlite_score_sql(query_parts.terms, weights)
    detail_columns = (
        ", substr(COALESCE(p.description, ''), 1, 500) AS description"
        ", COALESCE(p.search_document, '') AS search_document"
        ", COALESCE(("
        "  SELECT group_concat(t.name, char(31)) FROM photo_tags pt"
        "  JOIN tags t ON t.id = pt.tag_id WHERE pt.photo_id = p.id"
        "), '[]') AS tags_json"
        ", '{}' AS classifications_json"
    )
    return f"""
WITH scored AS (
    SELECT p.id AS id,
           ({score_sql}) AS raw_score,
           p.published_at AS published_at,
           p.created_at AS created_at
    FROM photos p
    WHERE /* FILTERS */
),
paged AS (
    SELECT id, raw_score, published_at, created_at
    FROM scored
    ORDER BY raw_score DESC, COALESCE(published_at, created_at) DESC
    LIMIT :limit OFFSET :offset
)
SELECT p.id, p.filename, p.title, p.author, p.width, p.height,
       p.season, p.category, p.campus, p.created_at, p.published_at,
       p.is_aigc, p.aigc_label, paged.raw_score{detail_columns}
FROM paged
JOIN photos p ON p.id = paged.id
ORDER BY paged.raw_score DESC, COALESCE(paged.published_at, paged.created_at) DESC
"""


# ---------------------------------------------------------------------------
# facet 聚合（一条 SQL）
# ---------------------------------------------------------------------------

async def compute_facets(
    db: AsyncSession,
    query: Optional[str] = None,
    *,
    keywords: Optional[Sequence[str]] = None,
    filters: Optional[Mapping[str, Any]] = None,
    top_tags: int = 20,
    weights: Optional[LexicalWeights] = None,
) -> FacetResult:
    """对当前查询的命中集合做 season / category / campus / tag 计数（一条聚合 SQL）。

    注意：facet 统计固定使用调用方传入的 filters（不剔除当前 facet 自身），
    前端切换筛选项时由页面自行传入新条件；保持语义简单可预期。
    """
    weights = weights or DEFAULT_WEIGHTS
    caps = await get_dialect_caps(db)
    query_parts = _prepare_query(caps, query, keywords, filters, weights)

    cte_keyword = "MATERIALIZED " if caps.is_postgres else ""
    sql = f"""
WITH matched AS {cte_keyword}(
    SELECT p.id AS id, p.season AS season, p.category AS category, p.campus AS campus
    FROM photos p
    WHERE {query_parts.where_sql}
)
SELECT facet, value, cnt FROM (
    SELECT 'total' AS facet, '' AS value, COUNT(*) AS cnt FROM matched
    UNION ALL
    SELECT 'season', season, COUNT(*) FROM matched
    WHERE season IS NOT NULL AND season <> '' GROUP BY season
    UNION ALL
    SELECT 'category', category, COUNT(*) FROM matched
    WHERE category IS NOT NULL AND category <> '' GROUP BY category
    UNION ALL
    SELECT 'campus', campus, COUNT(*) FROM matched
    WHERE campus IS NOT NULL AND campus <> '' GROUP BY campus
    UNION ALL
    SELECT 'tag', t.name, COUNT(DISTINCT m.id) FROM matched m
    JOIN photo_tags pt ON pt.photo_id = m.id
    JOIN tags t ON t.id = pt.tag_id
    GROUP BY t.name
) f
ORDER BY facet, cnt DESC, value
"""
    result = await db.execute(text(sql), query_parts.params)
    facets = FacetResult()
    for row in result.mappings().all():
        facet = row["facet"]
        value = row["value"] or ""
        count = int(row["cnt"] or 0)
        if facet == "total":
            facets.total = count
        elif facet == "season":
            facets.seasons.append(FacetValue(value=value, count=count))
        elif facet == "category":
            facets.categories.append(FacetValue(value=value, count=count))
        elif facet == "campus":
            facets.campuses.append(FacetValue(value=value, count=count))
        elif facet == "tag":
            facets.tags.append(FacetValue(value=value, count=count))
    if top_tags and len(facets.tags) > top_tags:
        facets.tags = facets.tags[:top_tags]
    return facets


# ---------------------------------------------------------------------------
# 子串补全 / suggest
# ---------------------------------------------------------------------------

async def suggest(
    db: AsyncSession,
    prefix: str,
    *,
    limit: int = 10,
) -> list[dict[str, str]]:
    """轻量子串补全：标签 / 照片标题 / taxonomy 节点名。

    走 pg_trgm GIN 索引（``ILIKE '%prefix%'`` 与 ``%`` 相似度），limit ≤ 10。
    """
    prefix = (prefix or "").strip()
    if not prefix:
        return []
    limit = max(1, min(int(limit or 10), 10))
    caps = await get_dialect_caps(db)
    params: dict[str, Any] = {
        "status": APPROVED_STATUS,
        "like": f"%{prefix}%",
        "prefix": prefix.lower(),
        "limit": limit,
    }

    trgm_sql = ""
    title_trgm = ""
    node_trgm = ""
    if caps.is_postgres and caps.trgm:
        trgm_sql = " OR t.name % :prefix OR similarity(t.name, :prefix) >= 0.3"
        title_trgm = " OR p.title % :prefix"
        node_trgm = " OR tn.name % :prefix"

    sql = f"""
SELECT text, kind, freq FROM (
    SELECT t.name AS text, 'tag' AS kind, COALESCE(t.usage_count, 0) AS freq
    FROM tags t
    WHERE t.name IS NOT NULL AND t.name <> '' AND (lower(t.name) LIKE lower(:like){trgm_sql})
    UNION ALL
    SELECT DISTINCT p.title AS text, 'title' AS kind, 0 AS freq
    FROM photos p
    WHERE p.status = :status AND p.title IS NOT NULL AND p.title <> ''
      AND (p.privacy_level IS NULL OR p.privacy_level <> 'sensitive')
      AND (lower(p.title) LIKE lower(:like){title_trgm})
    UNION ALL
    SELECT tn.name AS text, 'taxonomy' AS kind, 0 AS freq
    FROM taxonomy_nodes tn
    WHERE tn.is_active AND tn.name IS NOT NULL AND tn.name <> ''
      AND (lower(tn.name) LIKE lower(:like){node_trgm})
) s
WHERE text IS NOT NULL AND text <> ''
ORDER BY CASE WHEN lower(text) = :prefix THEN 0 ELSE 1 END, freq DESC, length(text)
LIMIT :limit
"""
    try:
        rows = (await db.execute(text(sql), params)).mappings().all()
    except Exception:  # noqa: BLE001 - suggest 失败不应影响主流程
        logger.warning("lexical_search.suggest failed", exc_info=True)
        return []

    suggestions: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        value = str(row["text"] or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        suggestions.append({"text": value, "type": str(row["kind"])})
        if len(suggestions) >= limit:
            break
    return suggestions


# ---------------------------------------------------------------------------
# 详情 / 工具
# ---------------------------------------------------------------------------

def _decode_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                decoded = json.loads(stripped)
                if isinstance(decoded, list):
                    return [str(item) for item in decoded if item]
            except (ValueError, TypeError):
                return []
        return [item for item in stripped.split("\x1f") if item]
    return []


def _decode_json_dict(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items() if item}
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                decoded = json.loads(stripped)
                if isinstance(decoded, dict):
                    return {str(key): str(item) for key, item in decoded.items() if item}
            except (ValueError, TypeError):
                return {}
    return {}


def _matched_fields(
    terms: Sequence[str],
    title: Optional[str],
    description: str,
    tags: Sequence[str],
    classifications: Mapping[str, str],
    search_document: str = "",
) -> list[str]:
    """解释「为什么命中」：标题 / 描述 / 标签 / 分类 中命中的词。"""
    haystacks: list[tuple[str, str]] = [
        ("title", title or ""),
        ("description", description or ""),
        ("caption", search_document or ""),
    ]
    for tag in tags:
        haystacks.append((f"tag:{tag}", tag))
    for key, value in classifications.items():
        haystacks.append((f"taxonomy:{key}", str(value)))

    fields: list[str] = []
    for label, haystack in haystacks:
        haystack_cf = haystack.casefold()
        if not haystack_cf:
            continue
        for term in terms:
            if term.casefold() in haystack_cf:
                if label not in fields:
                    fields.append(label)
                break
    return fields[:8]


def build_match_reason(hit: SearchHit, terms: Optional[Sequence[str]] = None) -> str:
    """用 matched_fields 生成一句话匹配理由（不额外调用 LLM）。"""
    terms = list(terms or [])
    fields = hit.matched_fields
    tag_fields = [item.split(":", 1)[1] for item in fields if item.startswith("tag:")]
    taxonomy_fields = [
        item.split(":", 1)[1] for item in fields if item.startswith("taxonomy:")
    ]
    parts: list[str] = []
    if "title" in fields:
        parts.append("标题匹配")
    if "description" in fields:
        parts.append("描述匹配")
    if "caption" in fields:
        parts.append("画面描述匹配")
    if tag_fields:
        parts.append("标签：" + "、".join(tag_fields[:3]))
    if taxonomy_fields:
        parts.append("分类：" + "、".join(taxonomy_fields[:2]))
    if not parts:
        if terms:
            parts.append("与「" + "」/「".join(terms[:2]) + "」语义相近")
        else:
            parts.append("符合筛选条件")
    return "；".join(parts)


def is_degraded_lexical(caps: _DialectCaps) -> bool:
    """是否处于降级词法模式（无 pg_trgm / 非 PG）。"""
    return not (caps.is_postgres and caps.trgm)
