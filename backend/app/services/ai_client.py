"""统一 AI 调用原语。

所有 AI 场景（审核快筛/复核、检索意图解析/结果解释、未来的打标/生图编排）都
通过这里的 `chat_json` 发起，以保证：

- **一处解析 provider**：优先用管理端配置的渠道（DB），否则回退到 .env 渠道；
- **一处兜底**：超时 / 429 / 5xx 重试，4xx 立即失败；JSON 解析失败自动再要一次；
- **一处记量**：每次调用写一条 `ai_usage_events`（flush 不 commit，随调用方事务提交）；
- **一处预算**：按 operation 前缀匹配日调用上限（0 = 不限），超限抛 `AIBudgetExceeded`。

设计约束（2c4g 小机器 + 渠道单点）：
- 不在模块顶层 import 任何重依赖（Pillow 在函数内 import）；
- 单次调用自带超时，绝不无限等待；
- 日志只记录用量元信息，不记录 prompt / 图片内容 / 密钥。

用法::

    res = await chat_json(
        db,
        operation="moderation.prefilter",
        system="你是内容审核助手……",
        user="请判断这张图片……",
        image_base64=b64,
        max_tokens=settings.MODERATION_PREFILTER_MAX_TOKENS,
        ref_type="photo",
        ref_id=photo.id,
    )
    tier = res.data.get("suggested_tier")
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ai_usage import AIUsageEvent
from app.services.ai_providers import resolve_db_providers, resolve_env_provider

logger = logging.getLogger(__name__)
settings = get_settings()

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


class AIError(Exception):
    """AI 调用相关错误基类。"""


class AIConfigError(AIError):
    """没有可用渠道 / 渠道配置不完整。"""


class AIBudgetExceeded(AIError):
    """当日调用预算已用完。"""


class AICallFailed(AIError):
    """调用失败（网络、HTTP 错误、响应结构异常等）。"""


class AIJSONError(AICallFailed):
    """模型有返回但无法解析出 JSON。"""


@dataclass(slots=True)
class AIJSONResult:
    """一次结构化 AI 调用的结果。"""

    data: dict[str, Any]
    text: str
    provider: str
    model_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    source: str = "env"
    raw: dict[str, Any] | None = field(default=None, repr=False)


@dataclass(slots=True)
class _Target:
    """解析后的调用目标。"""

    provider_type: str
    base_url: str
    model_id: str
    api_key: str | None
    headers: dict[str, str]
    timeout_seconds: float
    max_retries: int
    source: str


# ---------------------------------------------------------------------------
# provider 解析
# ---------------------------------------------------------------------------

async def _resolve_target(
    db: AsyncSession | None,
    *,
    model: str | None,
    image_base64: str | None,
) -> _Target:
    default_model = (
        (settings.AI_VISION_MODEL if image_base64 else settings.AI_TEXT_MODEL) or ""
    ).strip()

    db_providers = []
    if db is not None:
        try:
            db_providers = await resolve_db_providers(db)
        except Exception:  # noqa: BLE001 - 渠道表读失败不应阻断主流程
            logger.warning("resolve_db_providers failed, fallback to env provider", exc_info=True)
            db_providers = []

    if db_providers:
        provider = db_providers[0]
        return _Target(
            provider_type=provider.provider_type,
            base_url=provider.base_url,
            model_id=(model or provider.model_id or default_model),
            api_key=provider.api_key,
            headers=dict(provider.extra_headers or {}),
            timeout_seconds=float(provider.timeout_seconds or settings.AI_TIMEOUT),
            max_retries=int(provider.max_retries or settings.AI_MAX_RETRIES),
            source=provider.source or "db",
        )

    model_id = (model or default_model).strip()
    if not model_id:
        raise AIConfigError("no model configured: set AI_TEXT_MODEL / AI_VISION_MODEL")
    provider = resolve_env_provider(settings.AI_PROVIDER, model_id)
    if provider is None:
        raise AIConfigError(
            f"no usable AI provider: AI_PROVIDER={settings.AI_PROVIDER} "
            "and OPENAI_COMPATIBLE_BASE_URL / DASHSCOPE_API_KEY / OLLAMA_API_URL all unavailable"
        )
    return _Target(
        provider_type=provider.provider_type,
        base_url=provider.base_url,
        model_id=model_id,
        api_key=provider.api_key,
        headers=dict(provider.extra_headers or {}),
        timeout_seconds=float(provider.timeout_seconds or settings.AI_TIMEOUT),
        max_retries=int(provider.max_retries or settings.AI_MAX_RETRIES),
        source=provider.source or "env",
    )


# ---------------------------------------------------------------------------
# 预算
# ---------------------------------------------------------------------------

_BUDGET_ATTRS: tuple[tuple[str, str], ...] = (
    ("moderation.", "MODERATION_DAILY_CALL_BUDGET"),
    ("agent_search.", "AGENT_SEARCH_DAILY_CALL_BUDGET"),
)


def _budget_for(operation: str) -> int:
    for prefix, attr in _BUDGET_ATTRS:
        if operation.startswith(prefix):
            try:
                return int(getattr(settings, attr, 0) or 0)
            except (TypeError, ValueError):
                return 0
    return 0


async def _enforce_budget(db: AsyncSession | None, operation: str) -> None:
    budget = _budget_for(operation)
    if db is None or budget <= 0:  # 无会话 / 0 / 负数 = 不限
        return
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = (
        select(func.count())
        .select_from(AIUsageEvent)
        .where(
            AIUsageEvent.operation.like(f"{operation.split('.')[0]}.%"),
            AIUsageEvent.created_at >= start,
        )
    )
    used = int((await db.execute(stmt)).scalar() or 0)
    if used >= budget:
        raise AIBudgetExceeded(f"daily budget exhausted for {operation}: {used}/{budget}")


# ---------------------------------------------------------------------------
# 成本估算
# ---------------------------------------------------------------------------

def _estimate_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float:
    table = settings.AI_MODEL_PRICES or {}
    price: dict[str, Any] | None = table.get(model_id)
    if price is None:
        for key, value in table.items():
            if model_id.startswith(key):
                price = value
                break
    if not price:
        return 0.0
    try:
        in_price = float(price.get("input", 0) or 0) / 1_000_000
        out_price = float(price.get("output", 0) or 0) / 1_000_000
    except (TypeError, ValueError, AttributeError):
        return 0.0
    return round(prompt_tokens * in_price + completion_tokens * out_price, 6)


# ---------------------------------------------------------------------------
# 图片编码（给 VLM 用）
# ---------------------------------------------------------------------------

def encode_image_base64_sync(
    path: str | Path,
    max_edge: int = 1024,
    quality: int = 85,
) -> tuple[str, str]:
    """读取本地图片并压到长边 `max_edge`，返回 (base64, mime)。

    禁止裁切，仅等比缩小；EXIF 方向会被纠正到像素上。
    """
    from PIL import Image, ImageOps  # 延迟 import，避免基础环境未装 Pillow 时影响导入

    with Image.open(path) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((max_edge, max_edge), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii"), "image/jpeg"


async def encode_image_base64(
    path: str | Path,
    max_edge: int = 1024,
    quality: int = 85,
) -> tuple[str, str]:
    """`encode_image_base64_sync` 的异步版本（丢线程池，避免阻塞事件循环）。"""
    return await asyncio.to_thread(encode_image_base64_sync, path, max_edge, quality)


# ---------------------------------------------------------------------------
# HTTP 调用
# ---------------------------------------------------------------------------

class _RetryableError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _build_messages(
    system: str | None,
    user: str,
    image_base64: str | None,
    image_mime: str,
    provider_type: str,
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if system:
        messages.append({"role": "system", "content": system})

    if image_base64:
        if provider_type == "ollama":
            messages.append({"role": "user", "content": user, "images": [image_base64]})
        else:
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{image_mime};base64,{image_base64}"},
                        },
                    ],
                }
            )
    else:
        messages.append({"role": "user", "content": user})
    return messages


def _request_payload(target: _Target, messages: list[dict[str, Any]], max_tokens: int, temperature: float) -> tuple[str, dict[str, Any]]:
    base = target.base_url.rstrip("/")
    if target.provider_type == "ollama":
        return f"{base}/api/chat", {
            "model": target.model_id,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
    return f"{base}/chat/completions", {
        "model": target.model_id,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }


async def _post_once(
    target: _Target,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    url, payload = _request_payload(target, messages, max_tokens, temperature)
    headers: dict[str, str] = {"Content-Type": "application/json", **target.headers}
    if target.api_key:
        headers.setdefault("Authorization", f"Bearer {target.api_key}")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as client:
            response = await client.post(url, json=payload, headers=headers)
    except (httpx.TimeoutException, httpx.TransportError) as exc:
        raise _RetryableError(f"transport error: {exc.__class__.__name__}") from exc

    if response.status_code == 429 or response.status_code >= 500:
        raise _RetryableError(f"HTTP {response.status_code}")
    if response.status_code >= 400:
        body = response.text[:300].replace("\n", " ")
        raise AICallFailed(f"HTTP {response.status_code} from {target.model_id}: {body}")

    try:
        return response.json()
    except ValueError as exc:
        raise AICallFailed(f"invalid JSON envelope: {exc}") from exc


async def _request_with_retry(
    target: _Target,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    timeout_seconds: float,
) -> dict[str, Any]:
    attempts = max(1, min(target.max_retries, 3) + 1)
    last: Exception | None = None
    for idx in range(attempts):
        try:
            return await _post_once(target, messages, max_tokens, temperature, timeout_seconds)
        except _RetryableError as exc:
            last = exc
            if idx == attempts - 1:
                break
            wait = min(0.5 * (2**idx), 4.0)
            logger.info(
                "ai_call retry op_target=%s model=%s attempt=%d wait=%.1fs reason=%s",
                target.provider_type, target.model_id, idx + 1, wait, exc.message,
            )
            await asyncio.sleep(wait)
    raise AICallFailed(f"AI call failed after {attempts} attempts: {last}")


def _extract_content(response: dict[str, Any], provider_type: str) -> tuple[str, dict[str, int], str | None]:
    """从响应里取 (文本内容, usage, finish_reason)。"""
    if provider_type == "ollama":
        message = response.get("message") or {}
        content = message.get("content") or ""
        usage = {
            "prompt_tokens": int(response.get("prompt_eval_count") or 0),
            "completion_tokens": int(response.get("eval_count") or 0),
        }
        return content, usage, response.get("done_reason")

    choices = response.get("choices") or []
    if not choices:
        raise AICallFailed("response has no choices")
    choice = choices[0] or {}
    message = choice.get("message") or {}
    content = message.get("content")
    if content is None:
        content = ""
    if isinstance(content, list):  # 少数兼容层返回 content 数组
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    usage_raw = response.get("usage") or {}
    usage = {
        "prompt_tokens": int(usage_raw.get("prompt_tokens") or 0),
        "completion_tokens": int(usage_raw.get("completion_tokens") or 0),
    }
    return str(content), usage, choice.get("finish_reason")


# ---------------------------------------------------------------------------
# JSON 提取
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    stripped = text.strip()
    stripped = _JSON_FENCE_RE.sub("", stripped).strip()
    return stripped


def _find_json_object(text: str) -> str | None:
    """从任意文本中找到第一个完整的 JSON 对象（忽略字符串内的花括号）。"""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        start = text.find("{", start + 1)
    return None


def parse_json_text(text: str) -> dict[str, Any] | None:
    """把模型输出解析成 dict；失败返回 None。"""
    if not text:
        return None
    candidate = _strip_fences(text)
    for snippet in (candidate, _find_json_object(candidate)):
        if not snippet:
            continue
        try:
            parsed = json.loads(snippet)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


# ---------------------------------------------------------------------------
# 用量记录
# ---------------------------------------------------------------------------

async def _record_usage(
    db: AsyncSession | None,
    *,
    operation: str,
    target: _Target | None,
    ref_type: str | None,
    ref_id: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    latency_ms: int,
    success: bool,
    error: str | None = None,
) -> None:
    if db is None:
        return
    event = AIUsageEvent(
        operation=operation,
        provider=target.provider_type if target else None,
        model_id=target.model_id if target else None,
        source=target.source if target else None,
        ref_type=ref_type,
        ref_id=str(ref_id) if ref_id is not None else None,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        success=success,
        error=(error[:500] if error else None),
    )
    db.add(event)
    try:
        await db.flush()
    except Exception:  # noqa: BLE001 - 记量失败不影响主流程
        logger.warning("failed to persist ai_usage_event operation=%s", operation, exc_info=True)


# ---------------------------------------------------------------------------
# 对外主入口
# ---------------------------------------------------------------------------

async def chat_json(
    db: AsyncSession | None = None,
    *,
    operation: str,
    user: str,
    system: str | None = None,
    model: str | None = None,
    image_base64: str | None = None,
    image_mime: str = "image/jpeg",
    max_tokens: int = 1200,
    temperature: float = 0.1,
    timeout: float | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
    fallback_models: list[str] | None = None,
) -> AIJSONResult:
    """调用一次 AI，返回解析后的 JSON dict。

    Args:
        operation: 场景标识，如 ``moderation.prefilter`` / ``agent_search.plan``。
        user: 用户消息（提示词正文）。
        system: 系统提示词。
        model: 覆盖默认模型；为空时按是否带图自动选 ``AI_TEXT_MODEL`` / ``AI_VISION_MODEL``。
        image_base64: 带图调用时的 base64（不含 data: 前缀）。
        max_tokens: 输出上限。推理型模型（deepseek-v4.1-flash）建议 ≥2048。
        fallback_models: 主模型失败后依次尝试的模型（同一渠道）。
        ref_type / ref_id: 关联业务对象，写入用量表便于排障。

    Raises:
        AIConfigError: 没有可用渠道。
        AIBudgetExceeded: 当日预算用完。
        AICallFailed: 网络/HTTP/结构错误。
        AIJSONError: 有返回但解析不出 JSON。
    """
    started = time.perf_counter()
    await _enforce_budget(db, operation)
    target = await _resolve_target(db, model=model, image_base64=image_base64)

    models_to_try = [target.model_id]
    for candidate in fallback_models or []:
        candidate = (candidate or "").strip()
        if candidate and candidate not in models_to_try:
            models_to_try.append(candidate)

    messages = _build_messages(system, user, image_base64, image_mime, target.provider_type)
    timeout_seconds = float(timeout or target.timeout_seconds or settings.AI_TIMEOUT)

    last_error: Exception | None = None
    for model_id in models_to_try:
        attempt_target = _Target(
            provider_type=target.provider_type,
            base_url=target.base_url,
            model_id=model_id,
            api_key=target.api_key,
            headers=target.headers,
            timeout_seconds=target.timeout_seconds,
            max_retries=target.max_retries,
            source=target.source,
        )
        current_max_tokens = max_tokens
        for json_attempt in range(2):
            payload_messages = list(messages)
            if json_attempt == 1:
                payload_messages.append(
                    {
                        "role": "user",
                        "content": "你上一次的输出不是合法 JSON。现在只输出一个 JSON 对象，"
                        "不要 markdown 代码块，不要任何解释文字。",
                    }
                )
            try:
                response = await _request_with_retry(
                    attempt_target, payload_messages, current_max_tokens, temperature, timeout_seconds
                )
            except AICallFailed as exc:
                last_error = exc
                break

            text, usage, finish_reason = _extract_content(response, target.provider_type)
            parsed = parse_json_text(text)
            prompt_tokens = usage["prompt_tokens"]
            completion_tokens = usage["completion_tokens"]
            latency_ms = int((time.perf_counter() - started) * 1000)

            if parsed is not None:
                cost = _estimate_cost(model_id, prompt_tokens, completion_tokens)
                await _record_usage(
                    db,
                    operation=operation,
                    target=attempt_target,
                    ref_type=ref_type,
                    ref_id=ref_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    success=True,
                )
                logger.info(
                    "ai_call op=%s model=%s ok=1 latency=%dms tokens=%d/%d",
                    operation, model_id, latency_ms, prompt_tokens, completion_tokens,
                )
                return AIJSONResult(
                    data=parsed,
                    text=text,
                    provider=attempt_target.provider_type,
                    model_id=model_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                    source=attempt_target.source,
                    raw=response,
                )

            # 解析失败：若因输出被截断，下一轮加倍预算；记录本轮失败
            truncated = finish_reason == "length" or not text.strip()
            latency_ms = int((time.perf_counter() - started) * 1000)
            reason = "empty content (likely reasoning ate the token budget)" if truncated else "unparsable JSON"
            await _record_usage(
                db,
                operation=operation,
                target=attempt_target,
                ref_type=ref_type,
                ref_id=ref_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=_estimate_cost(model_id, prompt_tokens, completion_tokens),
                latency_ms=latency_ms,
                success=False,
                error=f"{reason}: {text[:200]}",
            )
            logger.info(
                "ai_call op=%s model=%s ok=0 reason=%s latency=%dms",
                operation, model_id, reason, latency_ms,
            )
            last_error = AIJSONError(f"{reason} from {model_id}: {text[:200]}")
            if json_attempt == 0:
                current_max_tokens = min(max(current_max_tokens * 2, current_max_tokens + 512), 8192)

    raise last_error if isinstance(last_error, AIError) else AICallFailed(str(last_error or "unknown AI error"))
