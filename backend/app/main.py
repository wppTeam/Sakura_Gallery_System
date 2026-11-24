"""
FastAPI 应用主入口。

包含安全启动校验、全局异常处理、请求日志中间件等。
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from xml.sax.saxutils import escape as xml_escape

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
from app.core.config import get_settings, DEFAULT_SECRET_KEY
from sqlalchemy import or_, select

from app.core.database import AsyncSessionLocal, init_db
from app.api.v1.router import api_router
import app.models  # noqa: F401  确保所有模型被导入，create_all 才能发现它们

# ────────────────────────────────────────────────────────────
# 日志配置
# ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("visual_buct")

settings = get_settings()

# ────────────────────────────────────────────────────────────
# SECRET_KEY 启动校验（P0 安全：防止生产环境使用默认密钥）
# ────────────────────────────────────────────────────────────
if not settings.DEBUG and settings.SECRET_KEY == DEFAULT_SECRET_KEY:
    raise RuntimeError(
        "🚨 安全错误：生产环境中 SECRET_KEY 不能使用默认值！"
        "请在 .env 文件中设置一个强随机密钥，例如：\n"
        "  SECRET_KEY=$(python -c \"import secrets; print(secrets.token_urlsafe(64))\")"
    )

if settings.SECRET_KEY == DEFAULT_SECRET_KEY:
    logger.warning(
        "⚠️  SECRET_KEY 使用默认值，仅适用于本地开发。"
        "部署前请务必在 .env 中配置强随机密钥。"
    )

# 确保上传目录存在
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

openapi_tags = [
    {
        "name": "Authentication",
        "description": "登录、注册、Token 刷新与当前用户信息。`/auth/login` 使用 JSON 请求体，`/auth/token` 用于 OpenAPI/OAuth2 password flow。",
    },
    {
        "name": "Photos",
        "description": "照片上传、查询、审核、下载、标签维护与个人投稿管理。",
    },
    {
        "name": "Tags",
        "description": "标签查询与管理。",
    },
    {
        "name": "Taxonomy",
        "description": "受控分类体系（facet / node）查询与审核端维护接口。",
    },
    {
        "name": "Import",
        "description": "管理员批量导入照片与导入路径校验。",
    },
    {
        "name": "Statistics",
        "description": "浏览量统计与审核后台仪表盘数据。",
    },
    {
        "name": "用户管理",
        "description": "管理员用户列表、创建、更新、删除与角色变更。",
    },
    {
        "name": "系统设置",
        "description": "系统级配置，当前主要包括人像照片可见性策略。",
    },
    {
        "name": "授权管理",
        "description": "管理员按学号授予、查询、校验和撤销资源访问权限。",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 启动内嵌审核队列 worker。"""
    await init_db()
    logger.info("数据库表已同步")

    worker_task = None
    if settings.MODERATION_ENABLED and settings.MODERATION_WORKER_EMBEDDED:
        from app.services.moderation_worker import start_embedded_worker

        worker_task = start_embedded_worker()
        if worker_task is not None:
            logger.info(
                "审核队列 worker 已启动（poll=%.1fs, batch=%s）",
                settings.MODERATION_WORKER_POLL_SECONDS,
                settings.MODERATION_WORKER_BATCH,
            )
    try:
        yield
    finally:
        if worker_task is not None:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            logger.info("审核队列 worker 已停止")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    debug=settings.DEBUG,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
    description=(
        "视觉北化 (Visual BUCT) - 北京化工大学媒体资源管理系统后端接口。\n\n"
        "认证方式：大多数受保护接口使用 `Authorization: Bearer <token>`。\n"
        "前端常用登录接口为 `POST /api/v1/auth/login`，"
        "OpenAPI 工具链兼容登录接口为 `POST /api/v1/auth/token`。"
    ),
    openapi_tags=openapi_tags,
)


# ────────────────────────────────────────────────────────────
# 全局异常处理器（P0 安全：生产环境隐藏堆栈信息）
# ────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    捕获所有未处理的异常，防止堆栈信息泄露给客户端。
    """
    logger.error(
        "未处理的异常 [%s %s]: %s",
        request.method,
        request.url.path,
        str(exc),
        exc_info=True,
    )
    if settings.DEBUG:
        # 开发环境返回详细信息便于调试
        return JSONResponse(
            status_code=500,
            content={"detail": str(exc), "code": "INTERNAL_ERROR"},
        )
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误，请稍后重试", "code": "INTERNAL_ERROR"},
    )


# ────────────────────────────────────────────────────────────
# 请求日志中间件
# ────────────────────────────────────────────────────────────
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """记录每个请求的方法、路径、状态码和耗时。"""
    start_time = time.time()
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    # 跳过健康检查等高频端点的日志
    if request.url.path not in ("/health", "/docs", "/redoc", "/openapi.json"):
        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )

    return response


# ────────────────────────────────────────────────────────────
# CORS 配置（P0：收紧 methods 和 headers）
# ────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "X-Requested-With",
    ],
)

# ────────────────────────────────────────────────────────────
# 限流配置（P0：防止暴力破解和垃圾注册）
# ────────────────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 注册 API 路由
app.include_router(api_router, prefix="/api/v1")


def custom_openapi():
    """Customize OpenAPI schema for import tools such as ApiFox."""
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )
    schema["servers"] = [
        {"url": "http://localhost:8000", "description": "本地开发环境"},
        {"url": "/", "description": "相对路径，适合反向代理或 ApiFox 自定义环境"},
    ]
    schema["components"]["securitySchemes"]["OAuth2PasswordBearer"]["description"] = (
        "使用 `POST /api/v1/auth/token` 获取 Bearer Token，"
        "或通过 `POST /api/v1/auth/login` 获取前端登录响应。"
    )
    schema["externalDocs"] = {
        "description": "项目部署与使用说明",
        "url": "/README.md",
    }
    app.openapi_schema = schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """存活检查（进程在跑就返回 200，不触达数据库/存储）"""
    return {"status": "healthy"}


@app.get("/health/ready", include_in_schema=False)
async def readiness_check():
    """就绪检查：数据库可达 + 存储后端可用（供监控/编排系统使用）。

    - 数据库不可达 → 503（服务无法正常工作）
    - 存储探测失败只降级为 warning 状态，不影响 200（避免对象存储抖动把整站判死）
    """
    from app.services.storage import get_storage

    checks = {"database": False, "storage": "unknown"}
    healthy = False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(select(1))
        checks["database"] = True
        healthy = True
    except Exception as exc:  # pragma: no cover - 需要真实故障演练
        logger.error("readiness: 数据库不可用: %s", exc)

    try:
        storage = get_storage()
        if settings.STORAGE_BACKEND == "s3":
            await asyncio.to_thread(storage.client.head_bucket, Bucket=settings.S3_BUCKET)
        else:
            upload_dir = settings.UPLOAD_DIR
            ok = os.path.isdir(upload_dir) and os.access(upload_dir, os.W_OK)
            if not ok:
                raise RuntimeError(f"upload dir 不可写: {upload_dir}")
        checks["storage"] = "ok"
    except Exception as exc:
        logger.warning("readiness: 存储探测失败（不阻塞就绪）: %s", exc)
        checks["storage"] = "error"

    payload = {
        "status": "ready" if healthy else "not_ready",
        "checks": checks,
        "version": settings.APP_VERSION,
    }
    if not healthy:
        return JSONResponse(payload, status_code=503)
    return payload


# ────────────────────────────────────────────────────────────
# SEO：robots.txt / sitemap.xml（nginx 把这两个路径反代到这里）
# ────────────────────────────────────────────────────────────
def _site_base_url() -> str:
    """每次请求读取配置，便于测试/环境切换（默认 https://buct-sakura.cn）。"""
    return (settings.SITE_BASE_URL or "https://buct-sakura.cn").rstrip("/")


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    """允许公开页面收录，禁止后台/接口/登录页。"""
    base = _site_base_url()
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /api/\n"
        "Disallow: /login\n"
        "Disallow: /upload\n"
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=3600"})


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    """站点地图：首页 / 探索 / 专题 / 公开且非敏感的作品。"""
    from app.models.collection import Collection
    from app.models.photo import Photo

    base = _site_base_url()
    entries: list[tuple[str, str | None]] = [
        (f"{base}/", None),
        (f"{base}/explore", None),
        (f"{base}/collections", None),
    ]
    async with AsyncSessionLocal() as db:
        collections = (
            await db.execute(
                select(Collection.slug, Collection.updated_at)
                .where(Collection.status == "published", Collection.visibility == "public")
                .order_by(Collection.sort_order, Collection.created_at)
            )
        ).all()
        for slug, updated_at in collections:
            entries.append((f"{base}/collections/{slug}", _iso(updated_at)))

        photos = (
            await db.execute(
                select(Photo.id, Photo.title, Photo.published_at, Photo.updated_at, Photo.exif_data)
                .where(
                    Photo.status == "approved",
                    or_(Photo.privacy_level.is_(None), Photo.privacy_level != "sensitive"),
                )
                .order_by(Photo.published_at.desc())
                .limit(5000)
            )
        ).all()

    body = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">'
        ),
    ]
    for loc, lastmod in entries:
        body.append("  <url>")
        body.append(f"    <loc>{xml_escape(loc)}</loc>")
        if lastmod:
            body.append(f"    <lastmod>{lastmod}</lastmod>")
        body.append("  </url>")
    for photo_id, title, published_at, updated_at, exif_data in photos:
        caption = None
        if isinstance(exif_data, dict):
            raw = exif_data.get("_ai_caption")
            if isinstance(raw, str) and raw.strip():
                caption = raw.strip()[:300]
        body.append("  <url>")
        body.append(f"    <loc>{xml_escape(f'{base}/photo/{photo_id}')}</loc>")
        lastmod = _iso(updated_at or published_at)
        if lastmod:
            body.append(f"    <lastmod>{lastmod}</lastmod>")
        body.append("    <image:image>")
        # 媒体经 307 跳对象存储，Google 图片可跟随重定向；不要放预签名 URL（会过期）
        body.append(
            f"      <image:loc>{xml_escape(f'{base}/api/v1/photos/{photo_id}/image/compressed')}</image:loc>"
        )
        if title:
            body.append(f"      <image:title>{xml_escape(str(title))}</image:title>")
        if caption:
            body.append(f"      <image:caption>{xml_escape(caption)}</image:caption>")
        body.append("    </image:image>")
        body.append("  </url>")
    body.append("</urlset>")
    return Response(
        "\n".join(body),
        media_type="application/xml",
        headers={"Cache-Control": "public, max-age=3600"},
    )


def _iso(value) -> str | None:
    """datetime → sitemap 需要的 W3C 日期（无时区则按 UTC 输出）。"""
    if not value:
        return None
    try:
        return value.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    except Exception:  # noqa: BLE001 - 坏数据不影响 sitemap 其它条目
        return None



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
