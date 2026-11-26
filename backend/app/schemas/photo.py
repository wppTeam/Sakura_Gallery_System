"""
Photo Pydantic schemas
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict, field_validator

from app.schemas.taxonomy import TaxonomyValueResponse


class PhotoBase(BaseModel):
    """Base photo schema"""
    filename: str = Field(..., description="Original filename")
    title: Optional[str] = Field(None, max_length=200, description="Photo title")
    author: Optional[str] = Field(None, max_length=100, description="Photo author")
    description: Optional[str] = Field(None, max_length=500, description="Photo description")
    season: Optional[str] = Field(None, description="Season: Spring/Summer/Autumn/Winter")
    category: Optional[str] = Field(None, description="Category: Landscape/Portrait/Activity/Documentary")
    campus: Optional[str] = Field(None, description="Campus classification")


class PhotoCreate(PhotoBase):
    """Schema for creating a photo"""
    pass


class PhotoUpdate(BaseModel):
    """Schema for updating a photo"""
    title: Optional[str] = Field(None, max_length=200)
    author: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    season: Optional[str] = None
    category: Optional[str] = None
    campus: Optional[str] = None
    status: Optional[str] = None
    
    model_config = ConfigDict(extra='forbid')


class PhotoInDB(PhotoBase):
    """Photo in database"""
    id: str
    uploader_id: str
    original_path: str
    processed_path: Optional[str] = None
    thumb_path: Optional[str] = None
    compressed_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    campus: Optional[str] = None
    exif_data: Optional[Dict[str, Any]] = None
    captured_at: Optional[datetime] = None
    status: str
    processing_status: str
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class PhotoResponse(PhotoInDB):
    """Photo response schema"""
    uploader_name: Optional[str] = None
    uploader_student_id: Optional[str] = None
    # 公开用户名（创作者主页 /u/{username} 的跳转目标；学号与真实姓名永不公开）
    uploader_username: Optional[str] = None
    # AIGC 法定标识（显式角标 + 详情说明；下载副本另写隐式 XMP）
    is_aigc: bool = False
    kind: Optional[str] = Field(None, description="photo | aigc（由 is_aigc 派生，前端角标用）")
    aigc_label: Optional[str] = None
    aigc_meta: Optional[Dict[str, Any]] = None
    label_written: Optional[bool] = None
    # 展示用占位图：20px WebP data-URI（首屏消除加载跳动），blurhash 预留
    lqip: Optional[str] = None
    lqip_color: Optional[str] = None
    blurhash: Optional[str] = None
    # 响应式图变体：{ "320": {"webp": url, "jpeg": url, "width": 320, "height": 213}, ... }
    variants: Optional[Dict[str, Dict[str, Any]]] = None
    # 人像隐私分级：normal | sensitive；sensitive 对外只给脱敏图（is_redacted=True）
    privacy_level: Optional[str] = None
    is_redacted: Optional[bool] = None
    # 对象存储模式下的绝对预签名直链（None 表示前端回退同源 /api/... 媒体端点）。
    # 目的：省掉「同源 API → 307 → 对象存储」每张图一次的隧道往返。
    thumb_url: Optional[str] = None
    compressed_url: Optional[str] = None
    # AI 画面描述（快筛生成，用于详情页「画面笔记」与检索；人像脱敏视角不返回）
    ai_caption: Optional[str] = Field(
        None,
        max_length=300,
        description="AI 生成的画面描述（公开文案，供检索/无障碍参考）",
    )
    tags: List[str] = Field(default_factory=list, description="Associated tags")
    free_tags: List[str] = Field(default_factory=list, description="User-visible free tags")
    classifications: Dict[str, TaxonomyValueResponse] | Dict[str, Dict[str, Any] | list[Dict[str, Any]]] = Field(
        default_factory=dict,
        description="Controlled taxonomy classifications",
    )
    
    model_config = ConfigDict(from_attributes=True)

    @field_validator('original_path', 'thumb_path', 'processed_path', 'compressed_path', mode='before')
    @classmethod
    def normalize_path(cls, v: Optional[str]) -> Optional[str]:
        if v and isinstance(v, str):
            # Replace backslashes with forward slashes
            v = v.replace('\\', '/')
            # Remove leading ./ if present (e.g. ./uploads/...)
            if v.startswith('./'):
                v = v[2:]
            return v


class PhotoListResponse(BaseModel):
    """Photo list response with pagination"""
    total: int
    page: int
    page_size: int
    items: List[PhotoResponse]
    search_interpretation: Optional[Dict[str, Any]] = Field(None, description="Smart search interpretation result")


class PhotoUploadResponse(BaseModel):
    """Response after uploading a photo"""
    id: str
    filename: str
    title: Optional[str] = None
    author: Optional[str] = None
    original_path: str
    thumb_path: Optional[str] = None
    compressed_path: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    status: str
    is_aigc: bool = False
    aigc_label: Optional[str] = None
    message: str = "Photo uploaded successfully"
    
    model_config = ConfigDict(from_attributes=True)


class SimilarPhotoItem(PhotoResponse):
    """视觉相似结果：公开安全序列化 + 相似度与理由。"""

    similarity: float = Field(..., ge=0, le=1, description="相似度 0..1")
    reasons: List[str] = Field(default_factory=list, description="面向用户的相似理由")


class SimilarPhotosResponse(BaseModel):
    """视觉相似作品列表。"""

    items: List[SimilarPhotoItem]
    total: int


class PhotoNeighborItem(BaseModel):
    """导航窗口里的紧凑作品项（胶片条用，避免完整 EXIF/变体的开销）。"""

    id: str
    title: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    aspect_ratio: Optional[float] = Field(None, description="宽/高，前端占位用")
    is_aigc: bool = False
    aigc_label: Optional[str] = None
    lqip_color: Optional[str] = None
    thumb_url: str


class MySubmissionStats(BaseModel):
    """「我的投稿」概览计数（作者工作台用，不含已删除作品）。"""

    total: int = Field(0, ge=0)
    pending: int = Field(0, ge=0)
    approved: int = Field(0, ge=0)
    rejected: int = Field(0, ge=0)
    pending_appeal: int = Field(0, ge=0, description="被驳回且已提交复核、正在等待受理的数量")


class PhotoNavContext(BaseModel):
    """当前作品所处的浏览上下文。"""

    kind: str = Field(..., description="latest | collection")
    slug: Optional[str] = None
    title: Optional[str] = None
    position: int = Field(..., ge=1, description="当前作品在序列中的位置（1 起）")
    total: int = Field(..., ge=0)


class PhotoNeighborsResponse(BaseModel):
    """详情页「上一张 / 下一张」导航。"""

    context: PhotoNavContext
    items: List[PhotoNeighborItem]
    index: int = Field(..., ge=0, description="当前作品在 items 中的下标")
    prev: Optional[str] = None
    next: Optional[str] = None
