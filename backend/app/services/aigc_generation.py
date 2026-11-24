"""站内 AI 生图（AI 创作台）。

数据流：

1. ``POST /api/v1/aigc/generations`` 建一行 ``aigc_generations``（queued）后立即返回 202；
2. BackgroundTasks 里跑 :func:`run_generation`：调 DashScope 异步接口 → 轮询 → 下载图片
   → 落到 ``UPLOAD_DIR/generated/<id>.<ext>`` → 行置 succeeded（失败置 failed）；
3. 前端轮询状态，成功后预览；满意则用现有 ``/photos/upload``（AIGC 声明已填）发布，
   审核、隐式标识、变体生成全部复用既有链路。

约束：
- 生成图是**草稿**，不进作品表、不对外公开，仅作者本人可取；
- 只记提示词与用量元信息，不记录模型原始响应；
- httpx 只在这里用，调用失败一律转成 ``GenerationError``，由调用方落 ``failed``。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.models.aigc_generation import AIGCGeneration
from app.models.ai_usage import AIUsageEvent

logger = logging.getLogger(__name__)
settings = get_settings()

_GENERATED_SUBDIR = "generated"
_MAGIC = {
    b"\x89PNG\r\n\x1a\n": ("png", "image/png"),
    b"\xff\xd8\xff": ("jpeg", "image/jpeg"),
}
_MEDIA_TYPES = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp"}
_ERROR_MAX_CHARS = 500


class GenerationError(RuntimeError):
    """生图失败（渠道错误、超时、返回不可用图片等）。"""


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
def generation_enabled() -> bool:
    """创作台是否可用：开关打开且配置了百炼 API Key。"""
    return bool(settings.AIGC_GENERATION_ENABLED and settings.DASHSCOPE_API_KEY)


def api_key() -> str:
    key = (settings.DASHSCOPE_API_KEY or "").strip()
    if not key:
        raise GenerationError("未配置 DASHSCOPE_API_KEY，AI 创作台不可用")
    return key


def size_dimensions(size_key: str) -> tuple[int, int]:
    """返回 ``(width, height)``；未知档位抛 ValueError。"""
    raw = settings.AIGC_IMAGE_SIZES.get(size_key)
    if not raw:
        raise ValueError(f"未知尺寸档位：{size_key}")
    try:
        width, height = (int(part) for part in raw.split("*", 1))
    except (TypeError, ValueError) as exc:  # pragma: no cover - 配置错误
        raise ValueError(f"AIGC_IMAGE_SIZES 中的尺寸格式不合法：{raw}") from exc
    return width, height


def generated_dir() -> Path:
    path = Path(settings.UPLOAD_DIR) / _GENERATED_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def image_media_type(image_format: str | None) -> str:
    return _MEDIA_TYPES.get((image_format or "").lower(), "application/octet-stream")


def _detect_format(data: bytes) -> str | None:
    for magic, (fmt, _media) in _MAGIC.items():
        if data.startswith(magic):
            return fmt
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _truncate_error(message: str) -> str:
    text = " ".join((message or "").split())
    return text[:_ERROR_MAX_CHARS]


# ---------------------------------------------------------------------------
# DashScope 调用
# ---------------------------------------------------------------------------
async def _submit_task(client: httpx.AsyncClient, prompt: str, size: str) -> str:
    body: dict[str, Any] = {
        "model": settings.AIGC_IMAGE_MODEL,
        "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
        "parameters": {"size": size, "n": 1, "prompt_extend": True},
    }
    headers = {
        "Authorization": f"Bearer {api_key()}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    resp = await client.post(
        f"{settings.AIGC_IMAGE_API_BASE}/api/v1/services/aigc/image-generation/generation",
        headers=headers,
        json=body,
    )
    if resp.status_code >= 400:
        raise GenerationError(f"生图请求被拒绝（HTTP {resp.status_code}）：{resp.text[:200]}")
    try:
        task_id = resp.json()["output"]["task_id"]
    except (KeyError, TypeError, ValueError) as exc:
        raise GenerationError("生图接口返回异常：缺少 task_id") from exc
    return str(task_id)


async def _poll_task(client: httpx.AsyncClient, task_id: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {api_key()}"}
    deadline = time.monotonic() + max(10, int(settings.AIGC_IMAGE_TIMEOUT))
    while time.monotonic() < deadline:
        await asyncio.sleep(max(0.5, float(settings.AIGC_IMAGE_POLL_INTERVAL)))
        resp = await client.get(
            f"{settings.AIGC_IMAGE_API_BASE}/api/v1/tasks/{task_id}", headers=headers
        )
        if resp.status_code >= 400:
            raise GenerationError(f"查询生图任务失败（HTTP {resp.status_code}）")
        payload = resp.json()
        output = payload.get("output") or {}
        status = str(output.get("task_status") or "").upper()
        if status == "SUCCEEDED":
            return output
        if status in {"FAILED", "CANCELED", "UNKNOWN"}:
            message = payload.get("message") or output.get("message") or status
            raise GenerationError(f"生图任务失败：{message}")
    raise GenerationError("生图超时：超过等待上限仍未完成")


def _extract_image_url(output: dict[str, Any]) -> str:
    choices = output.get("choices") or []
    if not choices:
        raise GenerationError("生图结果为空：没有返回图片")
    content = (choices[0].get("message") or {}).get("content") or []
    for item in content:
        url = item.get("image") if isinstance(item, dict) else None
        if url:
            return str(url)
    raise GenerationError("生图结果缺少图片地址")


async def _download_image(client: httpx.AsyncClient, url: str) -> bytes:
    resp = await client.get(url, follow_redirects=True)
    if resp.status_code >= 400:
        raise GenerationError(f"下载生成图失败（HTTP {resp.status_code}）")
    data = resp.content
    if not data:
        raise GenerationError("下载生成图失败：内容为空")
    if len(data) > int(settings.AIGC_IMAGE_MAX_BYTES):
        raise GenerationError("生成图超过大小上限，已放弃保存")
    return data


async def generate_image(prompt: str, size_key: str) -> dict[str, Any]:
    """提交并等待生成完成，返回 ``{data, format, task_id, latency_ms}``。"""
    width, height = size_dimensions(size_key)
    size = settings.AIGC_IMAGE_SIZES[size_key]
    started = time.monotonic()
    timeout = httpx.Timeout(30.0, connect=10.0)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            task_id = await _submit_task(client, prompt, size)
            output = await _poll_task(client, task_id)
            url = _extract_image_url(output)
            data = await _download_image(client, url)
    except GenerationError:
        raise
    except httpx.HTTPError as exc:
        raise GenerationError(f"生图渠道网络错误：{exc.__class__.__name__}") from exc
    fmt = _detect_format(data)
    if fmt is None:
        raise GenerationError("生成图格式无法识别（不是 PNG/JPEG/WebP）")
    return {
        "data": data,
        "format": fmt,
        "task_id": task_id,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "width": width,
        "height": height,
    }


# ---------------------------------------------------------------------------
# 每日额度
# ---------------------------------------------------------------------------
def _today_start_utc() -> datetime:
    """按东八区「今天」换算成 UTC naive（数据库统一存 UTC）。"""
    now_utc8 = datetime.utcnow() + timedelta(hours=8)
    local_midnight = datetime(now_utc8.year, now_utc8.month, now_utc8.day)
    return local_midnight - timedelta(hours=8)


async def count_today_generations(db: AsyncSession, user_id: str) -> int:
    stmt = (
        select(func.count())
        .select_from(AIGCGeneration)
        .where(
            AIGCGeneration.user_id == user_id,
            AIGCGeneration.created_at >= _today_start_utc(),
            AIGCGeneration.status != "failed",
        )
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


# ---------------------------------------------------------------------------
# 后台任务
# ---------------------------------------------------------------------------
def _generated_file_relpath(generation_id: str, image_format: str) -> str:
    return f"{_GENERATED_SUBDIR}/{generation_id}.{image_format}"


def _record_usage(
    db: AsyncSession,
    generation: AIGCGeneration,
    *,
    success: bool,
    latency_ms: int,
    error: str | None = None,
) -> None:
    cost = float(settings.AIGC_IMAGE_PRICE_USD or 0.0) if success else 0.0
    db.add(
        AIUsageEvent(
            operation="aigc.generate",
            provider="dashscope",
            model_id=generation.model_id,
            source="env",
            ref_type="aigc_generation",
            ref_id=generation.id,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost_usd=cost,
            latency_ms=max(0, latency_ms),
            success=success,
            error=error,
        )
    )
    generation.cost_usd = cost


async def expire_if_stale(
    db: AsyncSession, generation: AIGCGeneration, *, stale_seconds: int | None = None
) -> bool:
    """把卡在 queued/running 太久的任务标 failed（进程重启/崩溃兜底）。"""
    if generation.status not in {"queued", "running"}:
        return False
    threshold = stale_seconds or (int(settings.AIGC_IMAGE_TIMEOUT) + 120)
    if generation.updated_at is None:
        return False
    if datetime.utcnow() - generation.updated_at < timedelta(seconds=threshold):
        return False
    generation.status = "failed"
    generation.error = "生成任务中断（服务重启或超时），请重新生成"
    generation.finished_at = datetime.utcnow()
    await db.commit()
    return True


async def run_generation(
    generation_id: str,
    *,
    session_factory: Callable[[], Any] | None = None,
) -> None:
    """执行一次生成并提交；任何异常都落 ``failed``，不向上抛（后台任务）。"""
    factory = session_factory or AsyncSessionLocal
    async with factory() as db:
        generation = await db.get(AIGCGeneration, generation_id)
        if generation is None:
            logger.warning("aigc generation %s not found, skip", generation_id)
            return
        if generation.status not in {"queued", "running"}:
            return

        generation.status = "running"
        generation.error = None
        await db.commit()

        started = time.monotonic()
        try:
            result = await generate_image(generation.prompt, generation.size_key)
        except GenerationError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            generation.status = "failed"
            generation.error = _truncate_error(str(exc))
            generation.latency_ms = latency_ms
            generation.finished_at = datetime.utcnow()
            _record_usage(db, generation, success=False, latency_ms=latency_ms, error=generation.error)
            await db.commit()
            logger.warning("aigc generation %s failed: %s", generation.id, generation.error)
            return
        except Exception as exc:  # pragma: no cover - 防御性兜底
            latency_ms = int((time.monotonic() - started) * 1000)
            generation.status = "failed"
            generation.error = _truncate_error(f"生成异常：{exc.__class__.__name__}")
            generation.latency_ms = latency_ms
            generation.finished_at = datetime.utcnow()
            _record_usage(db, generation, success=False, latency_ms=latency_ms, error=generation.error)
            await db.commit()
            logger.exception("aigc generation %s crashed", generation.id)
            return

        rel_path = _generated_file_relpath(generation.id, result["format"])
        target = Path(settings.UPLOAD_DIR) / rel_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_bytes, result["data"])
        except OSError as exc:
            latency_ms = int((time.monotonic() - started) * 1000)
            generation.status = "failed"
            generation.error = _truncate_error(f"保存生成图失败：{exc}")
            generation.latency_ms = latency_ms
            generation.finished_at = datetime.utcnow()
            _record_usage(db, generation, success=False, latency_ms=latency_ms, error=generation.error)
            await db.commit()
            return

        latency_ms = int(result.get("latency_ms") or int((time.monotonic() - started) * 1000))
        generation.status = "succeeded"
        generation.image_path = rel_path
        generation.image_format = result["format"]
        generation.image_bytes = len(result["data"])
        generation.width = int(result.get("width") or 0) or None
        generation.height = int(result.get("height") or 0) or None
        generation.provider_task_id = result.get("task_id")
        generation.latency_ms = latency_ms
        generation.finished_at = datetime.utcnow()
        _record_usage(db, generation, success=True, latency_ms=latency_ms)
        await db.commit()
        logger.info(
            "aigc generation %s succeeded in %sms (%s bytes)",
            generation.id,
            latency_ms,
            generation.image_bytes,
        )
