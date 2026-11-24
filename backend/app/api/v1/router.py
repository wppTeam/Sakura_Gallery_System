"""
API v1 router aggregation

API v1 版本路由聚合，注册所有端点模块。
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin_ai,
    appeals,
    aigc,
    admin_audit,
    admin_config,
    admin_permissions,
    admin_users,
    auth,
    collections,
    favorites,
    import_photos,
    notifications,
    reports,
    photos,
    profile,
    search,
    stats,
    tagging_tasks,
    tags,
    taxonomy,
)
from app.api.v1.endpoints import moderation as moderation_api

api_router = APIRouter()

# Include all endpoint routers
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(photos.router, prefix="/photos", tags=["Photos"])
api_router.include_router(tags.router, prefix="/tags", tags=["Tags"])
api_router.include_router(taxonomy.router, prefix="/taxonomy", tags=["Taxonomy"])
api_router.include_router(tagging_tasks.router, prefix="/tagging-tasks", tags=["Tagging Tasks"])
api_router.include_router(import_photos.router, prefix="/photos", tags=["Import"])
api_router.include_router(stats.router, prefix="/stats", tags=["Statistics"])
api_router.include_router(notifications.router, prefix="/user", tags=["Notifications"])
api_router.include_router(profile.router, prefix="/user", tags=["Profile"])
api_router.include_router(favorites.router, prefix="/photos", tags=["Favorites"])

# Admin endpoint routers (权限管理接口)
api_router.include_router(admin_users.router, prefix="/admin", tags=["用户管理"])
api_router.include_router(admin_config.router, prefix="/admin", tags=["系统设置"])
api_router.include_router(admin_permissions.router, prefix="/admin", tags=["授权管理"])
api_router.include_router(admin_audit.router, prefix="/admin", tags=["审计日志"])
api_router.include_router(admin_ai.router, prefix="/admin", tags=["AI 成本"])
api_router.include_router(moderation_api.router, prefix="/admin", tags=["AI 审核"])
api_router.include_router(reports.router, prefix="", tags=["举报"])
api_router.include_router(reports.admin_router, prefix="/admin", tags=["举报"])
api_router.include_router(appeals.admin_router, prefix="/admin", tags=["审核复核"])

# Collections（策展专题，公开）
api_router.include_router(collections.router, prefix="/collections", tags=["Collections"])
api_router.include_router(collections.photo_router, prefix="/photos", tags=["Collections"])

# Search endpoint (public, no auth required)
api_router.include_router(search.router, prefix="", tags=["Search"])

# 站内 AI 生图（AI 创作台）
api_router.include_router(aigc.router, prefix="/aigc", tags=["AI 创作台"])
