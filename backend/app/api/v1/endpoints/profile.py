"""
用户个人中心和照片收藏 API 端点
"""
import io
import logging
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from PIL import Image, ImageOps
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_active_user, get_db
from app.core.security import verify_password
from app.crud import user as user_crud
from app.models.user import User
from app.schemas.user import AccountDeleteRequest, UserUpdate
from app.schemas.user import User as UserSchema
from app.services.account_deletion import LastAdminError, delete_account
from app.services.storage import get_storage

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

# 注销是不可逆操作，按 IP 限流，避免令牌泄露后被连续试探密码
_account_limiter = Limiter(key_func=get_remote_address)
_avatar_limiter = Limiter(key_func=get_remote_address)

_AVATAR_MAX_BYTES = 5 * 1024 * 1024
_AVATAR_SIZE = 512
_AVATAR_SUBDIR = "avatars"


@router.get("/profile", response_model=UserSchema)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
):
    """获取当前用户个人信息"""
    return UserSchema.model_validate(current_user)


@router.put("/profile", response_model=UserSchema)
async def update_my_profile(
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    更新当前用户个人信息

    可修改邮箱和姓名（不包含密码，密码走 PUT /auth/password）。
    """
    # 排除密码字段，密码修改走专用端点
    update_data = user_data.model_dump(exclude_unset=True, exclude={"password"})

    if "email" in update_data and update_data["email"]:
        existing = await user_crud.get_user_by_email(db, update_data["email"])
        if existing and existing.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该邮箱已被其他用户使用",
            )

    if "username" in update_data and update_data["username"]:
        existing = await user_crud.get_user_by_username(db, update_data["username"])
        if existing and existing.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="该用户名已被占用",
            )

    for key, value in update_data.items():
        setattr(current_user, key, value)

    await db.commit()
    await db.refresh(current_user)
    return UserSchema.model_validate(current_user)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
@_account_limiter.limit("10/hour")
async def delete_my_account(
    payload: AccountDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """作者自助注销账号：删除账号与全部内容（不可恢复）。

    - 需要输入密码做二次确认，且 confirm 必须为「注销」；
    - 站点最后一位管理员不能注销自己（返回 409）；
    - 作品、专辑、收藏、通知、AI 草稿等一并删除，审计日志脱敏保留。
    """
    if payload.confirm.strip() != "注销":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请输入「注销」两个字以确认",
        )
    if not current_user.hashed_password or not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="密码不正确，无法注销",
        )

    try:
        await delete_account(db, current_user, storage=get_storage(), request=request)
    except LastAdminError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="站点至少需要一位管理员。当前是最后一位管理员账号，请先新增管理员再注销。",
        )
    return None


def _avatar_relpath(user_id: str) -> str:
    return f"{_AVATAR_SUBDIR}/{user_id}.webp"


def _write_avatar(data: bytes, dest: Path) -> None:
    """居中裁方 + 缩到 512 的 WebP 头像（头像允许裁切，作品原图不允许）。"""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        width, height = img.size
        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((_AVATAR_SIZE, _AVATAR_SIZE), Image.LANCZOS)
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "WEBP", quality=88)


@router.post("/avatar", response_model=UserSchema, summary="上传公开头像")
@_avatar_limiter.limit("10/hour")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="头像文件为空")
    if len(data) > _AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="头像不能超过 5MB")
    dest = Path(settings.UPLOAD_DIR) / _avatar_relpath(current_user.id)
    try:
        await run_in_threadpool(_write_avatar, data, dest)
    except Exception as exc:
        logger.warning("avatar decode failed for %s: %s", current_user.id, exc)
        raise HTTPException(status_code=400, detail="头像不是可识别的图片（支持 JPEG / PNG / WebP）")
    current_user.avatar_path = _avatar_relpath(current_user.id)
    await db.commit()
    await db.refresh(current_user)
    return UserSchema.model_validate(current_user)


@router.delete("/avatar", response_model=UserSchema, summary="移除公开头像")
async def delete_avatar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    if current_user.avatar_path:
        path = Path(settings.UPLOAD_DIR) / current_user.avatar_path
        await run_in_threadpool(path.unlink, True)
    current_user.avatar_path = None
    await db.commit()
    await db.refresh(current_user)
    return UserSchema.model_validate(current_user)


@router.get("/avatar/{user_id}", summary="公开头像字节")
async def get_avatar(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    user = await user_crud.get_user_by_id(db, user_id)
    if user is None or not user.avatar_path:
        raise HTTPException(status_code=404, detail="头像不存在")
    path = Path(settings.UPLOAD_DIR) / user.avatar_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="头像不存在")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=3600"},
    )
