"""站内 AI 生图（AI 创作台）接口。

- ``GET  /api/v1/aigc/config``：创作台配置（开关、尺寸档位、基础每日额度、模型名）
- ``GET  /api/v1/aigc/quota``：我的额度（每日基础 + 管理员赠送池）
- ``POST /api/v1/aigc/generations``：发起生成（登录 + 3 次/分钟 + 额度）
- ``GET  /api/v1/aigc/generations``：我的生成记录
- ``GET  /api/v1/aigc/generations/{id}``：状态（前端轮询）
- ``GET  /api/v1/aigc/generations/{id}/image``：取草稿图（仅本人/管理员）
- ``DELETE /api/v1/aigc/generations/{id}``：删除草稿（连本地文件一起删）

生成图只是「草稿」：发布仍走 ``POST /api/v1/photos/upload``（AIGC 强制声明 +
审核 + 隐式标识），本模块不直接创建作品。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user, get_db
from app.models.aigc_generation import AIGCGeneration
from app.models.user import User
from app.schemas.aigc_generation import (
    AigcConfigResponse,
    AigcGenerationCreate,
    AigcGenerationListResponse,
    AigcGenerationResponse,
    AigcQuotaResponse,
    AigcSizeOption,
)
from app.services import aigc_generation as aigc_service
from app.services import aigc_quota
from app.services.aigc_generation import (
    run_generation,
    size_dimensions,
)

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

_SIZE_LABELS = {
    "square": ("方图", "1:1"),
    "landscape": ("横图", "16:9"),
    "portrait": ("竖图", "9:16"),
}
_PROMPT_MAX = 300


def _size_options() -> list[AigcSizeOption]:
    options: list[AigcSizeOption] = []
    for key, raw in settings.AIGC_IMAGE_SIZES.items():
        try:
            width, height = size_dimensions(key)
        except ValueError:
            continue
        label, ratio = _SIZE_LABELS.get(key, (key, f"{width}:{height}"))
        options.append(
            AigcSizeOption(key=key, label=label, width=width, height=height, ratio=ratio)
        )
    return options


def _image_url(generation: AIGCGeneration) -> Optional[str]:
    if generation.status != "succeeded" or not generation.image_path:
        return None
    return f"/api/v1/aigc/generations/{generation.id}/image"


def _to_response(generation: AIGCGeneration) -> AigcGenerationResponse:
    return AigcGenerationResponse(
        id=generation.id,
        prompt=generation.prompt,
        size=generation.size_key,
        width=generation.width,
        height=generation.height,
        status=generation.status,  # type: ignore[arg-type]
        model=generation.model_id,
        quota_source=generation.quota_source or "daily",  # type: ignore[arg-type]
        image_url=_image_url(generation),
        error=generation.error,
        latency_ms=generation.latency_ms,
        cost_usd=float(generation.cost_usd or 0.0),
        created_at=generation.created_at,
        finished_at=generation.finished_at,
    )


def _quota_response(state: aigc_quota.QuotaState) -> AigcQuotaResponse:
    return AigcQuotaResponse(
        unlimited=state.unlimited,
        daily_limit=state.daily_limit,
        daily_used=state.daily_used,
        daily_remaining=state.daily_remaining,
        bonus_total=state.bonus_total,
        bonus_used=state.bonus_used,
        bonus_remaining=state.bonus_remaining,
        total_remaining=state.total_remaining,
    )


def _assert_owner_or_admin(generation: AIGCGeneration, user: User) -> None:
    if generation.user_id != user.id and getattr(user, "role", "") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="只能查看自己的生成记录")


@router.get("/config", response_model=AigcConfigResponse, summary="AI 创作台配置")
async def get_aigc_config() -> AigcConfigResponse:
    return AigcConfigResponse(
        enabled=aigc_service.generation_enabled(),
        model=settings.AIGC_IMAGE_MODEL,
        sizes=_size_options(),
        prompt_max=_PROMPT_MAX,
        daily_limit=int(settings.AIGC_IMAGE_DAILY_LIMIT),
        est_seconds=60,
    )


@router.post(
    "/generations",
    response_model=AigcGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="发起一次 AI 生图",
)
@limiter.limit("3/minute")
async def create_generation(
    request: Request,
    payload: AigcGenerationCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AigcGenerationResponse:
    if not aigc_service.generation_enabled():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI 创作台暂未开启（未配置生图渠道）",
        )

    prompt = (payload.prompt or "").strip()
    if len(prompt) < 2:
        raise HTTPException(status_code=400, detail="提示词太短，至少写 2 个字")
    if len(prompt) > _PROMPT_MAX:
        raise HTTPException(status_code=400, detail=f"提示词不能超过 {_PROMPT_MAX} 字")
    if payload.size not in settings.AIGC_IMAGE_SIZES:
        raise HTTPException(status_code=400, detail="不支持的尺寸档位")

    try:
        quota_source = await aigc_quota.resolve_quota_source(db, current_user)
    except aigc_quota.QuotaExhausted as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)
        ) from exc

    width, height = size_dimensions(payload.size)
    generation = AIGCGeneration(
        user_id=current_user.id,
        prompt=prompt,
        size_key=payload.size,
        status="queued",
        provider="dashscope",
        model_id=settings.AIGC_IMAGE_MODEL,
        quota_source=quota_source,
        width=width,
        height=height,
    )
    db.add(generation)
    await db.commit()
    await db.refresh(generation)

    background_tasks.add_task(run_generation, generation.id)
    return _to_response(generation)


@router.get(
    "/generations",
    response_model=AigcGenerationListResponse,
    summary="我的 AI 生成记录",
)
async def list_my_generations(
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AigcGenerationListResponse:
    stmt = (
        select(AIGCGeneration)
        .where(AIGCGeneration.user_id == current_user.id)
        .order_by(AIGCGeneration.created_at.desc())
        .limit(limit)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    total = int(
        (
            await db.execute(
                select(func.count())
                .select_from(AIGCGeneration)
                .where(AIGCGeneration.user_id == current_user.id)
            )
        ).scalar_one()
        or 0
    )
    return AigcGenerationListResponse(
        items=[_to_response(row) for row in rows],
        total=total,
        quota=_quota_response(await aigc_quota.get_quota(db, current_user)),
    )


@router.get("/quota", response_model=AigcQuotaResponse, summary="我的生图额度")
async def get_my_quota(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AigcQuotaResponse:
    """每日基础额度 + 管理员赠送池的实时余量（创作台轮询用）。"""
    return _quota_response(await aigc_quota.get_quota(db, current_user))


@router.get(
    "/generations/{generation_id}",
    response_model=AigcGenerationResponse,
    summary="查询生成状态",
)
async def get_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AigcGenerationResponse:
    generation = await db.get(AIGCGeneration, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="生成记录不存在")
    _assert_owner_or_admin(generation, current_user)
    if await aigc_service.expire_if_stale(db, generation):
        await db.refresh(generation)
    return _to_response(generation)


@router.get(
    "/generations/{generation_id}/image",
    summary="取 AI 生成草稿图",
    responses={200: {"content": {"image/png": {}, "image/jpeg": {}, "image/webp": {}}}},
)
async def get_generation_image(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    generation = await db.get(AIGCGeneration, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="生成记录不存在")
    _assert_owner_or_admin(generation, current_user)
    if generation.status != "succeeded" or not generation.image_path:
        raise HTTPException(status_code=404, detail="图片还没生成好")
    path = Path(settings.UPLOAD_DIR) / generation.image_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="生成图已被清理，请重新生成")
    filename = f"sakura-ai-{generation.id[:8]}.{generation.image_format or 'png'}"
    return FileResponse(
        path,
        media_type=aigc_service.image_media_type(generation.image_format),
        filename=filename,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.delete(
    "/generations/{generation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除生成草稿",
)
async def delete_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    generation = await db.get(AIGCGeneration, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="生成记录不存在")
    _assert_owner_or_admin(generation, current_user)
    if generation.image_path:
        path = Path(settings.UPLOAD_DIR) / generation.image_path
        try:
            path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - 文件系统异常不阻塞删除记录
            logger.warning("failed to remove generated file %s", path)
    await db.delete(generation)
    await db.commit()
