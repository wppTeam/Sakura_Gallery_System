"""
照片模型
"""
import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, String, Integer, DateTime, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


class Photo(Base):
    """照片表"""
    __tablename__ = "photos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    uploader_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    title = Column(String(200))
    author = Column(String(100))
    original_path = Column(Text)
    processed_path = Column(Text)
    thumb_path = Column(Text)
    compressed_path = Column(Text)  # Compressed version (≤5MB)
    width = Column(Integer)
    height = Column(Integer)
    file_size = Column(Integer)  # File size in bytes
    mime_type = Column(String(50))  # MIME type (e.g., image/jpeg)
    season = Column(String(20))  # Spring/Summer/Autumn/Winter
    category = Column(String(50))  # Landscape/Portrait/Activity/Documentary
    campus = Column(String(50))  # 校区信息
    description = Column(Text)  # Photo description
    exif_data = Column(JSON)  # EXIF 元数据
    status = Column(String(20), default="pending", nullable=False)  # pending/approved/rejected/deleted
    processing_status = Column(String(20), default="pending", nullable=False)  # pending/processing/completed/failed/manual
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    captured_at = Column(DateTime)  # 拍摄时间
    published_at = Column(DateTime)  # 上线时间
    views = Column(Integer, default=0)  # 浏览量

    # 人像隐私分级：normal（普通作品）| sensitive（含可识别人像，默认不公开展示）
    # sensitive 作品对外只提供脱敏图（强模糊），原图仅作者/管理员可访问；
    # 公共列表默认排除，前端需显式「显示人像作品（已脱敏）」才纳入。
    privacy_level = Column(
        String(16), nullable=False, default="normal", server_default="normal", index=True
    )
    redacted_path = Column(Text)  # 脱敏图（长边 1600，强模糊）
    redacted_thumb_path = Column(Text)  # 脱敏缩略图（长边 640）

    # 补充检索文本：AI 画面描述（_ai_caption）等「可见文案之外」的检索语料，
    # 由 app/services/search_index.py 维护；DB trigger 会把它并入 search_tokens。
    search_document = Column(Text, nullable=True)

    # AIGC 法定标识（《人工智能生成合成内容标识办法》2025-09-01 施行）
    # is_aigc: 是否 AI 生成合成内容（用户声明或审核确认）
    # aigc_label: 显式标识文案（详情页/角标展示），如「AI 生成」
    # aigc_meta: 生成信息 {model, provider, prompt, prompt_public, source_work_id,
    #            face_swap, consent_confirmed, declared_at}
    # label_written: 下载副本是否已写入隐式标识（XMP/EXIF），写入后置 True
    is_aigc = Column(Boolean, nullable=False, default=False, server_default="false")
    aigc_label = Column(String(32), nullable=True)
    aigc_meta = Column(JSON, nullable=True)
    label_written = Column(Boolean, nullable=False, default=False, server_default="false")

    # 关系
    uploader = relationship("User", back_populates="photos")
    tags = relationship("PhotoTag", back_populates="photo", cascade="all, delete-orphan")
    task_photos = relationship("TaskPhoto", back_populates="photo", cascade="all, delete-orphan")
    classifications = relationship(
        "PhotoClassification",
        back_populates="photo",
        cascade="all, delete-orphan",
    )
    ai_analysis_tasks = relationship(
        "AIAnalysisTask",
        back_populates="photo",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Photo(filename='{self.filename}', status='{self.status}')>"
