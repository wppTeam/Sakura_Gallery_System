"""
用户个人中心和照片收藏 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.deps import get_db, get_current_active_user
from app.core.security import verify_password
from app.services.account_deletion import LastAdminError, delete_account
from app.services.audit import log_audit
from app.services.storage import get_storage
from app.crud import user as user_crud
from app.models.user import User
from app.schemas.user import AccountDeleteRequest, User as UserSchema, UserUpdate

router = APIRouter()

# 注销是不可逆操作，按 IP 限流，避免令牌泄露后被连续试探密码
_account_limiter = Limiter(key_func=get_remote_address)


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

    for key, value in update_data.items():
        setattr(current_user, key, value)

    await db.commit()
    await db.refresh(current_user)
    return UserSchema.model_validate(current_user)


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
@_account_limiter.limit("3/hour")
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
