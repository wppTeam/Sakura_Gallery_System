"""AI 审核流水线：规则前置 → 快筛 VLM → 复核推理 → 合并建议。

三层职责：

1. **规则前置**（``moderation_rules``，不花模型钱）：GPS / 文件 / 查重命中即硬拦；
2. **快筛 VLM**（qwen3-vl-plus）：对每张非硬拦照片给出结构化风险 JSON；
3. **复核推理**（deepseek-v4.1-flash）：只处理快筛判 L2 / 低置信度 / 敏感内容样本。

本模块只负责“得出结论并存进 ``moderation_reviews``”，**不 commit**——
调用方（worker / API）负责事务边界。任何 AI 失败都降级为“至少进人工”（tier ≥ L1），
绝不把照片误放行。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.moderation import ModerationReview
from app.models.photo import Photo
from app.prompts.moderation import (
    ESCALATION_SYSTEM,
    PREFILTER_SYSTEM,
    get_escalation_prompt,
    get_prefilter_prompt,
)
from app.services import auto_tagging, moderation_rules, privacy
from app.services.curation import sync_photo_curation
from app.services.ai_client import (
    AIJSONResult,
    chat_json,
    encode_image_base64,
)
from app.services.storage import get_storage

logger = logging.getLogger(__name__)
settings = get_settings()

PREFILTER_OPERATION = "moderation.prefilter"
ESCALATION_OPERATION = "moderation.escalation"
# 所有外部调用必须有超时：快筛看单图 30s，推理模型 90s
PREFILTER_TIMEOUT_SECONDS = 30.0
ESCALATION_TIMEOUT_SECONDS = 90.0

VALID_TIERS = ("L0", "L1", "L2")
TIER_RANK = {"L0": 0, "L1": 1, "L2": 2}
VALID_DECISIONS = ("approve", "reject", "hold")
COPYRIGHT_RISKS = ("low", "medium", "high", "unknown")

# 这些 warn 命中不影响 L0 自动放行（只是提示性），其余 warn（如 aigc_metadata）要人工确认
AUTO_APPROVE_IGNORED_WARN = frozenset(
    {"image_too_small", "image_extreme_aspect", "exif_personal_fields", "exif_editor_hint"}
)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------

def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是"}
    return default


def _as_confidence(value: Any, default: float = 0.0) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, confidence))


def _as_tier(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text if text in VALID_TIERS else None


def _as_copyright_risk(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in COPYRIGHT_RISKS else "unknown"


def _as_reason(value: Any, limit: int = 500) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _prompt_rules(result: moderation_rules.RuleResult) -> dict[str, Any]:
    """喂给提示词的规则结论（精简，不带内部元数据）。"""
    return {
        "blocked": result.blocked,
        "max_severity": result.max_severity,
        "hits": [hit.to_dict() for hit in result.hits],
        "image": {
            "width": result.width,
            "height": result.height,
            "format": result.image_format,
        },
    }


def get_privacy_risk(result: moderation_rules.RuleResult) -> bool:
    """规则层是否已发现隐私/身份类风险（GPS 已在入库时剥离）。"""
    return any(hit.code in {"exif_gps_present", "exif_personal_fields"} for hit in result.hits)


class _UsageMeter:
    """累计一次审核中所有 AI 调用的用量（review 上只留最后一次模型与总量）。"""

    __slots__ = (
        "completion_tokens",
        "cost_usd",
        "latency_ms",
        "model_id",
        "prompt_tokens",
        "provider",
    )

    def __init__(self) -> None:
        self.provider: str | None = None
        self.model_id: str | None = None
        self.latency_ms = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost_usd = 0.0

    def add(self, result: AIJSONResult | None) -> None:
        if result is None:
            return
        self.provider = result.provider or self.provider
        self.model_id = result.model_id or self.model_id
        self.latency_ms += int(result.latency_ms or 0)
        self.prompt_tokens += int(result.prompt_tokens or 0)
        self.completion_tokens += int(result.completion_tokens or 0)
        self.cost_usd += float(result.cost_usd or 0.0)

    def apply(self, review: ModerationReview) -> None:
        review.provider = self.provider
        review.model_id = self.model_id
        review.latency_ms = self.latency_ms
        review.prompt_tokens = self.prompt_tokens
        review.completion_tokens = self.completion_tokens
        review.cost_usd = round(self.cost_usd, 6)


# ---------------------------------------------------------------------------
# 快筛 / 复核
# ---------------------------------------------------------------------------

def normalize_prefilter(data: dict[str, Any] | None) -> dict[str, Any]:
    """把 VLM 返回的任意 JSON 收敛成稳定结构。

    除审核判定外，同时保留打标建议（``caption`` / ``tags`` / ``facets``）——
    这三项由 ``auto_tagging`` 落库，属于同一次模型调用的附加产出。
    """
    data = data or {}
    suggested_tier = _as_tier(data.get("suggested_tier")) or "L1"
    suggestions = auto_tagging.normalize_suggestions(
        data, max_tags=int(getattr(settings, "AUTO_TAGGING_MAX_TAGS", 6) or 6)
    )
    return {
        "has_identifiable_person": _as_bool(data.get("has_identifiable_person")),
        "likely_aigc": _as_bool(data.get("likely_aigc")),
        "sensitive_content": _as_bool(data.get("sensitive_content")),
        "copyright_risk": _as_copyright_risk(data.get("copyright_risk")),
        "watermark": _as_bool(data.get("watermark")),
        "text_in_image": _as_bool(data.get("text_in_image")),
        "suggested_tier": suggested_tier,
        "confidence": _as_confidence(data.get("confidence")),
        "reason": _as_reason(data.get("reason")),
        "caption": suggestions["caption"],
        "tags": suggestions["tags"],
        "facets": suggestions["facets"],
    }


def normalize_escalation(data: dict[str, Any] | None, fallback_tier: str) -> dict[str, Any]:
    """把复核模型返回的任意 JSON 收敛成稳定结构。"""
    data = data or {}
    decision = str(data.get("decision") or "hold").strip().lower()
    if decision not in VALID_DECISIONS:
        decision = "hold"
    final_tier = _as_tier(data.get("final_tier")) or fallback_tier
    risk_points = data.get("risk_points") or []
    if isinstance(risk_points, str):
        risk_points = [risk_points]
    if not isinstance(risk_points, list):
        risk_points = []
    return {
        "final_tier": final_tier,
        "decision": decision,
        "risk_points": [_as_reason(item, 200) for item in risk_points[:8]],
        "needs_human": _as_bool(data.get("needs_human")),
        "confidence": _as_confidence(data.get("confidence")),
        "reason": _as_reason(data.get("reason")),
    }


def _merge_tier_from_prefilter(prefilter: dict[str, Any]) -> str:
    """按合规规则修正快筛级别：可识别人物 / 敏感内容 / 高版权风险至少 L2。"""
    tier = _as_tier(prefilter.get("suggested_tier")) or "L1"
    rank = TIER_RANK[tier]
    if prefilter.get("has_identifiable_person") or prefilter.get("sensitive_content"):
        rank = max(rank, TIER_RANK["L2"])
    if prefilter.get("copyright_risk") == "high":
        rank = max(rank, TIER_RANK["L2"])
    elif prefilter.get("copyright_risk") == "medium" or prefilter.get("watermark"):
        rank = max(rank, TIER_RANK["L1"])
    if prefilter.get("likely_aigc"):
        # AIGC 标识是法定要求，需人工确认投稿声明与角标，至少 L1
        rank = max(rank, TIER_RANK["L1"])
    return VALID_TIERS[rank]


def _apply_aigc_declaration_policy(photo: Photo, tier: str) -> str:
    """AIGC 法定标识兜底：声明的 AIGC 至少 L1（人工确认角标与生成信息），
    图生图 / 换脸类一律 L2 前审（即使模型误判 L0）。"""
    if not bool(getattr(photo, "is_aigc", False)):
        return tier
    rank = max(TIER_RANK[tier], TIER_RANK["L1"])
    meta = photo.aigc_meta if isinstance(photo.aigc_meta, dict) else {}
    if meta.get("face_swap") or meta.get("source_work_id"):
        rank = max(rank, TIER_RANK["L2"])
    return VALID_TIERS[rank]


def _should_escalate(prefilter: dict[str, Any], tier: str) -> bool:
    """只把难例送复核，控制成本。"""
    if tier == "L2":
        return True
    if _as_confidence(prefilter.get("confidence")) < float(
        settings.MODERATION_ESCALATION_CONFIDENCE or 0.6
    ):
        return True
    return bool(
        prefilter.get("has_identifiable_person")
        or prefilter.get("sensitive_content")
        or prefilter.get("copyright_risk") == "high"
    )


def _merge_tier_from_escalation(tier: str, escalation: dict[str, Any]) -> str:
    rank = max(TIER_RANK[tier], TIER_RANK[escalation["final_tier"]])
    if escalation["decision"] in ("reject", "hold") or escalation.get("needs_human"):
        rank = max(rank, TIER_RANK["L1"])
    return VALID_TIERS[rank]


def _has_identifiable_person(payload: dict[str, Any] | None) -> bool:
    """快筛/复核结果里是否判定「含可识别的人」。"""
    if not isinstance(payload, dict):
        return False
    value = payload.get("has_identifiable_person")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1", "是", "有")
    return False


def _can_auto_approve(
    *,
    rule_result: moderation_rules.RuleResult,
    prefilter: dict[str, Any],
    escalated: bool,
    tier: str,
) -> bool:
    """L0 免审即发：仅当规则无命中、快筛高置信度判 L0、且无需复核。"""
    if not settings.MODERATION_AUTO_APPROVE_L0:
        return False
    if escalated or tier != "L0" or rule_result.blocked:
        return False
    if prefilter.get("suggested_tier") != "L0":
        return False
    if any(
        prefilter.get(key)
        for key in (
            "has_identifiable_person",
            "likely_aigc",
            "sensitive_content",
            "watermark",
            "text_in_image",
        )
    ):
        return False
    if prefilter.get("copyright_risk") in ("medium", "high"):
        return False
    if prefilter.get("confidence", 0.0) < float(
        settings.MODERATION_AUTO_APPROVE_CONFIDENCE or 0.8
    ):
        return False
    return not any(
        hit.severity == "warn" and hit.code not in AUTO_APPROVE_IGNORED_WARN
        for hit in rule_result.hits
    )


async def _load_image_for_ai(photo: Photo) -> tuple[str | None, str]:
    """读取图片并压到长边上限，返回 (base64, mime)；失败返回 (None, "image/jpeg")。"""
    storage_path = photo.compressed_path or photo.original_path or photo.thumb_path
    if not storage_path:
        return None, "image/jpeg"
    try:
        storage = get_storage()
        with storage.local_copy(storage_path) as local_path:
            return await encode_image_base64(
                local_path,
                max_edge=int(settings.MODERATION_PREFILTER_IMAGE_MAX_EDGE or 1024),
            )
    except Exception as exc:  # noqa: BLE001 - 读图失败降级，不阻断审核
        logger.warning("moderation image encode failed for photo=%s: %s", photo.id, exc)
        return None, "image/jpeg"


async def _run_prefilter(
    db: AsyncSession,
    photo: Photo,
    rule_result: moderation_rules.RuleResult,
) -> tuple[dict[str, Any], AIJSONResult]:
    """快筛 VLM。调用失败向上抛，由 ``moderate_photo`` 统一降级。"""
    image_base64, image_mime = await _load_image_for_ai(photo)
    prompt_rules = _prompt_rules(rule_result)
    try:
        taxonomy_catalog = await auto_tagging.build_taxonomy_catalog(db)
    except Exception as exc:  # noqa: BLE001 - 分类目录失败不影响审核
        logger.warning("taxonomy catalog build failed: %s", exc)
        taxonomy_catalog = None
    user_prompt = get_prefilter_prompt(
        title=photo.title,
        description=photo.description,
        category=photo.category,
        season=photo.season,
        author=photo.author,
        rules=prompt_rules,
        taxonomy_catalog=taxonomy_catalog,
    )
    result = await chat_json(
        db,
        operation=PREFILTER_OPERATION,
        system=PREFILTER_SYSTEM,
        user=user_prompt,
        model=settings.MODERATION_PREFILTER_MODEL or None,
        image_base64=image_base64,
        image_mime=image_mime,
        max_tokens=int(settings.MODERATION_PREFILTER_MAX_TOKENS or 1024),
        temperature=float(settings.MODERATION_PREFILTER_TEMPERATURE or 0.1),
        timeout=PREFILTER_TIMEOUT_SECONDS,
        ref_type="photo",
        ref_id=photo.id,
    )
    return normalize_prefilter(result.data), result


async def _run_escalation(
    db: AsyncSession,
    photo: Photo,
    rule_result: moderation_rules.RuleResult,
    prefilter: dict[str, Any],
) -> tuple[dict[str, Any], AIJSONResult]:
    """复核推理。调用失败向上抛，由 ``moderate_photo`` 统一降级。"""
    prompt_rules = _prompt_rules(rule_result)
    user_prompt = get_escalation_prompt(
        title=photo.title,
        description=photo.description,
        category=photo.category,
        season=photo.season,
        rules=prompt_rules,
        prefilter=prefilter,
    )
    result = await chat_json(
        db,
        operation=ESCALATION_OPERATION,
        system=ESCALATION_SYSTEM,
        user=user_prompt,
        model=settings.MODERATION_ESCALATION_MODEL or None,
        max_tokens=int(settings.MODERATION_ESCALATION_MAX_TOKENS or 3072),
        temperature=float(settings.MODERATION_ESCALATION_TEMPERATURE or 0.2),
        timeout=ESCALATION_TIMEOUT_SECONDS,
        ref_type="photo",
        ref_id=photo.id,
    )
    fallback_tier = _merge_tier_from_prefilter(prefilter)
    return normalize_escalation(result.data, fallback_tier), result


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

async def moderate_photo(
    db: AsyncSession,
    photo: Photo,
    review: ModerationReview | None = None,
) -> ModerationReview:
    """对一张照片执行完整审核流水线，返回已 flush 的 ModerationReview。

    行为：
    - 规则硬拦：直接 tier=L2、status=completed，不调用任何模型；
    - 快筛 → 必要时复核 → 合并 tier；
    - L0 高置信度且无风险 → photo.status=approved（免审即发）；
    - AI 失败：status=failed 留给 worker 重试，tier 至少 L1，照片保持 pending。
    """
    if review is None:
        review = ModerationReview(photo_id=photo.id)
        # 必须显式 add：直接调用 moderate_photo 时没有外部先把 review 落库，
        # 否则 flush 不会插入这一行（DB 里查不到审核记录）。
        db.add(review)
    review.photo_id = photo.id
    review.status = "running"
    review.error = None
    usage = _UsageMeter()

    try:
        rule_result = await moderation_rules.run_rules(db, photo)
        rules_payload = rule_result.to_dict()
        if bool(getattr(photo, "is_aigc", False)):
            meta = photo.aigc_meta if isinstance(photo.aigc_meta, dict) else {}
            rules_payload["aigc_declaration"] = {
                "declared": True,
                "label": photo.aigc_label,
                "model": meta.get("model"),
                "provider": meta.get("provider"),
                "source_work_id": meta.get("source_work_id"),
                "face_swap": bool(meta.get("face_swap")),
                "consent_confirmed": bool(meta.get("consent_confirmed")),
                "prompt_public": bool(meta.get("prompt_public")),
            }
        # JSON 列要存快照副本：之后 rules_payload 还会被原地追加（打标证据），
        # 若把同一个 dict 对象挂到 ORM 上，脏检查会拿被污染的对象做比较而漏掉 UPDATE。
        review.rules = dict(rules_payload)

        # 第一层直接硬拦：不花模型钱
        if rule_result.blocked:
            review.suggested_tier = "L2"
            review.tier = "L2"
            review.status = "completed"
            review.escalation = None
            review.prefilter = None
            usage.apply(review)
            await db.flush()
            return review

        # 第二层：快筛
        prefilter, prefilter_result = await _run_prefilter(db, photo, rule_result)
        review.prefilter = prefilter
        usage.add(prefilter_result)

        # 人像隐私分级：快筛判定含可识别人像 → 标记 sensitive 并生成脱敏图，
        # 之后公共端默认不展示、只给脱敏版本（失败不阻断审核）。
        if _has_identifiable_person(prefilter):
            await privacy.mark_photo_sensitive(db, photo, reason="moderation.prefilter")
            rules_payload["privacy"] = {
                "level": photo.privacy_level,
                "redacted": privacy.has_redacted_media(photo),
                "source": "moderation.prefilter",
            }
            review.rules = dict(rules_payload)

        # 审核即打标：复用同一次快筛输出，不额外调用模型；失败不影响审核结论
        if bool(getattr(settings, "MODERATION_AUTO_TAGGING", True)):
            tagging_summary = await auto_tagging.apply_prefilter_tags(
                db,
                photo,
                prefilter,
                max_tags=int(getattr(settings, "AUTO_TAGGING_MAX_TAGS", 6) or 6),
            )
            if tagging_summary.get("applied") or tagging_summary.get("caption"):
                rules_payload["auto_tagging"] = tagging_summary
                # 注意：必须赋一个新 dict。rules 是 JSON 列，若把同一个 dict 对象再赋一次，
                # SQLAlchemy 对比不到变化（原地改键不会触发脏检查），打标证据不会落库。
                review.rules = dict(rules_payload)

        tier = _merge_tier_from_prefilter(prefilter)
        tier = _apply_aigc_declaration_policy(photo, tier)
        review.suggested_tier = tier

        # 第三层：只处理难例
        escalated = _should_escalate(prefilter, tier)
        escalation: dict[str, Any] | None = None
        if escalated:
            escalation, escalation_result = await _run_escalation(
                db, photo, rule_result, prefilter
            )
            review.escalation = escalation
            usage.add(escalation_result)
            tier = _merge_tier_from_escalation(tier, escalation)
            if _has_identifiable_person(escalation):
                await privacy.mark_photo_sensitive(db, photo, reason="moderation.escalation")
                rules_payload["privacy"] = {
                    "level": photo.privacy_level,
                    "redacted": privacy.has_redacted_media(photo),
                    "source": "moderation.escalation",
                }
                review.rules = dict(rules_payload)

        review.tier = tier
        review.status = "completed"
        usage.apply(review)

        if not bool(getattr(photo, "is_aigc", False)) and _can_auto_approve(
            rule_result=rule_result,
            prefilter=prefilter,
            escalated=escalated,
            tier=tier,
        ):
            photo.status = "approved"
            photo.published_at = photo.published_at or datetime.utcnow()
            review.final_decision = "approve"
            review.final_tier = "L0"
            review.reviewed_at = datetime.utcnow()
            # 免审即发的作品同样要进策展（否则首页「光的一日」只能靠手动跑 seed）
            await sync_photo_curation(db, photo)

        await db.flush()
        return review
    except Exception as exc:
        logger.warning("moderation failed for photo=%s", photo.id, exc_info=True)
        review.status = "failed"
        review.error = f"{exc.__class__.__name__}: {exc}"[:1000]
        # 有结论就保留；完全没结论时至少 L1，等 worker 重试或人工处理
        if not review.tier or review.tier == "L0":
            review.tier = "L1"
        if not review.suggested_tier:
            review.suggested_tier = review.tier
        usage.apply(review)
        await db.flush()
        return review


__all__ = [
    "ESCALATION_OPERATION",
    "ESCALATION_TIMEOUT_SECONDS",
    "PREFILTER_OPERATION",
    "PREFILTER_TIMEOUT_SECONDS",
    "TIER_RANK",
    "VALID_DECISIONS",
    "VALID_TIERS",
    "get_privacy_risk",
    "moderate_photo",
    "normalize_escalation",
    "normalize_prefilter",
]
