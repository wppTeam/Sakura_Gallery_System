"""
收藏 CRUD 操作
"""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.favorite import Favorite
from app.models.photo import Photo


async def toggle_favorite(db: AsyncSession, user_id: str, photo_id: str) -> bool:
    """
    切换收藏状态

    返回 True 表示已收藏，False 表示已取消收藏。
    """
    result = await db.execute(
        select(Favorite).filter(
            Favorite.user_id == user_id,
            Favorite.photo_id == photo_id,
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        await db.delete(existing)
        await db.flush()
        return False
    else:
        fav = Favorite(user_id=user_id, photo_id=photo_id)
        db.add(fav)
        await db.flush()
        return True


async def is_favorited(db: AsyncSession, user_id: str, photo_id: str) -> bool:
    """检查是否已收藏"""
    result = await db.execute(
        select(func.count(Favorite.id)).filter(
            Favorite.user_id == user_id,
            Favorite.photo_id == photo_id,
        )
    )
    return (result.scalar() or 0) > 0


async def get_user_favorites(
    db: AsyncSession,
    user_id: str,
    skip: int = 0,
    limit: int = 20,
) -> tuple[list[str], int]:
    """
    获取用户收藏的照片 ID 列表
    """
    # 只返回仍公开可浏览（approved）的作品：作品被下架/退回后，收藏列表里
    # 不应再出现它的信息；total 与返回列表口径保持一致，分页不会出现空洞。
    query = (
        select(Favorite.photo_id)
        .join(Photo, Photo.id == Favorite.photo_id)
        .filter(
            Favorite.user_id == user_id,
            Photo.status == "approved",
            # 人像隐私：sensitive 作品不进收藏列表（避免脱敏图扩散与原图误取）
            or_(Photo.privacy_level.is_(None), Photo.privacy_level != "sensitive"),
        )
        .order_by(Favorite.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    count_query = (
        select(func.count(Favorite.id))
        .join(Photo, Photo.id == Favorite.photo_id)
        .filter(
            Favorite.user_id == user_id,
            Photo.status == "approved",
            or_(Photo.privacy_level.is_(None), Photo.privacy_level != "sensitive"),
        )
    )

    result = await db.execute(query)
    photo_ids = [row[0] for row in result.all()]

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    return photo_ids, total


async def get_photo_favorite_count(db: AsyncSession, photo_id: str) -> int:
    """获取照片收藏数"""
    result = await db.execute(
        select(func.count(Favorite.id)).filter(Favorite.photo_id == photo_id)
    )
    return result.scalar() or 0
