"""AI 策展助手：作者写一句话，agent 从自己的已通过作品里挑一组，生成专辑提案。

设计要点：
- **只读**：不创建专辑、不改任何作品，只返回一份可编辑的提案（前端确认后才落库）。
- **零向量依赖**：候选作品的标题 / 标签 / 季节 / 时段 / AI 描述一起拼成紧凑目录送给文本模型，
  由模型做语义筛选与排序；2c4g 上不引入 embedding 服务。
- **短编号防幻觉**：送进模型的作品用 ``P01`` 这类短编号，模型只能回编号；
  解析时按编号映射回真实 photo，未知 / 重复编号直接丢弃，避免模型编造 id。
- 结果上限 24 张、候选上限 60 张，成本约一次 2k tokens 调用（¥0.002 量级）。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.photo import Photo
from app.models.tag import PhotoTag, Tag
from app.models.taxonomy import PhotoClassification
from app.models.user import User
from app.services.ai_client import AIError, AIJSONResult, chat_json
from app.services.light_of_day import period_for_hour

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 60
MAX_PICKS = 24
MIN_PICKS = 3
MAX_PROMPT_CHARS = 200
MAX_TITLE_CHARS = 30
MAX_SUBTITLE_CHARS = 50
MAX_DESCRIPTION_CHARS = 300

_SEASON_LABELS = {
    "Spring": "春",
    "Summer": "夏",
    "Autumn": "秋",
    "Winter": "冬",
}

_SYSTEM_PROMPT = """你是「视觉百花」（北化学生创作共享站）的策展助理。作者会给你一个专辑主题，\
你要从他/她自己的已通过审核作品里挑出一组，给出标题、副标题、简介和挑选理由。

硬性要求：
1. 只能从给定候选里挑，用候选项开头的编号（如 P03）引用，禁止编造编号。
2. 6–24 张；如果主题与候选确实对不上，可以少挑（最少 3 张）甚至不挑，并在 note 里说明原因。
3. 顺序按观展节奏排：起势 → 展开 → 收束，不要简单按时间或编号。
4. 标题要有画面感、不要空泛（避免「校园风景」「我的作品」这类）；副标题一句氛围；简介 2–3 句。
5. 只输出 JSON，不要 markdown、不要解释。字段：
{
  "title": "≤20 字",
  "subtitle": "≤30 字",
  "description": "≤120 字，2–3 句",
  "picks": [{"ref": "P01", "reason": "≤30 字，说明这张为什么适合"}],
  "note": "≤40 字；无合适作品时说明原因，否则可空"
}"""


@dataclass(frozen=True)
class AssistantPick:
    photo: Photo
    reason: str | None = None


@dataclass
class AssistantProposal:
    title: str
    subtitle: str | None
    description: str | None
    picks: list[AssistantPick] = field(default_factory=list)
    note: str | None = None
    candidates: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    model_id: str | None = None


@dataclass(frozen=True)
class _Candidate:
    ref: str
    photo: Photo


def _clip(value: object, limit: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return text[:limit]


def _candidate_caption(photo: Photo) -> str:
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else {}
    caption = str(exif.get("_ai_caption") or "").strip()
    if caption:
        return caption
    return str(photo.description or "").strip()


def _catalog_line(ref: str, photo: Photo, tags: list[str]) -> str:
    parts: list[str] = []
    title = str(photo.title or "").strip()
    if title:
        parts.append(title[:40])
    when: list[str] = []
    season = _SEASON_LABELS.get(str(photo.season or "").strip())
    if season:
        when.append(season)
    if photo.captured_at is not None:
        when.append(period_for_hour(photo.captured_at.hour).label)
    if photo.campus:
        when.append(str(photo.campus))
    if when:
        parts.append("·".join(when))
    if tags:
        parts.append("标签：" + "、".join(tags[:4]))
    caption = _candidate_caption(photo)
    if caption:
        parts.append(caption[:60])
    if not parts:
        parts.append(photo.filename or "未命名")
    return f"{ref} | " + "；".join(parts)


async def _load_candidates(
    db: AsyncSession, user: User
) -> tuple[list[_Candidate], dict[str, list[str]]]:
    """取作者自己的已通过作品（不含敏感人像），并批量取自由标签。"""
    photos = (
        (
            await db.execute(
                select(Photo)
                .where(
                    Photo.uploader_id == user.id,
                    Photo.status == "approved",
                    func.coalesce(Photo.privacy_level, "normal") != "sensitive",
                )
                # 返回值要被 serialize_photo 序列化（读 taxonomy 分类），预先 selectin 加载，
                # 避免 async session 里触发懒加载导致 MissingGreenlet。
                .options(
                    selectinload(Photo.classifications).selectinload(
                        PhotoClassification.facet
                    ),
                    selectinload(Photo.classifications).selectinload(
                        PhotoClassification.node
                    ),
                )
                .order_by(
                    func.coalesce(Photo.published_at, Photo.created_at).desc(),
                    Photo.created_at.desc(),
                )
                .limit(MAX_CANDIDATES)
            )
        )
        .scalars()
        .all()
    )
    if not photos:
        return [], {}
    photo_ids = [str(photo.id) for photo in photos]
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
            tags_by_photo.setdefault(str(photo_id), []).append(str(name))
    candidates = [
        _Candidate(ref=f"P{index:02d}", photo=photo)
        for index, photo in enumerate(photos, start=1)
    ]
    return candidates, tags_by_photo


_REF_RE = re.compile(r"^[Pp]\s*0*(\d+)$")


def _parse_ref(raw: object) -> str | None:
    match = _REF_RE.match(str(raw or "").strip())
    if not match:
        return None
    index = int(match.group(1))
    if index < 1 or index > 999:
        return None
    return f"P{index:02d}"


def _normalize_picks(data: dict, by_ref: dict[str, Photo]) -> list[AssistantPick]:
    raw_picks = data.get("picks")
    if not isinstance(raw_picks, list):
        return []
    picks: list[AssistantPick] = []
    seen: set[str] = set()
    for item in raw_picks:
        if not isinstance(item, dict):
            continue
        ref = _parse_ref(item.get("ref"))
        if ref is None:
            continue
        photo = by_ref.get(ref)
        if photo is None or str(photo.id) in seen:
            continue
        reason = _clip(item.get("reason"), 40)
        picks.append(AssistantPick(photo=photo, reason=reason))
        seen.add(str(photo.id))
        if len(picks) >= MAX_PICKS:
            break
    return picks


async def propose_collection(
    db: AsyncSession,
    user: User,
    prompt: str,
) -> AssistantProposal:
    """生成一份专辑提案（只读，不落库）。

    Args:
        prompt: 作者的一句话主题，比如「雨天的校园」「黄昏的操场」。

    Raises:
        AIError: 渠道不可用 / 预算耗尽 / 模型返回无法解析。
    """
    candidate_rows, tags_by_photo = await _load_candidates(db, user)
    if not candidate_rows:
        return AssistantProposal(title="", subtitle=None, description=None, candidates=0)

    catalog = "\n".join(
        _catalog_line(row.ref, row.photo, tags_by_photo.get(str(row.photo.id), []))
        for row in candidate_rows
    )

    user_prompt = (
        f"作者想做的专辑主题：\n{prompt.strip()}\n\n"
        f"候选作品（共 {len(candidate_rows)} 张，格式：编号 | 标题 | 季节·时段·校区 | 标签 | 画面描述）：\n"
        f"{catalog}\n\n"
        "请按主题挑选，直接输出 JSON。"
    )
    result: AIJSONResult = await chat_json(
        db,
        operation="collection.assist",
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        # 推理型模型（deepseek-v4.1-flash）会先输出思维链，预算给小了可见内容会被吃光；
        # 这里给足余量，JSON 本体只有几百 token，多出来的都是推理开销。
        max_tokens=8192,
        temperature=0.4,
        ref_type="user",
        ref_id=str(user.id),
    )
    data = result.data if isinstance(result.data, dict) else {}
    by_ref = {row.ref: row.photo for row in candidate_rows}
    picks = _normalize_picks(data, by_ref)

    title = _clip(data.get("title"), MAX_TITLE_CHARS) or "未命名策展"
    subtitle = _clip(data.get("subtitle"), MAX_SUBTITLE_CHARS)
    description = _clip(data.get("description"), MAX_DESCRIPTION_CHARS)
    note = _clip(data.get("note"), 60)
    if len(picks) < MIN_PICKS and not note:
        note = f"只找到 {len(picks)} 张贴合主题的作品，可以放宽主题再试一次。"

    return AssistantProposal(
        title=title,
        subtitle=subtitle,
        description=description,
        picks=picks,
        note=note,
        candidates=len(candidate_rows),
        cost_usd=float(result.cost_usd or 0.0),
        latency_ms=int(result.latency_ms or 0),
        model_id=result.model_id,
    )


__all__ = [
    "AssistantPick",
    "AssistantProposal",
    "MAX_PROMPT_CHARS",
    "propose_collection",
]
