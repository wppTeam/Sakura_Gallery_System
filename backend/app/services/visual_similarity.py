"""视觉相似检索（无向量库，2c4g 友好）。

检索思路
--------
1. **签名**：上传时对缩略图算 dhash（16×16 = 256 bit 十六进制），写入
   ``photos.exif_data["_dhash"]``；光谱色卡在上传时写入 ``exif_data["_spectrum"]``。
2. **候选集**：已发布（approved）、非人像敏感（privacy_level=normal）的公开作品，
   当前规模 10² 量级，一次查询后在 Python 内打分即可，不需要 Milvus/pgvector。
3. **打分**（权重按可用信号归一化，老图缺 dhash 也能参与）：

   - 感知哈希汉明相似度   0.50
   - 构图比例相近         0.15
   - 光谱色卡相同         0.15
   - 自由标签 Jaccard     0.12
   - 同季节               0.05
   - 同校区               0.03

4. **理由**：给前端展示“为什么相似”（构图与光影 / 色调 / 比例 / 共同标签 / 同季 / 同校区）。

规模说明
--------
``MAX_CANDIDATES`` 限制单次参与打分的候选数；超过后应按发布时间取最近的一批。
作品量 > 2 万时再考虑把候选集换成 ANN 索引（届时才需要 pgvector/向量服务）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.photo import Photo
from app.models.tag import PhotoTag, Tag
from app.models.taxonomy import PhotoClassification
from app.services.moderation_rules import dhash_from_path, hamming_distance_hex
from app.services.privacy import PRIVACY_NORMAL
from app.services.spectrum import PALETTE_BY_KEY

# 单次参与打分的候选上限：2c4g 上 800 条的 Python 打分是微秒级，查询本身也很轻。
MAX_CANDIDATES = 800

DHASH_BITS = 256

# 归一化前的权重；target 缺某个信号时按“可用权重”重新归一化，避免老图整体分数偏低。
WEIGHT_DHASH = 0.50
WEIGHT_ASPECT = 0.15
WEIGHT_PALETTE = 0.15
WEIGHT_TAGS = 0.12
WEIGHT_SEASON = 0.05
WEIGHT_CAMPUS = 0.03

# 低于该分数视为“不相似”，不向前端返回。
MIN_SCORE = 0.34

# 汉明距离小于等于该值视为近重复（同一张图的不同上传/压缩），不推荐给自己。
NEAR_DUPLICATE_HAMMING = 3


@dataclass(frozen=True)
class SimilarityHit:
    """一条相似结果。"""

    photo: Photo
    score: float
    reasons: tuple[str, ...]


def photo_dhash(photo: Photo) -> Optional[str]:
    """读取照片的 dhash 签名（老图可能没有，返回 None）。"""
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else {}
    value = exif.get("_dhash")
    return value if isinstance(value, str) and len(value) == 64 else None


def photo_palette(photo: Photo) -> Optional[str]:
    """读取照片的光谱色卡 key（pink/gold/green/blue/ink）。"""
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else {}
    spectrum = exif.get("_spectrum")
    if isinstance(spectrum, dict):
        palette = spectrum.get("palette")
        if isinstance(palette, str) and palette in PALETTE_BY_KEY:
            return palette
    return None


def compute_dhash(path: str) -> Optional[str]:
    """对本地图片路径计算 dhash；失败返回 None（不阻塞上传/回填）。"""
    try:
        return dhash_from_path(path)
    except Exception:  # noqa: BLE001 - 签名是锦上添花
        return None


def _aspect_ratio(photo: Photo) -> Optional[float]:
    width, height = photo.width or 0, photo.height or 0
    if width <= 0 or height <= 0:
        return None
    return width / height


def _aspect_similarity(a: Photo, b: Photo) -> Optional[float]:
    """构图比例相似度：|log(r1/r2)| 归一化到 0..1（相差 2.2 倍即 0）。"""
    ratio_a, ratio_b = _aspect_ratio(a), _aspect_ratio(b)
    if not ratio_a or not ratio_b:
        return None
    distance = abs(math.log(ratio_a / ratio_b))
    return max(0.0, 1.0 - distance / math.log(2.2))


def _palette_similarity(a: Photo, b: Photo) -> Optional[float]:
    palette_a, palette_b = photo_palette(a), photo_palette(b)
    if not palette_a or not palette_b:
        return None
    return 1.0 if palette_a == palette_b else 0.0


def _tag_overlap(
    target_tags: Iterable[str],
    candidate_tags: Sequence[str],
) -> Optional[float]:
    target_set = {tag for tag in target_tags if tag}
    candidate_set = {tag for tag in candidate_tags if tag}
    if not target_set or not candidate_set:
        return None
    intersection = len(target_set & candidate_set)
    union = len(target_set | candidate_set)
    return intersection / union if union else None


def _season_match(a: Photo, b: Photo) -> Optional[float]:
    if not a.season or not b.season:
        return None
    return 1.0 if a.season == b.season else 0.0


def _campus_match(a: Photo, b: Photo) -> Optional[float]:
    if not a.campus or not b.campus:
        return None
    return 1.0 if a.campus == b.campus else 0.0


def _reasons(
    target: Photo,
    candidate: Photo,
    *,
    dhash_similarity: Optional[float],
    palette_similarity: Optional[float],
    aspect_similarity: Optional[float],
    tag_similarity: Optional[float],
    season_match: Optional[float],
    campus_match: Optional[float],
    shared_tags: Sequence[str],
) -> tuple[str, ...]:
    """生成面向用户的中文理由，最多 3 条（按信息量从强到弱）。"""
    reasons: list[str] = []
    if dhash_similarity is not None and dhash_similarity >= 0.86:
        reasons.append("构图与光影高度相似")
    if palette_similarity is not None and palette_similarity >= 1.0:
        palette = PALETTE_BY_KEY.get(photo_palette(target) or "")
        if palette is not None:
            reasons.append(f"同为{palette.name}色调")
    if shared_tags:
        reasons.append("共同标签：" + "、".join(list(shared_tags)[:2]))
    if aspect_similarity is not None and aspect_similarity >= 0.90:
        reasons.append("构图比例相近")
    if season_match is not None and season_match >= 1.0:
        reasons.append("同一季节")
    if campus_match is not None and campus_match >= 1.0:
        reasons.append("同一校区")
    return tuple(reasons[:3])


def _shared_tag_names(
    target_tags: Sequence[str], candidate_tags: Sequence[str]
) -> list[str]:
    target_set = {tag for tag in target_tags if tag}
    return [tag for tag in candidate_tags if tag in target_set]


def score_pair(
    target: Photo,
    candidate: Photo,
    target_tags: Sequence[str],
    candidate_tags: Sequence[str],
) -> tuple[float, tuple[str, ...]]:
    """对一对作品打分，返回 (score, reasons)。"""
    dhash_a, dhash_b = photo_dhash(target), photo_dhash(candidate)
    dhash_similarity: Optional[float] = None
    if dhash_a and dhash_b:
        dhash_similarity = 1.0 - min(
            hamming_distance_hex(dhash_a, dhash_b), DHASH_BITS
        ) / DHASH_BITS

    palette_similarity = _palette_similarity(target, candidate)
    aspect_similarity = _aspect_similarity(target, candidate)
    tag_similarity = _tag_overlap(target_tags, candidate_tags)
    season_match = _season_match(target, candidate)
    campus_match = _campus_match(target, candidate)

    parts: list[tuple[float, Optional[float]]] = [
        (WEIGHT_DHASH, dhash_similarity),
        (WEIGHT_ASPECT, aspect_similarity),
        (WEIGHT_PALETTE, palette_similarity),
        (WEIGHT_TAGS, tag_similarity),
        (WEIGHT_SEASON, season_match),
        (WEIGHT_CAMPUS, campus_match),
    ]
    numerator = sum(weight * value for weight, value in parts if value is not None)
    denominator = sum(weight for weight, value in parts if value is not None)
    score = numerator / denominator if denominator else 0.0

    shared_tags = _shared_tag_names(target_tags, candidate_tags)
    reasons = _reasons(
        target,
        candidate,
        dhash_similarity=dhash_similarity,
        palette_similarity=palette_similarity,
        aspect_similarity=aspect_similarity,
        tag_similarity=tag_similarity,
        season_match=season_match,
        campus_match=campus_match,
        shared_tags=shared_tags,
    )
    return round(score, 4), reasons


def rank_similar(
    target: Photo,
    candidates: Iterable[Photo],
    tags_by_photo: Mapping[str, Sequence[str]],
    target_tags: Sequence[str],
    *,
    limit: int = 8,
) -> list[SimilarityHit]:
    """对候选集排序，返回前 limit 条（过滤近重复与低分）。"""
    target_id = str(target.id)
    target_dhash = photo_dhash(target)
    hits: list[SimilarityHit] = []
    seen_dhash: set[str] = set()

    for candidate in candidates:
        if str(candidate.id) == target_id:
            continue
        candidate_tags = tags_by_photo.get(str(candidate.id), ())
        candidate_dhash = photo_dhash(candidate)
        # 近重复（同一张图重复上传/不同压缩）不推荐，避免“看起来一模一样”。
        if target_dhash and candidate_dhash:
            if hamming_distance_hex(target_dhash, candidate_dhash) <= NEAR_DUPLICATE_HAMMING:
                continue
            if candidate_dhash in seen_dhash:
                continue
        score, reasons = score_pair(target, candidate, target_tags, candidate_tags)
        if score < MIN_SCORE:
            continue
        if candidate_dhash:
            seen_dhash.add(candidate_dhash)
        hits.append(SimilarityHit(photo=candidate, score=score, reasons=reasons))

    hits.sort(key=lambda hit: (hit.score, hit.photo.published_at or hit.photo.created_at), reverse=True)
    return hits[: max(0, limit)]


async def find_similar_photos(
    db: AsyncSession,
    target: Photo,
    *,
    limit: int = 8,
) -> list[SimilarityHit]:
    """查询候选集并排序；目标作品本身需已公开（调用方负责 404 判断）。"""
    candidate_rows = (
        await db.execute(
            select(Photo)
            # 序列化要读 taxonomy 分类（serialize_classifications），预先 selectin
            # 加载，避免 async session 里触发懒加载导致 MissingGreenlet。
            .options(
                selectinload(Photo.classifications).selectinload(
                    PhotoClassification.facet
                ),
                selectinload(Photo.classifications).selectinload(
                    PhotoClassification.node
                ),
            )
            .where(
                Photo.id != target.id,
                Photo.status == "approved",
                func.coalesce(Photo.privacy_level, PRIVACY_NORMAL) == PRIVACY_NORMAL,
            )
            .order_by(Photo.published_at.desc().nullslast(), Photo.created_at.desc())
            .limit(MAX_CANDIDATES)
        )
    ).scalars().all()
    if not candidate_rows:
        return []

    candidate_ids = [str(photo.id) for photo in candidate_rows]
    tag_rows = (
        await db.execute(
            select(PhotoTag.photo_id, Tag.name)
            .join(Tag, Tag.id == PhotoTag.tag_id)
            .where(PhotoTag.photo_id.in_(candidate_ids))
        )
    ).all()
    tags_by_photo: dict[str, list[str]] = {}
    for photo_id, name in tag_rows:
        if name:
            tags_by_photo.setdefault(str(photo_id), []).append(name)

    target_tag_rows = (
        await db.execute(
            select(Tag.name)
            .join(PhotoTag, PhotoTag.tag_id == Tag.id)
            .where(PhotoTag.photo_id == str(target.id))
        )
    ).scalars().all()
    target_tags = [name for name in target_tag_rows if name]

    return rank_similar(
        target,
        candidate_rows,
        tags_by_photo,
        target_tags,
        limit=limit,
    )
