"""
应用配置管理模块
"""
from typing import Literal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# 默认密钥常量，仅用于启动时判断用户是否已自定义配置
DEFAULT_SECRET_KEY = "your-secret-key-here-change-in-production"


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用基础配置
    APP_NAME: str = "视觉北化"
    APP_NAME_EN: str = "Visual BUCT"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    
    # 数据库配置
    DATABASE_URL: str = "sqlite+aiosqlite:///./visual_buct.db"
    # 对外站点地址（sitemap/robots/canonical 用；不含结尾斜杠）
    SITE_BASE_URL: str = "https://buct-sakura.cn"
    # 连接池按「小机器」可调：2c4g + uvicorn --workers 2 时，每个 worker 都有
    # 自己的池，pool_size*workers 才是真实连接数（PG 默认 max_connections=100）。
    DB_POOL_SIZE: int = 10
    DB_POOL_MAX_OVERFLOW: int = 20
    DB_POOL_RECYCLE: int = 1800
    REDIS_URL: str = "redis://localhost:6379/0"
    TASK_QUEUE_BACKEND: Literal["background", "celery"] = "background"
    
    # 文件存储配置
    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    UPLOAD_DIR: str = "./uploads"
    # 上传时同步生成 320/640/1080/1600/2400 响应式变体（WebP+JPEG）。
    # 2c4g 上每上传一次会多 10 次编码，但换来首屏按屏宽取图的带宽节省；
    # 若机器更小或吞吐优先，可置 false 退化为 thumbnail+compressed 两档。
    UPLOAD_GENERATE_VARIANTS: bool = True
    # 每个进程同时处理的上传数量上限（进程内信号量，默认 1）。
    # 24MP 原图单次处理峰值 RSS 约 +190MB，2c4g 上并发大图会把容器顶到 OOM；
    # 2 个 uvicorn worker × 1 = 最多 2 张图同时处理，其余在事件循环里排队。
    # 小图为主的站点可调到 2；内存 ≥ 8G 可调到 4。
    UPLOAD_PROCESS_CONCURRENCY: int = 1
    MAX_UPLOAD_SIZE: int = 20971520  # 20MB
    S3_ENDPOINT: str | None = None
    S3_BUCKET: str | None = None
    S3_ACCESS_KEY: str | None = None
    S3_SECRET_KEY: str | None = None
    S3_REGION: str | None = None
    S3_USE_SSL: bool = False
    # boto3 的寻址风格：auto（默认，非 AWS endpoint 用 path-style）/ virtual（bucket.host）
    # 腾讯 COS / 阿里 OSS 等云厂商的预签名 URL 需要 virtual-style；MinIO 本机用 auto。
    S3_ADDRESSING_STYLE: str = "auto"
    S3_PRESIGN_EXPIRE_SECONDS: int = 600
    
    # 安全配置
    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15  # Access Token 短时效
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7     # Refresh Token 长时效
    
    # AI 服务配置
    AI_PROVIDER: Literal["ollama", "dashscope", "openai_compatible"] = "ollama"
    OLLAMA_API_URL: str = "http://localhost:11434"
    AI_MODEL_NAME: str = "llava"
    AI_MODEL_ID: str = "llava"
    AI_ENABLED: bool = True
    AI_TIMEOUT: int = 60
    AI_MAX_RETRIES: int = 2
    AI_DAILY_BUDGET: int = 500
    DASHSCOPE_API_KEY: str | None = None
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    OPENAI_COMPATIBLE_API_KEY: str | None = None
    OPENAI_COMPATIBLE_BASE_URL: str | None = None
    OPENAI_COMPATIBLE_MODEL_ID: str | None = None
    OPENAI_COMPATIBLE_HEADERS: dict[str, str] = Field(default_factory=dict)

    # AI 搜索专用配置（可选，未设置时回退到默认AI配置）
    AI_SEARCH_ENABLED: bool = True
    AI_SEARCH_PROVIDER: str | None = None
    AI_SEARCH_MODEL_ID: str | None = None
    AI_SEARCH_TIMEOUT: int = 15

    # ---- AI 场景默认模型（审核 / Agent 检索共用，同一 OpenAI 兼容渠道）----
    # 视觉模型：审核快筛、需要读图的场景
    AI_VISION_MODEL: str = "qwen3-vl-plus"
    # 文本/推理模型：难例复核、检索意图解析与结果解释
    # 注意：deepseek-v4.1-flash 是推理型，max_tokens 必须给足（≥2048），否则可见输出会被思维链吃光
    AI_TEXT_MODEL: str = "deepseek-v4.1-flash-1017"
    # 模型价格表（每 1M token，USD），用于成本估算；形如 {"model-id": {"input": 0.1, "output": 0.3}}
    # 默认值按 2026-11 调研价换算（qwen3-vl-plus 官方 1 元/M 输入、10 元/M 输出 ÷ 7.1；
    # deepseek-v4.1-flash 走中转站，按便宜档估算）。可在 .env 用 JSON 覆盖。
    AI_MODEL_PRICES: dict[str, dict[str, float]] = Field(
        default_factory=lambda: {
            "qwen3-vl-plus": {"input": 0.14, "output": 1.41},
            "qwen3-vl": {"input": 0.14, "output": 1.41},
            "deepseek-v4.1-flash": {"input": 0.10, "output": 0.40},
            "deepseek-v4-flash": {"input": 0.10, "output": 0.40},
        }
    )

    # ---- 站内 AI 生图（AI 创作台）----
    # 生成走百炼直连异步接口（qwen-image-3.0-pro，单张约 50s）；生成图只是草稿，
    # 发布仍走普通上传 / 审核 / AIGC 强制声明链路，因此这里只存本地临时文件。
    AIGC_GENERATION_ENABLED: bool = True
    AIGC_IMAGE_MODEL: str = "qwen-image-3.0-pro"
    AIGC_IMAGE_API_BASE: str = "https://dashscope.aliyuncs.com"
    AIGC_IMAGE_TIMEOUT: int = 180  # 秒：排队 + 生成 + 下载的总上限
    AIGC_IMAGE_POLL_INTERVAL: float = 3.0
    # 尺寸档位：键给前端，值传给百炼（宽*高，注意百炼用 * 而不是 x）
    AIGC_IMAGE_SIZES: dict[str, str] = Field(
        default_factory=lambda: {
            "square": "1328*1328",
            "landscape": "1664*928",
            "portrait": "928*1664",
        }
    )
    # 每用户每日基础额度（失败不计）；管理员不限，用尽后可消耗管理员赠送池
    AIGC_IMAGE_DAILY_LIMIT: int = 3
    AIGC_IMAGE_PRICE_USD: float = 0.0  # 按张成本；按渠道实际单价填写，用于用量页估算
    AIGC_IMAGE_MAX_BYTES: int = 20 * 1024 * 1024

    # ---- Agent 审核（moderation）----
    MODERATION_ENABLED: bool = True
    MODERATION_PREFILTER_MODEL: str = ""  # 空 → AI_VISION_MODEL
    MODERATION_ESCALATION_MODEL: str = ""  # 空 → AI_TEXT_MODEL
    MODERATION_PREFILTER_MAX_TOKENS: int = 1024
    MODERATION_ESCALATION_MAX_TOKENS: int = 3072  # 推理型模型需要足够预算
    MODERATION_PREFILTER_IMAGE_MAX_EDGE: int = 1024  # 送 VLM 前压到长边 1024，省带宽与 token
    MODERATION_PREFILTER_TEMPERATURE: float = 0.1
    MODERATION_ESCALATION_TEMPERATURE: float = 0.2
    # 快筛置信度低于该值 → 升级复核
    MODERATION_ESCALATION_CONFIDENCE: float = 0.6
    # 规则无硬拦截且快筛判 L0、置信度不低于该值 → 自动放行（免审即发）
    MODERATION_AUTO_APPROVE_CONFIDENCE: float = 0.8
    MODERATION_AUTO_APPROVE_L0: bool = True
    # 每日调用上限（0 = 不限；开发阶段用户明确说不限流）
    MODERATION_DAILY_CALL_BUDGET: int = 0
    MODERATION_RETRY: int = 2
    # ---- 审核即打标（同一次快筛调用顺带落标签/分类，不额外花钱）----
    MODERATION_AUTO_TAGGING: bool = True
    AUTO_TAGGING_MAX_TAGS: int = 6
    # 近重复检测的 dhash 汉明距离阈值（越大越宽松）
    MODERATION_DUPLICATE_HAMMING: int = 5
    # ---- 审核队列持久化与内嵌 worker ----
    # 入队即落库（moderation_reviews.status=queued），重启/崩溃不丢任务；
    # fancy 快路径仍用 BackgroundTasks 立即跑，worker 作为兜底
    MODERATION_QUEUE_MODE: str = "durable"  # durable | inline
    MODERATION_WORKER_EMBEDDED: bool = True  # 在 API 进程内跑队列消费循环
    MODERATION_WORKER_POLL_SECONDS: float = 5.0
    MODERATION_WORKER_BATCH: int = 3
    # running 超过该时长视为 worker 中途崩溃，回收为 queued 重试
    MODERATION_WORKER_STALE_SECONDS: int = 900

    # ---- Agent 驱动的图片检索（agent search）----
    AGENT_SEARCH_ENABLED: bool = True
    AGENT_SEARCH_MODEL: str = ""  # 空 → AI_TEXT_MODEL
    AGENT_SEARCH_MAX_STEPS: int = 4
    AGENT_SEARCH_TIMEOUT: int = 20
    AGENT_SEARCH_EXPLAIN: bool = True  # 是否生成结果解释（多一次模型调用）
    AGENT_SEARCH_CLARIFY_ENABLED: bool = True
    AGENT_SEARCH_TRACE_ENABLED: bool = True
    AGENT_SEARCH_DAILY_CALL_BUDGET: int = 0  # 0 = 不限
    AGENT_SEARCH_LIMIT_MAX: int = 100

    # 向量搜索 / Milvus 配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION_NAME: str = "photo_vectors_v2"
    MILVUS_LEGACY_COLLECTION_NAME: str = "photo_vectors"
    MILVUS_EMBEDDING_DIM: int = 512
    
    # SSO/OAuth 预留配置（对接学校统一身份认证）
    # 认证流程类似 Google OAuth: authorize → callback → token → userinfo
    SSO_ENABLED: bool = False
    SSO_PROVIDER: str = "university_sso"  # 认证提供方标识
    SSO_CLIENT_ID: str | None = None
    SSO_CLIENT_SECRET: str | None = None
    SSO_AUTHORIZE_URL: str | None = None    # 学校认证页面 URL
    SSO_TOKEN_URL: str | None = None        # 获取 Token 的 URL
    SSO_USERINFO_URL: str | None = None     # 获取用户信息的 URL
    SSO_REDIRECT_URI: str = "http://localhost:5173/auth/callback"
    SSO_SCOPES: str = "openid profile email"
    SSO_AUTO_CREATE_USER: bool = True       # SSO 登录时自动创建本地用户

    # 注册配置
    REGISTRATION_ENABLED: bool = True  # 是否开放注册（关闭后 /auth/register 返回 403）
    REGISTRATION_INVITE_CODE: str = ""  # 非空时注册必须填写该邀请码（校园内测/限量放号用）
    REQUIRE_REGISTRATION_APPROVAL: bool = False  # 是否开启注册审批

    # ── 邮箱验证码 / 邮件发送 ──
    # EMAIL_ENABLED=False 时不真实发送（本地开发用 console 输出到日志），
    # 生产通过 SMTP 或 Resend API 发送；注册/找回密码是否强制验证码见下方开关。
    EMAIL_ENABLED: bool = False
    EMAIL_PROVIDER: str = "console"  # console | smtp | resend
    SMTP_HOST: str = ""
    SMTP_PORT: int = 465
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "视觉百花 <noreply@buct-sakura.cn>"
    SMTP_USE_SSL: bool = True
    SMTP_USE_TLS: bool = False
    RESEND_API_KEY: str = ""
    RESEND_FROM: str = "视觉百花 <noreply@buct-sakura.cn>"
    EMAIL_CODE_LENGTH: int = 6
    EMAIL_CODE_TTL_SECONDS: int = 600  # 验证码有效期（秒）
    EMAIL_CODE_COOLDOWN_SECONDS: int = 60  # 同一邮箱同一用途的重发冷却
    EMAIL_CODE_MAX_ATTEMPTS: int = 5  # 单条验证码最多尝试次数
    EMAIL_CODE_HOURLY_LIMIT: int = 10  # 同一邮箱每小时最多发码次数
    REQUIRE_EMAIL_VERIFICATION: bool = False  # 注册是否强制邮箱验证（生产建议 True）
    ALLOW_PASSWORDLESS_EMAIL_LOGIN: bool = True  # 是否允许邮箱验证码免密登录

    # 登录保护
    LOGIN_MAX_FAILED_ATTEMPTS: int = 5
    LOGIN_LOCK_MINUTES: int = 15

    # CORS 配置
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:5175",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://127.0.0.1:5175",
        "http://127.0.0.1:3000",
    ]

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug_flag(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "prod", "production"}:
            return False
        return value

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()
