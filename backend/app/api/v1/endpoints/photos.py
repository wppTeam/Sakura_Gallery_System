"""
Photo API endpoints.
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import (
    get_current_admin_user,
    get_current_auditor_user,
    get_current_user,
    get_db,
    get_optional_current_user,
    get_optional_current_user_for_media,
    get_portrait_visibility,
)
from app.crud import permission as permission_crud
from app.crud import photo as photo_crud
from app.crud import tag as tag_crud
from app.models.ai_analysis import AIAnalysisTask
from app.models.photo import Photo
from app.models.system_config import PortraitVisibility
from app.models.user import User
from app.schemas.ai_analysis import AIAnalysisTaskCreate, AIAnalysisTaskResponse, AIApplyResponse
from app.schemas.photo import PhotoListResponse, PhotoResponse, PhotoUpdate, PhotoUploadResponse
from app.schemas.search import SearchInterpretRequest, SearchInterpretResponse
from app.schemas.taxonomy import PhotoClassificationUpdateSchema
from app.services.ai_tasks import (
    apply_ai_analysis_task,
    create_ai_analysis_task,
    get_ai_task,
    get_latest_ai_task_for_photo,
)
from app.services.image_processing import process_uploaded_image
from app.services.runtime_settings import get_runtime_settings
from app.services.search_interpreter import get_search_interpreter
from app.services.storage import cleanup_staged_files, get_storage, stage_photo_upload
from app.services import privacy
from starlette.concurrency import run_in_threadpool

from app.services.moderation_worker import enqueue_moderation
from app.services.task_dispatcher import dispatch_ai_analysis_task
from app.services.taxonomy import (
    delete_photo_classification,
    ensure_default_taxonomy,
    resolve_legacy_photo_classifications,
    serialize_classifications,
    set_photo_classifications,
)
from app.services.audit import log_audit
from app.services.notification import notify_user as send_notification

settings = get_settings()


# 进程内上传处理信号量：每 worker 同时只处理 N 张原图（见 settings.UPLOAD_PROCESS_CONCURRENCY）。
# 懒创建是为了绑定当前事件循环（TestClient/uvicorn 都会调用）。
_upload_semaphores: Dict[int, asyncio.Semaphore] = {}


def _get_upload_semaphore() -> asyncio.Semaphore:
    # 按事件循环隔离：uvicorn 只有一条循环，但测试里每个 TestClient 会建新循环，
    # 复用同一个 Semaphore 会报 "bound to a different event loop"。
    loop = asyncio.get_running_loop()
    sem = _upload_semaphores.get(id(loop))
    if sem is None:
        sem = asyncio.Semaphore(max(1, settings.UPLOAD_PROCESS_CONCURRENCY))
        _upload_semaphores[id(loop)] = sem
    return sem

# 《人工智能生成合成内容标识办法》要求：AIGC 投稿必须显式声明并展示角标；
# 图生图/换脸类还需额外确认被摄者同意，且一律进 L2 前审。
AIGC_LABEL_TEXT = "AI 生成"

# AIGC 下载副本的扩展名按探测到的真实格式决定
_MIME_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
_AIGC_FACE_SWAP_KEYWORDS = (
    "换脸", "换头", "face swap", "faceswap", "deepfake", "人脸替换",
    "明星脸", "写真生成", "证件照生成", "脱衣", "nudify",
)
logger = logging.getLogger(__name__)

router = APIRouter()


def is_reviewer(user: Optional[User]) -> bool:
    return bool(user and user.role in ("admin", "auditor"))


async def can_access_portrait_photo(
    db: AsyncSession,
    current_user: Optional[User],
    portrait_visibility: str,
) -> bool:
    if portrait_visibility == PortraitVisibility.PUBLIC:
        return True
    if not current_user:
        return False
    if portrait_visibility == PortraitVisibility.LOGIN_REQUIRED:
        return True
    return await permission_crud.check_permission(db, current_user.id, "category", "Portrait", "view")


async def can_access_photo_publicly(
    db: AsyncSession,
    photo: Photo,
    current_user: Optional[User],
    portrait_visibility: str,
) -> bool:
    if photo.status != "approved":
        return False
    if photo.category != "Portrait":
        return True
    return await can_access_portrait_photo(db, current_user, portrait_visibility)


def _photo_free_tags(tags: list) -> list[str]:
    return [tag.name for tag in tags]


_META_PART_PATTERNS = (
    re.compile(r"^作者[:：]"),
    re.compile(r"^序号[:：]"),
    re.compile(r"^排名[:：]"),
    re.compile(r"^评分[:：]"),
    re.compile(r"^第[一二三四五六七八九十0-9]+届.*摄影大赛"),
    re.compile(r"^(风光类|纪实类|建筑楼宇|校区设施|自然生态|优秀奖|一等奖|二等奖|三等奖|网络人气奖)$"),
)


def _description_parts(description: str | None) -> list[str]:
    return [part.strip() for part in (description or "").split("|") if part.strip()]


def _clean_author(value: str | None) -> str:
    return re.sub(
        r"\s*(?:（教师）|（学生）|（宣传部）|\(教师\)|\(学生\)|\(宣传部\))\s*$",
        "",
        re.sub(r"[|].*$", "", re.sub(r"^作者[:：]\s*", "", value or "")),
    ).strip()


def _split_legacy_title_author(part: str) -> tuple[str, str] | None:
    match = re.match(r"^(.+?)\s*[-－—]\s*(.+)$", part)
    if not match:
        return None
    title = match.group(1).strip()
    author = _clean_author(match.group(2))
    if not title or not author:
        return None
    return title, author


def _parse_photo_title(description: str | None) -> str:
    for part in _description_parts(description):
        if any(pattern.search(part) for pattern in _META_PART_PATTERNS):
            continue
        legacy = _split_legacy_title_author(part)
        return (legacy[0] if legacy else re.sub(r"^作品名称[:：]\s*", "", part)).strip()
    return ""


def _parse_photo_author(description: str | None) -> str:
    parts = _description_parts(description)
    for part in parts:
        if re.match(r"^作者[:：]", part):
            return _clean_author(part)
    for part in parts:
        legacy = _split_legacy_title_author(part)
        if legacy:
            return legacy[1]
    return ""


# 公开响应 EXIF 白名单：只保留拍摄参数；GPS、作者/版权、描述类个人信息一律不出
_PUBLIC_EXIF_KEYS = frozenset({
    "Make", "Model", "LensMake", "LensModel", "FNumber", "ExposureTime",
    "ISOSpeedRatings", "PhotographicSensitivity", "FocalLength",
    "FocalLengthIn35mmFilm", "DateTimeOriginal", "CreateDate", "ColorSpace",
    "WhiteBalance", "Flash", "Orientation", "Software", "ImageWidth",
    "ImageHeight", "ExposureProgram", "ExposureBiasValue", "MeteringMode",
    "SceneCaptureType", "DigitalZoomRatio", "Contrast", "Saturation",
    "Sharpness", "ExifVersion",
})


def _sanitize_public_exif(exif_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """公开 EXIF 白名单过滤：剔除 GPS、真实姓名（Artist/Copyright）、UserComment 等。"""
    if not isinstance(exif_data, dict):
        return None
    safe: Dict[str, Any] = {}
    for key, value in exif_data.items():
        if key not in _PUBLIC_EXIF_KEYS or value in (None, "", [], {}):
            continue
        if isinstance(value, (str, int, float, bool)):
            safe[str(key)] = value
        elif isinstance(value, list) and len(value) <= 16 and all(
            isinstance(item, (str, int, float, bool)) for item in value
        ):
            safe[str(key)] = value
    return safe or None


def _internal_exif(photo: Photo, key: str) -> Optional[str]:
    """读取入库时写在 exif_data 里的内部展示字段（下划线前缀，不进公开 EXIF）。"""
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else None
    if not exif:
        return None
    value = exif.get(key)
    return value if isinstance(value, str) and value else None


def _public_aigc_meta(photo: Photo) -> Optional[Dict[str, Any]]:
    """AIGC 生成信息对外子集：prompt 仅在作者勾选「公开提示词」时返回。"""
    meta = photo.aigc_meta if isinstance(photo.aigc_meta, dict) else None
    if not meta:
        return None
    safe: Dict[str, Any] = {}
    for key in ("model", "provider", "source_work_id", "face_swap", "declared_at"):
        value = meta.get(key)
        if value not in (None, "", [], {}):
            safe[key] = value
    if meta.get("prompt_public") and meta.get("prompt"):
        safe["prompt"] = meta["prompt"]
    return safe or None


_VARIANT_SIZES = (320, 640, 1080, 1600, 2400)


def _variant_meta(photo: Photo) -> Dict[str, Any]:
    """读取入库时写入 exif_data["_variants"] 的档位元信息（内部键，不进公开 EXIF）。"""
    exif = photo.exif_data if isinstance(photo.exif_data, dict) else None
    meta = exif.get("_variants") if exif else None
    return meta if isinstance(meta, dict) else {}


def _public_variants(photo: Photo) -> Optional[Dict[str, Dict[str, Any]]]:
    """响应式图各档 URL（同源相对路径，前端 <picture>/srcset 直接可用）。

    只出真实存在的档位（上传时记录在 exif_data["_variants"]），老照片没有该
    元信息则返回 None，前端退回 thumbnail/compressed 单图，行为不变。
    """
    meta = _variant_meta(photo)
    if not meta:
        return None
    out: Dict[str, Dict[str, Any]] = {}
    for size in sorted(meta, key=lambda key: int(key) if str(key).isdigit() else 0):
        info = meta[size] if isinstance(meta[size], dict) else {}
        url_base = f"/api/v1/photos/{photo.id}/image/variant/{size}"
        out[str(size)] = {
            "webp": f"{url_base}?format=webp",
            "jpeg": f"{url_base}?format=jpeg",
            "width": info.get("width"),
            "height": info.get("height"),
        }
    return out or None


def _photo_common_dict(photo: Photo, *, redact: bool = False) -> dict:
    """显式字段白名单（禁止 {**photo.__dict__}，避免泄漏内部/个人信息）。

    ``redact=True``（人像 sensitive 且访问者不是作者/审核员）时，所有媒体
    路径换成强模糊脱敏图，并去掉响应式变体（脱敏图只有一档 1600）。
    """
    use_redacted = bool(redact) and privacy.is_sensitive(photo)
    redacted_path = photo.redacted_path or photo.compressed_path
    redacted_thumb = photo.redacted_thumb_path or redacted_path
    return {
        "id": photo.id,
        "filename": photo.filename,
        "title": photo.title or _parse_photo_title(photo.description),
        "author": photo.author or _parse_photo_author(photo.description),
        "description": photo.description,
        "uploader_id": photo.uploader_id,
        "original_path": redacted_path if use_redacted else photo.original_path,
        "processed_path": redacted_path if use_redacted else photo.processed_path,
        "thumb_path": redacted_thumb if use_redacted else photo.thumb_path,
        "compressed_path": redacted_path if use_redacted else photo.compressed_path,
        "width": photo.width,
        "height": photo.height,
        "file_size": photo.file_size,
        "mime_type": photo.mime_type,
        "season": photo.season,
        "category": photo.category,
        "campus": photo.campus,
        "captured_at": photo.captured_at,
        "status": photo.status,
        "processing_status": photo.processing_status,
        "created_at": photo.created_at,
        "updated_at": photo.updated_at,
        # 首屏占位（内部存于 exif_data["_lqip"]，不随公开 EXIF 白名单泄漏）
        "lqip": _internal_exif(photo, "_lqip"),
        "lqip_color": _internal_exif(photo, "_lqip_color"),
        "blurhash": _internal_exif(photo, "_blurhash"),
        # 响应式图变体（上传时同步生成 5 档；老图为 None；脱敏展示时不出变体）
        "variants": None if use_redacted else _public_variants(photo),
        # AIGC 法定标识：显式角标所需字段（隐式 XMP 标识在 /download 写入）
        "is_aigc": bool(photo.is_aigc),
        "kind": "aigc" if photo.is_aigc else "photo",
        "aigc_label": photo.aigc_label,
        "aigc_meta": photo.aigc_meta if isinstance(photo.aigc_meta, dict) else None,
        "label_written": bool(photo.label_written),
        # 人像隐私分级：sensitive 作品对外只给脱敏图
        "privacy_level": photo.privacy_level or privacy.PRIVACY_NORMAL,
        "is_redacted": bool(use_redacted),
    }


async def serialize_photo(
    db: AsyncSession, photo: Photo, *, redact: bool = False
) -> PhotoResponse:
    """公开安全序列化：白名单字段 + EXIF 子集；不返回学号/真实姓名/GPS。"""
    tags = await photo_crud.get_photo_tags(db, photo.id)
    free_tags = _photo_free_tags(tags)
    photo_dict = _photo_common_dict(photo, redact=redact)
    photo_dict["exif_data"] = _sanitize_public_exif(photo.exif_data)
    photo_dict["tags"] = free_tags
    photo_dict["free_tags"] = free_tags
    photo_dict["classifications"] = serialize_classifications(photo)
    photo_dict["aigc_meta"] = _public_aigc_meta(photo)
    photo_dict["label_written"] = None
    photo_dict["uploader_name"] = None
    photo_dict["uploader_student_id"] = None
    return PhotoResponse(**photo_dict)


async def serialize_photos(
    db: AsyncSession,
    photos: List[Photo],
    *,
    current_user: Optional[User] = None,
) -> List[PhotoResponse]:
    """公开列表序列化：sensitive 作品对非作者/非审核员自动脱敏。"""
    out: List[PhotoResponse] = []
    for photo in photos:
        redact = privacy.should_redact_for_viewer(photo, current_user)
        out.append(await serialize_photo(db, photo, redact=redact))
    return out


async def serialize_photo_admin(db: AsyncSession, photo: Photo) -> PhotoResponse:
    """管理端 / 本人鉴权端序列化：完整 EXIF 与上传者身份，仅用于非公开端点。"""
    tags = await photo_crud.get_photo_tags(db, photo.id)
    free_tags = _photo_free_tags(tags)
    photo_dict = _photo_common_dict(photo)
    photo_dict["exif_data"] = photo.exif_data
    photo_dict["tags"] = free_tags
    photo_dict["free_tags"] = free_tags
    photo_dict["classifications"] = serialize_classifications(photo)
    uploader = getattr(photo, "uploader", None)
    photo_dict["uploader_name"] = getattr(uploader, "full_name", None)
    photo_dict["uploader_student_id"] = getattr(uploader, "student_id", None)
    return PhotoResponse(**photo_dict)


async def serialize_photos_admin(db: AsyncSession, photos: List[Photo]) -> List[PhotoResponse]:
    return [await serialize_photo_admin(db, photo) for photo in photos]


def _assert_sensitive_viewer(photo: Photo, current_user: Optional[User]) -> None:
    """sensitive 作品不向匿名访问者暴露任何媒体（含脱敏图）。"""
    if privacy.is_sensitive(photo) and current_user is None:
        raise HTTPException(status_code=404, detail="Photo not found")


async def _assert_photo_access(
    db: AsyncSession,
    photo: Photo,
    current_user: Optional[User],
    portrait_visibility: str,
) -> None:
    can_access = (
        is_reviewer(current_user)
        or (current_user and photo.uploader_id == current_user.id)
        or await can_access_photo_publicly(db, photo, current_user, portrait_visibility)
    )
    if not can_access:
        raise HTTPException(status_code=404, detail="Photo not found")


@router.get("/public", response_model=PhotoListResponse)
async def list_public_photos(
    skip: int = 0,
    limit: int = 20,
    season: Optional[str] = None,
    category: Optional[str] = None,
    campus: Optional[str] = None,
    building: Optional[str] = None,
    landmark: Optional[str] = None,
    source_type: Optional[str] = None,
    facility: Optional[str] = None,
    landscape: Optional[str] = None,
    natural_phenomenon: Optional[str] = None,
    technique: Optional[str] = None,
    animal: Optional[str] = None,
    plant: Optional[str] = None,
    gallery_series: Optional[str] = None,
    gallery_year: Optional[str] = None,
    award_level: Optional[str] = None,
    photo_type: Optional[str] = None,
    documentary_topic: Optional[str] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    smart: bool = False,
    include_sensitive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
    portrait_visibility: str = Depends(get_portrait_visibility),
):
    limit = min(limit, 100)
    if sort_by not in ["created_at", "views", "published_at"]:
        sort_by = "created_at"
    if sort_order not in ["asc", "desc"]:
        sort_order = "desc"

    should_filter_portrait = False
    if portrait_visibility == PortraitVisibility.LOGIN_REQUIRED and not current_user:
        should_filter_portrait = True
    elif portrait_visibility == PortraitVisibility.AUTHORIZED_ONLY:
        if not current_user or not await can_access_portrait_photo(db, current_user, portrait_visibility):
            should_filter_portrait = True

    # 人像隐私：sensitive 作品默认不展示，只有显式 include_sensitive=true 且
    # 当前访问者达到 portrait_visibility 要求时才纳入（并且仍然只给脱敏图）。
    show_sensitive = False
    if include_sensitive:
        if portrait_visibility == PortraitVisibility.PUBLIC:
            show_sensitive = True
        elif portrait_visibility == PortraitVisibility.LOGIN_REQUIRED:
            show_sensitive = current_user is not None
        else:  # AUTHORIZED_ONLY
            show_sensitive = bool(
                current_user
                and await can_access_portrait_photo(db, current_user, portrait_visibility)
            )

    interpretation = None
    search_interpretation_data = None

    if smart and search:
        runtime_settings = await get_runtime_settings(db)
        if runtime_settings.ai_search_enabled:
            interpreter = get_search_interpreter()
            interpretation = await interpreter.interpret(search, db)
            search_interpretation_data = {
                "facet_filters": interpretation.facet_filters,
                "keywords": interpretation.keywords,
                "original_query": interpretation.original_query,
                "method": interpretation.method,
                "confidence": interpretation.confidence,
                "explanation": interpretation.explanation,
            }
        else:
            smart = False

    photos, total = await photo_crud.get_photos(
        db,
        skip=skip,
        limit=limit,
        status="approved",
        season=season,
        category=category,
        campus=campus,
        building=building,
        landmark=landmark,
        source_type=source_type,
        facility=facility,
        landscape=landscape,
        natural_phenomenon=natural_phenomenon,
        technique=technique,
        animal=animal,
        plant=plant,
        gallery_series=gallery_series,
        gallery_year=gallery_year,
        award_level=award_level,
        photo_type=photo_type,
        documentary_topic=documentary_topic,
        search=search,
        tag=tag,
        exclude_categories=["Portrait"] if should_filter_portrait else None,
        exclude_sensitive=not show_sensitive,
        sort_by=sort_by,
        sort_order=sort_order,
        interpretation=interpretation,
    )
    return PhotoListResponse(
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        items=await serialize_photos(db, photos, current_user=current_user),
        search_interpretation=search_interpretation_data,
    )


@router.post("/interpret-search", response_model=SearchInterpretResponse)
async def interpret_search(
    payload: SearchInterpretRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
):
    interpreter = get_search_interpreter()
    result = await interpreter.interpret(payload.query, db)
    return SearchInterpretResponse(
        facet_filters=result.facet_filters,
        keywords=result.keywords,
        original_query=result.original_query,
        method=result.method,
        confidence=result.confidence,
        explanation=result.explanation,
    )


@router.get("/public/{photo_id}", response_model=PhotoResponse)
async def get_public_photo(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user),
    portrait_visibility: str = Depends(get_portrait_visibility),
):
    photo = await photo_crud.get_photo_with_tags(db, photo_id)
    if not photo or not await can_access_photo_publicly(db, photo, current_user, portrait_visibility):
        raise HTTPException(status_code=404, detail="Photo not found")
    # 人像隐私：匿名不展示 sensitive 作品；登录用户看脱敏图；作者/审核员看原图。
    if privacy.is_sensitive(photo):
        if current_user is None:
            raise HTTPException(status_code=404, detail="Photo not found")
        redact = privacy.should_redact_for_viewer(photo, current_user)
        return await serialize_photo(db, photo, redact=redact)
    return await serialize_photo(db, photo)


@router.get("/{photo_id}/image/original")
async def get_photo_image(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user_for_media),
    portrait_visibility: str = Depends(get_portrait_visibility),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    await _assert_photo_access(db, photo, current_user, portrait_visibility)
    _assert_sensitive_viewer(photo, current_user)
    if privacy.should_redact_for_viewer(photo, current_user):
        raise HTTPException(
            status_code=403,
            detail="该作品含可识别人像，原图仅作者本人与管理员可查看",
        )
    return get_storage().build_media_response(photo.original_path)


@router.get("/{photo_id}/image/thumbnail")
async def get_photo_thumbnail(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user_for_media),
    portrait_visibility: str = Depends(get_portrait_visibility),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    await _assert_photo_access(db, photo, current_user, portrait_visibility)
    _assert_sensitive_viewer(photo, current_user)
    # 人像隐私：非作者/非审核员只给脱敏缩略图（缺脱敏图则拒绝，不泄露原图）
    if privacy.should_redact_for_viewer(photo, current_user):
        redacted = photo.redacted_thumb_path or photo.redacted_path
        if not redacted:
            raise HTTPException(status_code=404, detail="该作品的脱敏图暂不可用")
        return get_storage().build_media_response(redacted)
    # Fall back to original if no thumbnail exists
    path = photo.thumb_path or photo.original_path
    return get_storage().build_media_response(path)


@router.get("/{photo_id}/image/compressed")
async def get_photo_compressed(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user_for_media),
    portrait_visibility: str = Depends(get_portrait_visibility),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    await _assert_photo_access(db, photo, current_user, portrait_visibility)
    _assert_sensitive_viewer(photo, current_user)
    if privacy.should_redact_for_viewer(photo, current_user):
        redacted = photo.redacted_path
        if not redacted:
            raise HTTPException(status_code=404, detail="该作品的脱敏图暂不可用")
        return get_storage().build_media_response(redacted)
    # Fall back to original if no compressed version exists
    path = photo.compressed_path or photo.original_path
    return get_storage().build_media_response(path)


@router.get("/{photo_id}/image/variant/{size}")
async def get_photo_variant(
    photo_id: str,
    size: str,
    fmt: str = Query("webp", alias="format", pattern="^(webp|jpeg|jpg)$"),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user_for_media),
    portrait_visibility: str = Depends(get_portrait_visibility),
):
    """响应式图：按档位返回 WebP（主用）或 JPEG（兜底）。

    档位不存在时（老图未生成变体）退回 thumbnail → compressed → 原图，
    保证前端 <picture> 永远拿得到一张图，且仍走 storage 的长缓存/预签名策略。
    """
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    await _assert_photo_access(db, photo, current_user, portrait_visibility)
    _assert_sensitive_viewer(photo, current_user)

    storage = get_storage()
    if privacy.should_redact_for_viewer(photo, current_user):
        redacted = photo.redacted_path
        if not redacted:
            raise HTTPException(status_code=404, detail="该作品的脱敏图暂不可用")
        return storage.build_media_response(redacted)
    meta = _variant_meta(photo)
    if size.isdigit() and size in meta:
        ext = "webp" if fmt == "webp" else "jpg"
        return storage.build_media_response(f"variants/{photo.id}_{size}.{ext}")

    # 老图兜底链：保证 200，不 404 打断页面渲染
    for fallback in (photo.thumb_path, photo.compressed_path, photo.original_path):
        if fallback:
            return storage.build_media_response(fallback)
    raise HTTPException(status_code=404, detail="Media file not found")


async def _aigc_download_response(db: AsyncSession, photo: Photo) -> Response:
    """AIGC 作品下载：把隐式标识（XMP）写进返回的文件字节。

    不改库内原图（原图只读），下载的每个副本都带标识；WebP/GIF 等暂不支持
    写入的格式降级为原字节 + ``X-AIGC-Implicit-Label: unsupported-format``，
    由文档标注为已知限制。
    """
    from urllib.parse import quote

    from app.services.aigc_labeling import build_xmp_packet, detect_image_mime, embed_aigc_label

    # 显式查一次公开身份，避免在 async 上下文里访问 photo.uploader lazy relationship。
    creator_row = (
        await db.execute(
            select(User.display_name, User.username).where(User.id == photo.uploader_id)
        )
    ).first()
    creator = None
    if creator_row is not None:
        creator = creator_row.display_name or creator_row.username
    packet = build_xmp_packet(photo, creator=creator).encode("utf-8")
    filename = photo.filename or f"{photo.id}"
    stem = Path(filename).stem or photo.id
    headers: Dict[str, str] = {
        "Cache-Control": "private, max-age=0, must-revalidate",
        "X-AIGC-Label": "AIGC",
        "X-AIGC-Work-Id": str(photo.id),
    }
    labeled: Optional[bytes] = None
    actual_mime = photo.mime_type
    with get_storage().local_copy(photo.original_path) as local_path:
        data = Path(local_path).read_bytes()
        actual_mime = detect_image_mime(data) or photo.mime_type
        labeled = embed_aigc_label(data, actual_mime, packet)
        if labeled is None:
            labeled = data
            headers["X-AIGC-Implicit-Label"] = "unsupported-format"
        else:
            headers["X-AIGC-Implicit-Label"] = "xmp"
            if not photo.label_written:
                photo.label_written = True
                try:
                    await db.commit()
                except Exception:  # 记账失败不影响下载本身
                    await db.rollback()
                    logger.warning("AIGC label_written 落库失败 photo=%s", photo.id)
    # 扩展名与 media_type 都按真实字节判断（上传时声明的 mime 可能是错的，
    # 例如浏览器把 PNG 报成 image/jpeg）
    suffix = _MIME_SUFFIX.get(actual_mime or "") or Path(filename).suffix or ".jpg"
    download_name = f"{stem}{suffix}"
    ascii_name = f"{photo.id}{suffix}"
    headers["Content-Disposition"] = (
        f'attachment; filename="{ascii_name}"; '
        f"filename*=UTF-8''{quote(download_name)}"
    )
    return Response(
        content=labeled,
        media_type=actual_mime or "application/octet-stream",
        headers=headers,
    )


@router.get("/{photo_id}/download")
async def download_photo(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_current_user_for_media),
    portrait_visibility: str = Depends(get_portrait_visibility),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    await _assert_photo_access(db, photo, current_user, portrait_visibility)
    _assert_sensitive_viewer(photo, current_user)
    if privacy.should_redact_for_viewer(photo, current_user):
        raise HTTPException(
            status_code=403,
            detail="该作品含可识别人像，原图下载仅作者本人与管理员可用",
        )
    if photo.is_aigc:
        return await _aigc_download_response(db, photo)
    return get_storage().build_media_response(photo.original_path, download_name=photo.filename)


@router.post("/upload", response_model=PhotoUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_photo(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="Photo file to upload"),
    title: Optional[str] = Form(None, max_length=200),
    author: Optional[str] = Form(None, max_length=100),
    description: Optional[str] = Form(None, max_length=500),
    season: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    campus: Optional[str] = Form(None),
    classifications: Optional[str] = Form(None),
    enable_ai: bool = Form(True),
    # —— AIGC 法定标识：必须显式声明（不传即拒绝）——
    aigc_declared: Optional[bool] = Form(
        None, description="是否包含 AI 生成合成内容（必填：true/false）"
    ),
    aigc_model: Optional[str] = Form(None, max_length=100),
    aigc_provider: Optional[str] = Form(None, max_length=100),
    aigc_prompt: Optional[str] = Form(None, max_length=2000),
    aigc_prompt_public: bool = Form(False),
    aigc_source_work_id: Optional[str] = Form(None, max_length=36),
    aigc_face_swap: bool = Form(False),
    consent_confirmed: bool = Form(False, description="图生图/换脸类：已获得被摄者同意"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    if season and season not in ["Spring", "Summer", "Autumn", "Winter", "春季", "夏季", "秋季", "冬季"]:
        raise HTTPException(status_code=400, detail="Season must be a known legacy or taxonomy season")
    if category and category not in [
        "Landscape", "Portrait", "Activity", "Documentary",
        "风光", "风光类", "校园风光", "建筑楼宇", "校区设施",
        "纪实", "纪实类", "活动", "人文纪实", "自然生态", "人像",
    ]:
        raise HTTPException(status_code=400, detail="Category must be a known legacy category")

    # AIGC 声明强制校验（法规四件套之一：上传时强制声明）
    if aigc_declared is None:
        raise HTTPException(
            status_code=400,
            detail="投稿必须声明是否包含 AI 生成合成内容：请传 aigc_declared=true 或 false",
        )
    aigc_meta: Optional[dict] = None
    if aigc_declared:
        prompt_text = (aigc_prompt or "").lower()
        face_swap = bool(aigc_face_swap) or any(
            keyword in prompt_text for keyword in _AIGC_FACE_SWAP_KEYWORDS
        )
        img2img = bool(aigc_source_work_id)
        # 图生图 / 换脸类额外限制：必须确认已获得被摄者同意，且强制进 L2 前审
        if (face_swap or img2img) and not consent_confirmed:
            raise HTTPException(
                status_code=400,
                detail=(
                    "图生图 / 换脸类 AIGC 内容必须确认已获得被摄者书面同意"
                    "（consent_confirmed=true），并会在人工前审后发布"
                ),
            )
        aigc_meta = {
            "model": (aigc_model or "").strip() or None,
            "provider": (aigc_provider or "").strip() or None,
            "prompt": (aigc_prompt or "").strip() or None,
            "prompt_public": bool(aigc_prompt_public),
            "source_work_id": aigc_source_work_id or None,
            "face_swap": face_swap,
            "consent_confirmed": bool(consent_confirmed),
            "declared_at": datetime.utcnow().isoformat(timespec="seconds"),
        }
    else:
        if any([aigc_model, aigc_provider, aigc_prompt, aigc_source_work_id, aigc_face_swap, consent_confirmed]):
            raise HTTPException(
                status_code=400,
                detail="声明为非 AIGC 时不能提交 AI 生成信息（model/provider/prompt 等）",
            )

    parsed_classifications: dict[str, int | list[int]] = {}
    if classifications:
        try:
            parsed = json.loads(classifications)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="classifications must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="classifications must be a JSON object")
        parsed_classifications = parsed

    staged_original_path = None
    staged_thumb_path = None
    try:
        runtime_settings = await get_runtime_settings(db)
        photo_uuid, staged_original_path, original_filename, _ = await stage_photo_upload(file)
        # Pillow 解码 + 5 档 WebP/JPEG 变体 + LQIP 是纯 CPU 密集的同步调用，
        # 直接在 async 端点里跑会堵住整个事件循环（2c4g 上 workers=2，两个并发
        # 上传就能让全站 API 卡住数秒）。丢到线程池，事件循环继续服务其它请求。
        staged_variants_dir = None
        if settings.UPLOAD_GENERATE_VARIANTS:
            staged_variants_dir = str(Path(staged_original_path).parent / "variants")
        async with _get_upload_semaphore():
            processing_result = await run_in_threadpool(
                process_uploaded_image,
                staged_original_path,
                photo_uuid,
                output_dir=str(Path(staged_original_path).parent),
                variants_dir=staged_variants_dir,
            )
        staged_thumb_path = processing_result.get("thumb_path")
        staged_compressed_path = processing_result.get("compressed_path")
        # S3 写入是网络阻塞调用（boto3），同样不能占住事件循环。
        stored_media = await run_in_threadpool(
            get_storage().persist_photo_files,
            photo_uuid,
            staged_original_path,
            staged_thumb_path,
            staged_compressed_path,
            processing_result.get("variants") or {},
        )

        # 档位元信息（宽高/是否存在）记在 exif_data["_variants"]，公开响应只出 URL。
        stored_exif = dict(processing_result.get("exif_data") or {})
        variant_meta: Dict[str, Dict[str, Any]] = {
            str(size): {"width": info.get("width"), "height": info.get("height")}
            for size, info in (stored_media.variants or {}).items()
        }
        if variant_meta:
            stored_exif["_variants"] = variant_meta

        processing_status = "pending" if enable_ai and runtime_settings.ai_enabled else "manual"
        photo = await photo_crud.create_photo(
            db,
            {
                "id": photo_uuid,
                "filename": original_filename,
                "title": title,
                "author": author,
                "original_path": stored_media.original_path,
                "thumb_path": stored_media.thumb_path,
                "compressed_path": stored_media.compressed_path,
                "width": processing_result.get("width"),
                "height": processing_result.get("height"),
                "file_size": stored_media.file_size,
                "mime_type": processing_result.get("mime_type") or file.content_type,
                "exif_data": stored_exif,
                "captured_at": processing_result.get("captured_at"),
                "description": description,
                "season": season,
                "category": category,
                "campus": campus,
                "status": "pending",
                "processing_status": processing_status,
                "is_aigc": bool(aigc_declared),
                "aigc_label": AIGC_LABEL_TEXT if aigc_declared else None,
                "aigc_meta": aigc_meta,
                "label_written": False,
            },
            str(current_user.id),
        )
        await ensure_default_taxonomy(db)
        legacy_classifications = await resolve_legacy_photo_classifications(
            db,
            season=season,
            category=category,
            campus=campus,
        )
        taxonomy_updates: dict[str, int | list[int]] = {**legacy_classifications, **parsed_classifications}
        if taxonomy_updates:
            try:
                await set_photo_classifications(db, photo, taxonomy_updates)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            await db.commit()

        if enable_ai and runtime_settings.ai_enabled:
            task = await create_ai_analysis_task(
                db,
                photo=photo,
                requested_by_id=current_user.id,
                provider=runtime_settings.ai_provider,
                model_id=runtime_settings.ai_model_id,
            )
            dispatch_ai_analysis_task(background_tasks, task.id)

        # AI 审核入队：先持久化 queued 记录（重启不丢），再尽力立即执行
        if settings.MODERATION_ENABLED:
            try:
                await enqueue_moderation(db, background_tasks, photo.id)
            except Exception:  # noqa: BLE001 - 审核属增强链路，不能回滚上传
                logger.warning("moderation enqueue failed: photo=%s", photo.id, exc_info=True)

        return PhotoUploadResponse(
            id=photo.id,
            filename=photo.filename,
            title=photo.title,
            author=photo.author,
            original_path=photo.original_path,
            thumb_path=photo.thumb_path,
            width=photo.width,
            height=photo.height,
            status=photo.status,
            is_aigc=bool(photo.is_aigc),
            aigc_label=photo.aigc_label,
            message="Photo uploaded successfully",
        )
    except HTTPException:
        cleanup_staged_files(staged_original_path, staged_thumb_path)
        raise
    except Exception as exc:  # noqa: BLE001
        cleanup_staged_files(staged_original_path, staged_thumb_path)
        raise HTTPException(status_code=500, detail=f"Failed to upload photo: {exc}") from exc
    finally:
        # Clean up temp files on success too (S3 backend copies, doesn't move)
        if staged_original_path:
            cleanup_staged_files(staged_original_path, staged_thumb_path)


@router.get("", response_model=PhotoListResponse)
async def list_photos(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    season: Optional[str] = None,
    category: Optional[str] = None,
    campus: Optional[str] = None,
    building: Optional[str] = None,
    landmark: Optional[str] = None,
    source_type: Optional[str] = None,
    facility: Optional[str] = None,
    landscape: Optional[str] = None,
    natural_phenomenon: Optional[str] = None,
    technique: Optional[str] = None,
    animal: Optional[str] = None,
    plant: Optional[str] = None,
    gallery_series: Optional[str] = None,
    gallery_year: Optional[str] = None,
    award_level: Optional[str] = None,
    photo_type: Optional[str] = None,
    documentary_topic: Optional[str] = None,
    search: Optional[str] = None,
    tag: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    limit = min(limit, 100)
    photos, total = await photo_crud.get_photos(
        db,
        skip=skip,
        limit=limit,
        status=status,
        season=season,
        category=category,
        campus=campus,
        building=building,
        landmark=landmark,
        source_type=source_type,
        facility=facility,
        landscape=landscape,
        natural_phenomenon=natural_phenomenon,
        technique=technique,
        animal=animal,
        plant=plant,
        gallery_series=gallery_series,
        gallery_year=gallery_year,
        award_level=award_level,
        photo_type=photo_type,
        documentary_topic=documentary_topic,
        search=search,
        tag=tag,
    )
    return PhotoListResponse(
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        items=await serialize_photos_admin(db, photos),
    )


@router.get("/my-submissions", response_model=PhotoListResponse)
async def list_my_submissions(
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None,
    season: Optional[str] = None,
    category: Optional[str] = None,
    campus: Optional[str] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    limit = min(limit, 100)
    photos, total = await photo_crud.get_photos(
        db,
        skip=skip,
        limit=limit,
        status=status,
        season=season,
        category=category,
        campus=campus,
        search=search,
        uploader_id=current_user.id,
    )
    return PhotoListResponse(
        total=total,
        page=skip // limit + 1 if limit > 0 else 1,
        page_size=limit,
        items=await serialize_photos_admin(db, photos),
    )


@router.get("/{photo_id}", response_model=PhotoResponse)
async def get_photo(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await photo_crud.get_photo_with_tags(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if not is_reviewer(current_user) and photo.uploader_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this photo")
    return await serialize_photo_admin(db, photo)


@router.patch("/{photo_id}", response_model=PhotoResponse)
async def update_photo(
    photo_id: str,
    photo_update: PhotoUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await photo_crud.get_photo_with_tags(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and not is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to update this photo")
    updated_photo = await photo_crud.update_photo(db, photo, photo_update)
    legacy_fields = {"season", "category", "campus"} & photo_update.model_fields_set
    if legacy_fields:
        await ensure_default_taxonomy(db)
        taxonomy_updates = await resolve_legacy_photo_classifications(
            db,
            season=updated_photo.season if "season" in legacy_fields else None,
            category=updated_photo.category if "category" in legacy_fields else None,
            campus=updated_photo.campus if "campus" in legacy_fields else None,
        )
        if "category" in legacy_fields and updated_photo.category in {"Portrait", "人像"}:
            await delete_photo_classification(db, updated_photo, "photo_type")
        if taxonomy_updates:
            await set_photo_classifications(db, updated_photo, taxonomy_updates)
        await db.commit()
    return await serialize_photo_admin(db, updated_photo)


@router.delete("/{photo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_photo(
    photo_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Not authorized to delete this photo")
    storage = get_storage()
    storage.delete_file(photo.original_path)
    storage.delete_file(photo.thumb_path)
    storage.delete_file(photo.processed_path)
    # Log BEFORE delete — photo_crud.delete_photo internally calls db.commit()
    # which also commits the flushed audit log
    await log_audit(db, user_id=current_user.id, action="photo.delete",
                    resource_type="photo", resource_id=photo_id,
                    detail=f"删除照片: {photo.filename}", request=request)
    await photo_crud.delete_photo(db, photo)
    return None


@router.post("/{photo_id}/approve", response_model=PhotoResponse)
async def approve_photo(
    photo_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    photo.status = "approved"
    photo.published_at = datetime.utcnow()
    await log_audit(db, user_id=current_user.id, action="photo.approve",
                    resource_type="photo", resource_id=photo_id, request=request)
    # 通知上传者
    if photo.uploader_id and photo.uploader_id != current_user.id:
        await send_notification(db, user_id=photo.uploader_id, type="photo_approved",
                                title="您的照片已通过审核",
                                content=f"照片 {photo.filename} 已被审核通过并发布",
                                related_id=photo_id)
    await db.commit()
    await db.refresh(photo)
    return await serialize_photo_admin(db, await photo_crud.get_photo_with_tags(db, photo_id))


@router.post("/{photo_id}/reject", response_model=PhotoResponse)
async def reject_photo(
    photo_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    photo.status = "rejected"
    photo.published_at = None
    await log_audit(db, user_id=current_user.id, action="photo.reject",
                    resource_type="photo", resource_id=photo_id, request=request)
    # 通知上传者
    if photo.uploader_id and photo.uploader_id != current_user.id:
        await send_notification(db, user_id=photo.uploader_id, type="photo_rejected",
                                title="您的照片未通过审核",
                                content=f"照片 {photo.filename} 未通过审核",
                                related_id=photo_id)
    await db.commit()
    await db.refresh(photo)
    return await serialize_photo_admin(db, await photo_crud.get_photo_with_tags(db, photo_id))


@router.post("/batch-approve")
async def batch_approve_photos(
    photo_ids: List[str],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    updated_count = 0
    for photo_id in photo_ids:
        photo = await photo_crud.get_photo(db, photo_id)
        if photo:
            photo.status = "approved"
            photo.published_at = datetime.utcnow()
            updated_count += 1
    await log_audit(db, user_id=current_user.id, action="photo.batch_approve",
                    resource_type="photo", detail=f"批量通过 {updated_count} 张照片", request=request)
    await db.commit()
    return {"message": f"Successfully approved {updated_count} photos", "updated_count": updated_count, "total_requested": len(photo_ids)}


@router.post("/batch-reject")
async def batch_reject_photos(
    photo_ids: List[str],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    updated_count = 0
    for photo_id in photo_ids:
        photo = await photo_crud.get_photo(db, photo_id)
        if photo:
            photo.status = "rejected"
            photo.published_at = None
            updated_count += 1
    await log_audit(db, user_id=current_user.id, action="photo.batch_reject",
                    resource_type="photo", detail=f"批量拒绝 {updated_count} 张照片", request=request)
    await db.commit()
    return {"message": f"Successfully rejected {updated_count} photos", "updated_count": updated_count, "total_requested": len(photo_ids)}


@router.post("/batch-delete")
async def batch_delete_photos(
    photo_ids: List[str],
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only administrators can delete photos in batch")
    storage = get_storage()
    deleted_count = 0
    for photo_id in photo_ids:
        photo = await photo_crud.get_photo(db, photo_id)
        if photo:
            storage.delete_file(photo.original_path)
            storage.delete_file(photo.thumb_path)
            storage.delete_file(photo.processed_path)
            await photo_crud.delete_photo(db, photo)
            deleted_count += 1
    await log_audit(db, user_id=current_user.id, action="photo.batch_delete",
                    resource_type="photo",
                    detail=f"批量删除 {deleted_count} 张照片",
                    request=request)
    await db.commit()
    return {"message": f"Successfully deleted {deleted_count} photos", "deleted_count": deleted_count, "total_requested": len(photo_ids)}


@router.post("/{photo_id}/tags", response_model=PhotoResponse)
async def add_photo_tags(
    photo_id: str,
    tag_names: List[str],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and not is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to update tags for this photo")
    tag_ids = []
    for tag_name in tag_names:
        tag = await tag_crud.get_or_create_tag(db, tag_name)
        tag_ids.append(tag.id)
    await photo_crud.add_tags_to_photo(db, photo_id, tag_ids)
    return await serialize_photo_admin(db, await photo_crud.get_photo_with_tags(db, photo_id))


@router.delete("/{photo_id}/tags/{tag_id}", response_model=PhotoResponse)
async def remove_photo_tag(
    photo_id: str,
    tag_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and not is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to update tags for this photo")

    from app.models.tag import PhotoTag

    await db.execute(
        PhotoTag.__table__.delete().where(
            PhotoTag.photo_id == photo_id,
            PhotoTag.tag_id == tag_id,
        )
    )
    await db.commit()
    tag = await tag_crud.get_tag(db, tag_id)
    if tag and tag.usage_count > 0:
        tag.usage_count -= 1
        await db.commit()
    return await serialize_photo_admin(db, await photo_crud.get_photo_with_tags(db, photo_id))


@router.put("/{photo_id}/classifications", response_model=PhotoResponse)
async def update_photo_classifications(
    photo_id: str,
    body: "PhotoClassificationUpdateSchema",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Batch update photo classifications. Accepts { facet_key: node_id } mapping."""
    photo = await photo_crud.get_photo_with_tags(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and not is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to update this photo")

    from app.services.taxonomy import set_photo_classifications

    try:
        await set_photo_classifications(db, photo, body.classifications)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    await db.commit()
    return await serialize_photo_admin(db, await photo_crud.get_photo_with_tags(db, photo_id))


@router.delete("/{photo_id}/classifications/{facet_key}", response_model=PhotoResponse)
async def remove_photo_classification(
    photo_id: str,
    facet_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a single classification from a photo by facet key."""
    photo = await photo_crud.get_photo_with_tags(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and not is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to update this photo")

    from app.services.taxonomy import delete_photo_classification

    await delete_photo_classification(db, photo, facet_key)
    await db.commit()
    return await serialize_photo_admin(db, await photo_crud.get_photo_with_tags(db, photo_id))


@router.post("/{photo_id}/classifications", response_model=PhotoResponse)
async def update_photo_classifications_post(
    photo_id: str,
    body: "PhotoClassificationUpdateSchema",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST alternative for updating photo classifications (workaround for proxy filtering)."""
    return await update_photo_classifications(photo_id, body, db, current_user)


@router.post("/{photo_id}/classifications/{facet_key}/remove", response_model=PhotoResponse)
async def remove_photo_classification_post(
    photo_id: str,
    facet_key: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """POST alternative for removing a photo classification (workaround for proxy filtering)."""
    return await remove_photo_classification(photo_id, facet_key, db, current_user)


@router.post("/{photo_id}/ai-analysis", response_model=AIAnalysisTaskResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_photo_ai_analysis(
    photo_id: str,
    payload: AIAnalysisTaskCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and not is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to analyze this photo")

    existing = await get_latest_ai_task_for_photo(db, photo_id)
    if existing and existing.status in {"pending", "processing"} and not payload.force:
        return AIAnalysisTaskResponse.model_validate(existing)
    if existing and existing.status in {"completed", "applied"} and not payload.force:
        return AIAnalysisTaskResponse.model_validate(existing)

    runtime_settings = await get_runtime_settings(db)
    task = await create_ai_analysis_task(
        db,
        photo=photo,
        requested_by_id=current_user.id,
        provider=runtime_settings.ai_provider,
        model_id=runtime_settings.ai_model_id,
    )
    dispatch_ai_analysis_task(background_tasks, task.id)
    return AIAnalysisTaskResponse.model_validate(task)


class BatchAIAnalysisRequest(BaseModel):
    processing_status: str = Field(default="pending", description="Filter by processing_status")
    category: Optional[str] = Field(default=None, description="Filter by category")
    created_after: Optional[datetime] = Field(default=None, description="Filter photos created after this timestamp")
    max_count: int = Field(default=50, ge=1, le=100, description="Max number of AI tasks to create")
    prompt_version: str = Field(default="v4", description="Prompt version to use (v3, v4)")
    force: bool = Field(default=False, description="Force re-analysis even if task exists (for prompt upgrade)")
    apply_auto: bool = Field(default=False, description="Auto-apply results with confidence >= 0.7")


class BatchAIAnalysisResponse(BaseModel):
    tasks_created: int
    photos_scanned: int
    photos_matched: int
    photos_skipped_no_path: int
    photos_skipped_has_task: int
    filters_applied: dict


@router.post("/batch-ai-analysis", response_model=BatchAIAnalysisResponse)
async def batch_ai_analysis(
    payload: BatchAIAnalysisRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Admin-only: trigger AI analysis for multiple photos in batch."""
    conditions = [Photo.original_path.isnot(None), Photo.original_path != ""]
    if payload.processing_status:
        conditions.append(Photo.processing_status == payload.processing_status)
    if payload.category:
        conditions.append(Photo.category == payload.category)
    if payload.created_after:
        conditions.append(Photo.created_at >= payload.created_after)

    result = await db.execute(
        select(Photo).where(and_(*conditions)).limit(payload.max_count * 3)
    )
    photos = result.scalars().all()

    photos_scanned = len(photos)
    photos_skipped_no_path = 0
    photos_skipped_has_task = 0
    tasks_created = 0

    runtime_settings = await get_runtime_settings(db)

    for photo in photos:
        if not photo.original_path:
            photos_skipped_no_path += 1
            continue

        existing = await get_latest_ai_task_for_photo(db, photo.id)
        if not payload.force and existing and existing.status in {"pending", "processing", "completed", "applied"}:
            photos_skipped_has_task += 1
            continue

        task = await create_ai_analysis_task(
            db,
            photo=photo,
            requested_by_id=current_user.id,
            provider=runtime_settings.ai_provider,
            model_id=runtime_settings.ai_model_id,
        )
        dispatch_ai_analysis_task(background_tasks, task.id)
        tasks_created += 1

        if tasks_created >= payload.max_count:
            break

    return BatchAIAnalysisResponse(
        tasks_created=tasks_created,
        photos_scanned=photos_scanned,
        photos_matched=tasks_created,
        photos_skipped_no_path=photos_skipped_no_path,
        photos_skipped_has_task=photos_skipped_has_task,
        filters_applied={
            "processing_status": payload.processing_status,
            "category": payload.category,
            "created_after": payload.created_after.isoformat() if payload.created_after else None,
        },
    )


@router.get("/{photo_id}/ai-analysis", response_model=Optional[AIAnalysisTaskResponse])
async def get_photo_ai_analysis(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    photo = await photo_crud.get_photo(db, photo_id)
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    if photo.uploader_id != current_user.id and not is_reviewer(current_user):
        raise HTTPException(status_code=403, detail="Not authorized to access this photo")
    task = await get_latest_ai_task_for_photo(db, photo_id)
    return AIAnalysisTaskResponse.model_validate(task) if task else None


@router.post("/{photo_id}/ai-analysis/{task_id}/apply", response_model=AIApplyResponse)
async def apply_photo_ai_analysis(
    photo_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    task = await get_ai_task(db, task_id)
    if task is None or task.photo_id != photo_id:
        raise HTTPException(status_code=404, detail="AI task not found")
    unresolved = await apply_ai_analysis_task(db, task, current_user.id)
    return AIApplyResponse(applied=True, task=AIAnalysisTaskResponse.model_validate(task), unresolved_classifications=unresolved)


@router.post("/{photo_id}/ai-analysis/{task_id}/ignore", response_model=AIAnalysisTaskResponse)
async def ignore_photo_ai_analysis(
    photo_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_auditor_user),
):
    task = await get_ai_task(db, task_id)
    if task is None or task.photo_id != photo_id:
        raise HTTPException(status_code=404, detail="AI task not found")
    task.status = "ignored"
    task.reviewed_by_id = current_user.id
    task.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(task)
    return AIAnalysisTaskResponse.model_validate(task)
