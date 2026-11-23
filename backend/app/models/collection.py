"""策展专题（album / collection）模型。

产品背景：平台不只一条「最新流」。编辑可以策展年度特辑、校园四季、手机摄影等
专题；用户也能自建专辑（不需要管理员批准，见 AGENTS.md §4）。

设计取舍：
- `collections` 存专题元信息，`collection_photos` 存多对多与排序位置；
- 封面 `cover_photo_id` 可空，为空时线上取该专题第一张公开作品；
- `kind` 区分 `editorial`（编辑策展，owner 为空）与 `user`（用户自建）；
- 公开接口只暴露 `status=published` 且 `visibility=public` 的专题。
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class Collection(Base):
    """专题 / 专辑。"""

    __tablename__ = "collections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    slug = Column(String(80), unique=True, nullable=False, index=True)
    title = Column(String(120), nullable=False)
    subtitle = Column(String(200))
    description = Column(Text)
    # 封面作品（可空；为空时取专题内第一张公开作品）
    cover_photo_id = Column(String(36), ForeignKey("photos.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(20), nullable=False, default="editorial", server_default="editorial")
    owner_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    visibility = Column(String(20), nullable=False, default="public", server_default="public")
    status = Column(String(20), nullable=False, default="published", server_default="published")
    sort_order = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    cover_photo = relationship("Photo", foreign_keys=[cover_photo_id], lazy="selectin")
    entries = relationship(
        "CollectionPhoto",
        back_populates="collection",
        cascade="all, delete-orphan",
        order_by="CollectionPhoto.position",
    )

    __table_args__ = (
        Index("ix_collections_status_sort", "status", "sort_order"),
    )


class CollectionPhoto(Base):
    """专题作品（有序多对多）。"""

    __tablename__ = "collection_photos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    collection_id = Column(
        String(36), ForeignKey("collections.id", ondelete="CASCADE"), nullable=False, index=True
    )
    photo_id = Column(
        String(36), ForeignKey("photos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position = Column(Integer, nullable=False, default=0, server_default="0")
    added_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    collection = relationship("Collection", back_populates="entries")
    photo = relationship("Photo", lazy="selectin")

    __table_args__ = (
        UniqueConstraint("collection_id", "photo_id", name="uq_collection_photo"),
        Index("ix_collection_photos_collection_position", "collection_id", "position"),
    )
