"""图片检索 API —— Agent 驱动（planner → 词法/向量检索 → 解释器）。

兼容旧接口：GET /api/v1/search 的 results[].photo_id / score / tags / classifications
字段保持不变；新增 mode=agent|fast、offset、结构化过滤、分页与解释信息。

附加端点：
- GET /api/v1/search/facets   facet 计数（season / category / campus / tag）
- GET /api/v1/search/suggest  标签/标题/taxonomy 补全
- GET /api/v1/search/traces/{trace_id}  检索 trace（仅管理员）

公开检索不要求登录；默认 agent 模式，AGENT_SEARCH_ENABLED=false 时强制 fast。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_admin_user, get_db
from app.models.search_trace import AgentSearchTrace
from app.models.tag import PhotoTag, Tag
from app.services import lexical_search
from app.services.agent_search import run_agent_search
from app.services.agent_search.types import AgentSearchResult
from app.services.lexical_search import FacetResult, SearchHit
from app.services.spectrum import PALETTE_BY_KEY
from app.services.visual_probe import (
    MAX_PROBE_BYTES,
    ProbeError,
    build_visual_probe,
    probe_source_label,
)
from app.services.visual_similarity import search_visual

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()

# 以图搜图是公开端点，按 IP 限流，避免被当成免费的图片识别/抓取接口。
limiter = Limiter(key_func=get_remote_address)

# 旧端点保留的结构化筛选参数（→ filters）
_TAXONOMY_QUERY_KEYS = (
    "landmark",
    "building",
    "gallery_series",
    "gallery_year",
    "award_level",
    "photo_type",
    "source_type",
    "facility",
    "landscape",
    "natural_phenomenon",
    "technique",
    "animal",
    "plant",
)


# ---- Response schema ----

class SearchStepModel(BaseModel):
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    result_count: Optional[int] = None
    latency_ms: Optional[float] = None
    status: str = "ok"


class SearchIntentModel(BaseModel):
    query: str = ""
    keywords: list[str] = Field(default_factory=list)
    filters: dict[str, Any] = Field(default_factory=dict)
    semantic_query: str = ""
    assumed: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_clarification: bool = False
    expected_facets: list[str] = Field(default_factory=list)
    source: str = "heuristic"


class FacetValueModel(BaseModel):
    value: str
    label: str
    count: int


class SearchFacetsModel(BaseModel):
    season: list[FacetValueModel] = Field(default_factory=list)
    category: list[FacetValueModel] = Field(default_factory=list)
    campus: list[FacetValueModel] = Field(default_factory=list)
    tag: list[FacetValueModel] = Field(default_factory=list)
    total: int = 0


class SearchPhotoResult(BaseModel):
    """单张照片结果（兼容旧字段 + 前端卡片所需摘要，不含隐私字段）。"""

    photo_id: str = Field(..., description="Photo UUID")
    id: str = Field(..., description="Photo UUID（前端卡片直接使用）")
    kind: str = Field("photo", description="作品类型：photo / aigc")
    score: float = Field(..., ge=0.0, le=1.0, description="Relevance score (0-1)")
    tags: list[str] = Field(default_factory=list, description="Associated tag names")
    classifications: dict[str, str] = Field(
        default_factory=dict,
        description="Taxonomy classifications {facet_key: node_name}",
    )
    matched_fields: list[str] = Field(default_factory=list, description="命中字段")
    match_reason: Optional[str] = Field(None, description="匹配理由（中文）")
    title: Optional[str] = None
    filename: Optional[str] = None
    author: Optional[str] = Field(None, description="作者署名（用户自填，非真实姓名）")
    thumb_url: Optional[str] = Field(None, description="缩略图路径")
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = None
    season: Optional[str] = None
    category: Optional[str] = None
    campus: Optional[str] = None
    is_aigc: bool = Field(False, description="是否 AIGC（法定显式标识用）")
    aigc_label: Optional[str] = Field(None, description="AIGC 显式角标文案（如「AI 生成」）")
    blurhash: Optional[str] = None
    created_at: Optional[datetime] = None
    published_at: Optional[datetime] = None


class SearchResponse(BaseModel):
    """检索响应（旧字段 + Agent 扩展字段）。"""

    results: list[SearchPhotoResult] = Field(default_factory=list)
    total: int = Field(..., ge=0, description="匹配总数（用于分页）")
    query_time_ms: float = Field(..., ge=0, description="端到端耗时（含模型调用）")
    search_mode: str = Field("agent", description="Search mode used: agent / fast")
    fallback_reason: Optional[str] = Field(None, description="降级/回退原因")
    index_version: Optional[str] = Field(None, description="索引实现标识，用于排障")
    # Agent 扩展
    explanation: Optional[str] = Field(None, description="结果解释（1-3 句中文）")
    steps: list[SearchStepModel] = Field(default_factory=list, description="工具调用轨迹")
    intent: Optional[SearchIntentModel] = Field(None, description="解析后的检索意图")
    clarify: Optional[str] = Field(None, description="需要澄清时的追问")
    clarify_options: list[str] = Field(default_factory=list)
    facets: Optional[SearchFacetsModel] = None
    trace_id: Optional[str] = None


class SuggestItemModel(BaseModel):
    text: str
    type: str = "tag"


class SuggestResponse(BaseModel):
    suggestions: list[str] = Field(default_factory=list)
    items: list[SuggestItemModel] = Field(default_factory=list)
    prefix: str = ""


class VisualSearchQueryModel(BaseModel):
    """探针图摘要（前端用来说明“我们看到了什么”）。"""

    filename: Optional[str] = Field(None, description="上传文件名（仅展示）")
    width: int
    height: int
    aspect_ratio: Optional[float] = None
    palette: Optional[str] = Field(None, description="主色卡 key：pink/gold/green/blue/ink")
    palette_name: Optional[str] = Field(None, description="主色卡中文名")
    palette_hex: Optional[str] = None


class VisualSearchResponse(BaseModel):
    """以图搜图响应；results 与文本检索同构，前端可复用结果卡片。"""

    results: list[SearchPhotoResult] = Field(default_factory=list)
    total: int = Field(..., ge=0)
    query_time_ms: float = Field(..., ge=0)
    mode: str = Field("visual", description="固定为 visual")
    query: VisualSearchQueryModel


# ---- 请求参数 → filters ----

def _collect_filters(
    *,
    season: Optional[str] = None,
    campus: Optional[str] = None,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    captured_from: Optional[str] = None,
    captured_to: Optional[str] = None,
    published_from: Optional[str] = None,
    published_to: Optional[str] = None,
    taxonomy_values: Optional[dict[str, Optional[str]]] = None,
) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key, value in {
        "season": season,
        "campus": campus,
        "category": category,
        "tag": tag,
        "captured_from": captured_from,
        "captured_to": captured_to,
        "published_from": published_from,
        "published_to": published_to,
    }.items():
        if value:
            filters[key] = value
    for key, value in (taxonomy_values or {}).items():
        if value:
            filters[key] = value
    return filters


def _to_result_item(hit: SearchHit) -> SearchPhotoResult:
    thumb_url = f"/api/v1/photos/{hit.photo_id}/image/thumbnail"
    aspect_ratio: Optional[float] = None
    if hit.width and hit.height:
        try:
            aspect_ratio = round(float(hit.width) / float(hit.height), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            aspect_ratio = None
    return SearchPhotoResult(
        photo_id=hit.photo_id,
        id=hit.photo_id,
        kind="aigc" if hit.is_aigc else "photo",
        score=round(max(0.0, min(1.0, float(hit.score or 0.0))), 4),
        tags=list(hit.tags or []),
        classifications=dict(hit.classifications or {}),
        matched_fields=list(hit.matched_fields or []),
        match_reason=hit.match_reason,
        title=hit.title,
        filename=hit.filename,
        author=hit.author,
        thumb_url=thumb_url,
        width=hit.width,
        height=hit.height,
        aspect_ratio=aspect_ratio,
        season=hit.season,
        category=hit.category,
        campus=hit.campus,
        is_aigc=bool(hit.is_aigc),
        aigc_label=hit.aigc_label,
        blurhash=None,
        created_at=hit.created_at,
        published_at=hit.published_at,
    )


def _facets_model(facets: Optional[FacetResult]) -> Optional[SearchFacetsModel]:
    if facets is None:
        return None
    data = facets.to_dict()
    return SearchFacetsModel(**data)


def _intent_model(result: AgentSearchResult) -> Optional[SearchIntentModel]:
    if result.intent is None:
        return None
    data = result.intent.to_dict()
    return SearchIntentModel(**data)


def _build_response(result: AgentSearchResult) -> SearchResponse:
    return SearchResponse(
        results=[_to_result_item(hit) for hit in result.results],
        total=int(result.total or 0),
        query_time_ms=round(float(result.query_time_ms or 0.0), 2),
        search_mode=result.search_mode or "agent",
        fallback_reason=result.fallback_reason,
        index_version=result.index_version,
        explanation=result.explanation,
        steps=[SearchStepModel(**step.to_dict()) for step in result.steps],
        intent=_intent_model(result),
        clarify=result.clarify,
        clarify_options=list(result.clarify_options or []),
        facets=_facets_model(result.facets),
        trace_id=result.trace_id,
    )


def _visual_result_item(
    hit,
    tags: list[str],
) -> SearchPhotoResult:
    """把一条视觉相似命中转成与文本检索同构的结果项（前端复用卡片）。"""
    photo = hit.photo
    aspect_ratio: Optional[float] = None
    if photo.width and photo.height:
        try:
            aspect_ratio = round(float(photo.width) / float(photo.height), 4)
        except (TypeError, ValueError, ZeroDivisionError):
            aspect_ratio = None
    return SearchPhotoResult(
        photo_id=str(photo.id),
        id=str(photo.id),
        kind="aigc" if photo.is_aigc else "photo",
        score=round(max(0.0, min(1.0, float(hit.score))), 4),
        tags=list(tags),
        classifications={},
        matched_fields=["visual"],
        match_reason="；".join(hit.reasons) or None,
        title=photo.title,
        filename=photo.filename,
        author=photo.author,
        thumb_url=f"/api/v1/photos/{photo.id}/image/thumbnail",
        width=photo.width,
        height=photo.height,
        aspect_ratio=aspect_ratio,
        season=photo.season,
        category=photo.category,
        campus=photo.campus,
        is_aigc=bool(photo.is_aigc),
        aigc_label=photo.aigc_label if photo.is_aigc else None,
        blurhash=None,
        created_at=photo.created_at,
        published_at=photo.published_at,
    )


async def _tags_for_photos(
    db: AsyncSession, photo_ids: list[str]
) -> dict[str, list[str]]:
    """批量取自由标签（以图搜图结果卡片展示用，避免 N+1）。"""
    if not photo_ids:
        return {}
    rows = (
        await db.execute(
            select(PhotoTag.photo_id, Tag.name)
            .join(Tag, Tag.id == PhotoTag.tag_id)
            .where(PhotoTag.photo_id.in_(photo_ids))
        )
    ).all()
    tags_by_photo: dict[str, list[str]] = {}
    for photo_id, name in rows:
        if name:
            tags_by_photo.setdefault(str(photo_id), []).append(name)
    return tags_by_photo


@router.post(
    "/search/visual",
    response_model=VisualSearchResponse,
    summary="以图搜图（上传一张图，找站内视觉相似作品）",
)
@limiter.limit("10/minute")
async def search_by_image(
    request: Request,
    file: UploadFile = File(..., description="JPEG / PNG / WebP，不超过 8MB"),
    limit: int = Query(12, ge=1, le=30, description="最多返回条数"),
    db: AsyncSession = Depends(get_db),
):
    """公开端点，不需要登录；探针图只在内存里算签名，不落盘、不写库、无 AI 成本。"""
    started = time.perf_counter()
    if getattr(file, "size", None) and file.size > MAX_PROBE_BYTES:
        raise HTTPException(status_code=413, detail="图片不能超过 8MB，请压缩后再试")
    data = await file.read(MAX_PROBE_BYTES + 1)
    try:
        probe = build_visual_probe(data)
    except ProbeError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc

    hits = await search_visual(db, probe, limit=limit)
    tags_by_photo = await _tags_for_photos(db, [str(hit.photo.id) for hit in hits])
    results = [
        _visual_result_item(hit, tags_by_photo.get(str(hit.photo.id), []))
        for hit in hits
    ]

    spectrum = probe.exif_data.get("_spectrum")
    palette_key: Optional[str] = None
    palette_hex: Optional[str] = None
    if isinstance(spectrum, dict):
        candidate_key = spectrum.get("palette")
        if isinstance(candidate_key, str) and candidate_key in PALETTE_BY_KEY:
            palette_key = candidate_key
            hex_value = spectrum.get("hex")
            if isinstance(hex_value, str):
                palette_hex = hex_value
    palette = PALETTE_BY_KEY.get(palette_key or "")
    try:
        aspect = round(probe.width / probe.height, 4) if probe.height else None
    except ZeroDivisionError:
        aspect = None

    return VisualSearchResponse(
        results=results,
        total=len(results),
        query_time_ms=round((time.perf_counter() - started) * 1000, 2),
        mode="visual",
        query=VisualSearchQueryModel(
            filename=probe_source_label(file.filename) if file.filename else None,
            width=probe.width,
            height=probe.height,
            aspect_ratio=aspect,
            palette=palette_key,
            palette_name=palette.name if palette else None,
            palette_hex=palette_hex,
        ),
    )


# ---- Endpoints ----

@router.get("/search", response_model=SearchResponse, summary="Photo search (agent / fast)")
async def search_photos(
    q: str = Query(..., min_length=1, max_length=500, description="Search query text"),
    mode: Literal["agent", "fast"] = Query(
        "agent", description="agent: 意图解析+检索+解释；fast: 纯词法确定性检索"
    ),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    offset: int = Query(0, ge=0, le=1000, description="Pagination offset"),
    season: Optional[str] = Query(None, description="季节 filter (e.g. 秋季)"),
    campus: Optional[str] = Query(None, description="校区 filter (e.g. 昌平校区)"),
    category: Optional[str] = Query(None, description="Category filter (e.g. landscape)"),
    tag: Optional[str] = Query(None, description="标签 filter (e.g. 樱花)"),
    captured_from: Optional[str] = Query(None, description="拍摄日期下界 YYYY-MM-DD"),
    captured_to: Optional[str] = Query(None, description="拍摄日期上界 YYYY-MM-DD"),
    published_from: Optional[str] = Query(None, description="发布日期下界 YYYY-MM-DD"),
    published_to: Optional[str] = Query(None, description="发布日期上界 YYYY-MM-DD"),
    landmark: Optional[str] = Query(None, description="Legacy 楼宇/地标 filter"),
    building: Optional[str] = Query(None, description="楼宇/建筑 filter"),
    gallery_series: Optional[str] = Query(None, description="专区 filter"),
    gallery_year: Optional[str] = Query(None, description="届次/年份 filter"),
    award_level: Optional[str] = Query(None, description="奖项 filter"),
    photo_type: Optional[str] = Query(None, description="类别 filter"),
    source_type: Optional[str] = Query(None, description="来源 filter"),
    facility: Optional[str] = Query(None, description="设施 filter"),
    landscape: Optional[str] = Query(None, description="景观 filter"),
    natural_phenomenon: Optional[str] = Query(None, description="自然现象 filter"),
    technique: Optional[str] = Query(None, description="表现手法 filter"),
    animal: Optional[str] = Query(None, description="动物 filter"),
    plant: Optional[str] = Query(None, description="植物 filter"),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse:
    """自然语言 + 结构化筛选检索已通过审核的照片。

    - ``mode=agent``（默认）：planner 解析意图 → 确定性检索（词法 + facet，可选向量）
      → explainer 生成中文说明；任何环节失败自动降级，不会 500。
    - ``mode=fast``：跳过模型调用，直接走 pg_trgm + tsvector 词法检索。
    """
    filters = _collect_filters(
        season=season,
        campus=campus,
        category=category,
        tag=tag,
        captured_from=captured_from,
        captured_to=captured_to,
        published_from=published_from,
        published_to=published_to,
        taxonomy_values={
            "landmark": landmark,
            "building": building,
            "gallery_series": gallery_series,
            "gallery_year": gallery_year,
            "award_level": award_level,
            "photo_type": photo_type,
            "source_type": source_type,
            "facility": facility,
            "landscape": landscape,
            "natural_phenomenon": natural_phenomenon,
            "technique": technique,
            "animal": animal,
            "plant": plant,
        },
    )
    result = await run_agent_search(
        db,
        q,
        filters=filters or None,
        limit=limit,
        offset=offset,
        mode=mode,
    )
    # trace 是本接口唯一的写操作；flush 成功后显式提交，失败不影响响应
    if getattr(result, "trace", None) is not None:
        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            logger.warning("search: failed to commit agent search trace", exc_info=True)
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001
                pass
    return _build_response(result)


@router.get(
    "/search/facets",
    response_model=SearchFacetsModel,
    summary="Facet counts for a query",
)
async def search_facets(
    q: str = Query("", max_length=500, description="Search query text"),
    season: Optional[str] = Query(None),
    campus: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
) -> SearchFacetsModel:
    """对当前查询的命中集合统计 season / category / campus / tag 计数（一条聚合 SQL）。"""
    filters = _collect_filters(
        season=season, campus=campus, category=category, tag=tag
    )
    facets = await lexical_search.compute_facets(
        db, (q or "").strip() or None, keywords=None, filters=filters or None
    )
    return _facets_model(facets) or SearchFacetsModel()


@router.get("/search/suggest", response_model=SuggestResponse, summary="Search suggestions")
async def search_suggest(
    q: str = Query("", max_length=100, description="Prefix text"),
    limit: int = Query(8, ge=1, le=10, description="Max suggestions"),
    db: AsyncSession = Depends(get_db),
) -> SuggestResponse:
    """标签 / 照片标题 / taxonomy 节点名补全（pg_trgm GIN 索引）。"""
    prefix = (q or "").strip()
    if not prefix:
        return SuggestResponse(suggestions=[], items=[], prefix="")
    items = await lexical_search.suggest(db, prefix, limit=limit)
    suggestions = [item["text"] for item in items if item.get("text")]
    return SuggestResponse(
        suggestions=suggestions,
        items=[SuggestItemModel(text=item["text"], type=item.get("type", "tag")) for item in items],
        prefix=prefix,
    )


@router.get("/search/traces/{trace_id}", summary="Agent search trace (admin only)")
async def get_search_trace(
    trace_id: str,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_current_admin_user),
) -> dict[str, Any]:
    """按 trace_id 读取一次 Agent 检索的完整轨迹（仅管理员）。"""
    stmt = select(AgentSearchTrace).where(AgentSearchTrace.trace_id == trace_id)
    trace = (await db.execute(stmt)).scalars().first()
    if trace is None:
        raise HTTPException(status_code=404, detail="Search trace not found")
    return {
        "trace_id": trace.trace_id,
        "query": trace.query,
        "intent": trace.intent,
        "facets": trace.facets,
        "steps": trace.steps,
        "result_count": trace.result_count,
        "clarify": trace.clarify,
        "explanation": trace.explanation,
        "model_id": trace.model_id,
        "latency_ms": trace.latency_ms,
        "total_tokens": trace.total_tokens,
        "cost_usd": trace.cost_usd,
        "error": trace.error,
        "created_at": trace.created_at.isoformat() if trace.created_at else None,
    }
