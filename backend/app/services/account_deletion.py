"""账号注销（自助删除账号与内容）。

隐私政策承诺「可随时申请注销；注销后 30 天内删除账号与内容」。此前只有管理员
停用账号，没有作者自助注销的入口，这里补齐：

- 删除账号名下的全部作品，连同原图 / 缩略图 / 压缩图 / 响应式变体 / 脱敏图、
  AI 创作台草稿图一并清理；
- 删除作者自建专辑、收藏、通知、邮箱验证码；
- 保留审计日志与举报记录（举报人 / 操作人外键 ``ON DELETE SET NULL``，
  信息脱敏保留，满足合规追溯）；
- 禁止注销最后一位管理员（否则站点失去管理入口）；
- 单事务提交，任何一步失败整体回滚。
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aigc_generation import AIGCGeneration
from app.models.appeal import PhotoAppeal
from app.models.collection import Collection, CollectionPhoto
from app.models.email_code import EmailVerificationCode
from app.models.favorite import Favorite
from app.models.notification import Notification
from app.models.photo import Photo
from app.models.user import User
from app.services.aigc_generation import generated_dir
from app.services.audit import log_audit
from app.services.photo_assets import delete_photo_assets


class LastAdminError(RuntimeError):
    """试图注销站点最后一位管理员。"""


async def _count_other_active_admins(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        select(func.count(User.id)).where(
            User.role == "admin",
            User.is_active.is_(True),
            User.id != user_id,
        )
    )
    return int(result.scalar() or 0)


def _remove_generation_files(generation: AIGCGeneration) -> int:
    """删除 AI 创作台草稿图（本地 uploads/generated/<id>.<fmt>）。"""
    removed = 0
    try:
        base = generated_dir()
    except Exception:  # noqa: BLE001 - 上传目录不可用时不影响账号注销
        return 0
    for path in base.glob(f"{generation.id}.*"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


async def delete_account(
    db: AsyncSession,
    user: User,
    *,
    storage: Any,
    request: Optional[Any] = None,
) -> dict[str, int]:
    """删除账号及其内容，返回各资源清理数量。

    调用方负责校验身份与密码、捕获 :class:`LastAdminError` 并转换为 HTTP 状态码。
    """
    if user.role == "admin" and await _count_other_active_admins(db, user.id) == 0:
        raise LastAdminError("last_admin")

    stats = {
        "photos": 0,
        "photo_files": 0,
        "collections": 0,
        "favorites": 0,
        "generations": 0,
        "generation_files": 0,
        "notifications": 0,
        "email_codes": 0,
    }

    # 1) 作品与全部派生文件
    photo_rows = (await db.execute(select(Photo).where(Photo.uploader_id == user.id))).scalars().all()
    stats["photos"] = len(photo_rows)
    for photo in photo_rows:
        stats["photo_files"] += delete_photo_assets(storage, photo)

    # 2) AI 创作台草稿（先删文件，再删行）
    generations = (
        await db.execute(select(AIGCGeneration).where(AIGCGeneration.user_id == user.id))
    ).scalars().all()
    stats["generations"] = len(generations)
    for generation in generations:
        stats["generation_files"] += _remove_generation_files(generation)
    if generations:
        await db.execute(delete(AIGCGeneration).where(AIGCGeneration.user_id == user.id))

    # 3) 作者自建专辑（editorial 专辑 owner 为空，不受影响）
    owned = (await db.execute(select(Collection.id).where(Collection.owner_id == user.id))).scalars().all()
    if owned:
        await db.execute(delete(CollectionPhoto).where(CollectionPhoto.collection_id.in_(owned)))
        await db.execute(delete(Collection).where(Collection.id.in_(owned)))
    stats["collections"] = len(owned)

    # 4) 收藏、通知、邮箱验证码
    favorite_count = await db.execute(delete(Favorite).where(Favorite.user_id == user.id))
    stats["favorites"] = int(favorite_count.rowcount or 0)
    notif_count = await db.execute(delete(Notification).where(Notification.user_id == user.id))
    stats["notifications"] = int(notif_count.rowcount or 0)
    if user.email:
        code_count = await db.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.email == user.email.lower())
        )
        stats["email_codes"] = int(code_count.rowcount or 0)

    # 5) 作品行（子表 photo_tags / classifications / favorites / moderation_reviews /
    #    appeals / collection_photos 由数据库 ON DELETE CASCADE 清理）
    if photo_rows:
        await db.execute(delete(Photo).where(Photo.uploader_id == user.id))

    # 6) 审计日志（user_id 外键 ON DELETE SET NULL，记录保留）
    await log_audit(
        db,
        user_id=user.id,
        action="user.self_delete",
        resource_type="user",
        resource_id=user.id,
        detail=(
            "作者自助注销账号："
            f"作品 {stats['photos']} 件、专辑 {stats['collections']} 个、"
            f"收藏 {stats['favorites']} 条、清理文件 {stats['photo_files'] + stats['generation_files']} 个"
        ),
        request=request,
    )

    # 7) 最后才是账号行
    await db.execute(delete(User).where(User.id == user.id))
    await db.commit()
    return stats
