import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.deps import get_db, get_current_active_user, get_optional_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    get_password_hash,
)
from app.schemas.token import LoginRequest, LoginResponse, RefreshRequest, Token
from app.schemas.user import User, UserCreate, PasswordChange
from app.schemas.email import (
    EmailCodeLoginRequest,
    EmailCodePurpose,
    EmailCodeRequest,
    EmailCodeResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.services import email_codes
from app.services.email_codes import EmailCodeError
from app.crud import user as user_crud

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


# ── 认证辅助 ────────────────────────────────────────────────────────────────

def _login_response(user) -> LoginResponse:
    """为已通过校验的用户签发 Token 对并返回登录响应。"""
    token_data = {"sub": user.student_id, "ver": user.token_version}
    return LoginResponse(
        access_token=create_access_token(data=token_data),
        refresh_token=create_refresh_token(data=token_data),
        token_type="bearer",
        user=User.model_validate(user),
    )


def _code_error(exc: EmailCodeError) -> HTTPException:
    """把验证码错误转成 HTTPException（带 Retry-After）。"""
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(int(exc.retry_after))
    return HTTPException(status_code=exc.status_code, detail=exc.message, headers=headers or None)


async def _find_user_by_identifier(db: AsyncSession, identifier: str):
    """按 邮箱 / 学号 / 用户名 查找用户。"""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    user = await user_crud.get_user_by_email(db, identifier)
    if user is None:
        user = await user_crud.get_user_by_student_id(db, identifier)
    if user is None:
        user = await user_crud.get_user_by_username(db, identifier)
    return user


def _dev_code(settings, code: str):
    """仅本地开发（EMAIL_ENABLED=false 且 DEBUG）把验证码直接返回给前端，便于联调。"""
    return code if (settings.DEBUG and not settings.EMAIL_ENABLED) else None


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    credentials: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    用户登录

    支持学号或邮箱登录，返回 Access Token、Refresh Token 和用户信息。
    """
    # 先查找用户（不校验密码）以支持失败计数
    # 支持三种登录标识：邮箱 / 学号 / 公开用户名（users.username）
    from app.crud.user import get_user_by_email, get_user_by_student_id, get_user_by_username
    user = await get_user_by_email(db, credentials.identifier)
    if not user:
        user = await get_user_by_student_id(db, credentials.identifier)
    if not user:
        user = await get_user_by_username(db, credentials.identifier)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="学号/邮箱/用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 检查账号是否被锁定
    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被锁定，请15分钟后再试"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已被禁用"
        )

    # 校验密码
    if not user_crud.verify_password(credentials.password, user.hashed_password):
        await user_crud.record_login_failure(db, user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="学号/邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 登录成功，记录审计信息
    await user_crud.record_login_success(db, user)

    # 使用 student_id 作为 JWT subject (主要标识)，携带 token_version
    token_data = {"sub": user.student_id, "ver": user.token_version}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user=User.model_validate(user)
    )


@router.get("/me", response_model=User)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """
    获取当前登录用户信息
    """
    return current_user


# ── 邮箱验证码：发送 / 免密登录 / 找回密码 / 邮箱验证 ──────────────────────

@router.post("/email-code", response_model=EmailCodeResponse)
@limiter.limit("5/minute")
async def send_email_code(
    request: Request,
    body: EmailCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_optional_current_user),
):
    """
    发送邮箱验证码。

    purpose：
    - register：邮箱未被注册时才发送
    - login：邮箱已注册且启用才发送（未注册返回通用提示，避免枚举）
    - reset_password：邮箱已注册才发送（同上）
    - verify_email：需登录，发到当前账号绑定的邮箱
    """
    from app.core.config import get_settings
    settings = get_settings()
    purpose = body.purpose.value
    email = str(body.email)

    if purpose == EmailCodePurpose.VERIFY_EMAIL.value:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="请先登录后再验证邮箱",
                headers={"WWW-Authenticate": "Bearer"},
            )
        email = (current_user.email or "").strip()
        if not email:
            raise HTTPException(status_code=400, detail="当前账号未绑定邮箱，请先在个人资料中填写邮箱")
        if current_user.email_verified:
            raise HTTPException(status_code=400, detail="邮箱已验证，无需重复验证")
    elif purpose == EmailCodePurpose.REGISTER.value:
        if await user_crud.get_user_by_email(db, email):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该邮箱已被注册")
    elif purpose in (EmailCodePurpose.LOGIN.value, EmailCodePurpose.RESET_PASSWORD.value):
        user = await user_crud.get_user_by_email(db, email)
        if user is None or not user.is_active:
            return EmailCodeResponse(
                ok=True,
                message="如果该邮箱已注册，验证码已发送",
                expires_in=int(settings.EMAIL_CODE_TTL_SECONDS),
                cooldown_seconds=int(settings.EMAIL_CODE_COOLDOWN_SECONDS),
                delivered=False,
                dev_code=None,
            )

    try:
        issued = await email_codes.issue_code(
            db,
            email,
            purpose,
            request_ip=request.client.host if request.client else None,
        )
    except EmailCodeError as exc:
        raise _code_error(exc) from exc

    return EmailCodeResponse(
        ok=True,
        message="验证码已发送，请查收邮箱（含垃圾箱）",
        expires_in=issued.expires_in,
        cooldown_seconds=issued.cooldown_seconds,
        delivered=issued.delivered,
        dev_code=_dev_code(settings, issued.code),
    )


@router.post("/login-with-code", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login_with_email_code(
    request: Request,
    body: EmailCodeLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """邮箱验证码免密登录。"""
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.ALLOW_PASSWORDLESS_EMAIL_LOGIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前站点未开启验证码登录")

    user = await user_crud.get_user_by_email(db, str(body.email))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或验证码不正确",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.is_locked:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被锁定，请稍后再试")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户已被禁用")

    try:
        await email_codes.verify_code(
            db, str(body.email), EmailCodePurpose.LOGIN.value, body.code
        )
    except EmailCodeError as exc:
        raise _code_error(exc) from exc

    await user_crud.record_login_success(db, user)
    return _login_response(user)


@router.post("/password/forgot", response_model=ForgotPasswordResponse)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """发起找回密码：给账号绑定邮箱发送验证码（不泄露账号是否存在）。"""
    from app.core.config import get_settings
    settings = get_settings()
    cooldown = int(settings.EMAIL_CODE_COOLDOWN_SECONDS)
    generic = ForgotPasswordResponse(
        ok=True,
        message="如果该账号绑定了邮箱，验证码已发送",
        cooldown_seconds=cooldown,
    )

    user = await _find_user_by_identifier(db, body.identifier)
    if user is None or not user.email:
        return generic

    try:
        issued = await email_codes.issue_code(
            db,
            user.email,
            EmailCodePurpose.RESET_PASSWORD.value,
            request_ip=request.client.host if request.client else None,
        )
    except EmailCodeError as exc:
        raise _code_error(exc) from exc

    generic.cooldown_seconds = issued.cooldown_seconds
    generic.dev_code = _dev_code(settings, issued.code)
    return generic


@router.post("/password/reset")
@limiter.limit("5/minute")
async def reset_password(
    request: Request,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """用邮箱验证码重置密码（成功后旧 Token 全部失效）。"""
    user = await _find_user_by_identifier(db, body.identifier)
    if user is None or not user.email:
        raise HTTPException(status_code=400, detail="验证码不正确或已过期")

    try:
        await email_codes.verify_code(
            db, user.email, EmailCodePurpose.RESET_PASSWORD.value, body.code
        )
    except EmailCodeError as exc:
        raise _code_error(exc) from exc

    user.hashed_password = get_password_hash(body.new_password)
    user.token_version = (user.token_version or 1) + 1
    user.failed_login_attempts = 0
    user.locked_until = None
    await db.commit()
    await email_codes.invalidate_codes(db, user.email, EmailCodePurpose.RESET_PASSWORD.value)
    logger.info("用户通过邮箱验证码重置密码 user_id=%s", user.id)
    return {"detail": "密码已重置，请用新密码登录"}


@router.post("/email/send-verification", response_model=EmailCodeResponse)
@limiter.limit("3/minute")
async def send_email_verification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """给当前账号绑定邮箱发送验证码。"""
    from app.core.config import get_settings
    settings = get_settings()
    email = (current_user.email or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="当前账号未绑定邮箱，请先在个人资料中填写邮箱")
    if current_user.email_verified:
        raise HTTPException(status_code=400, detail="邮箱已验证，无需重复验证")

    try:
        issued = await email_codes.issue_code(
            db,
            email,
            EmailCodePurpose.VERIFY_EMAIL.value,
            request_ip=request.client.host if request.client else None,
        )
    except EmailCodeError as exc:
        raise _code_error(exc) from exc

    return EmailCodeResponse(
        ok=True,
        message="验证码已发送到当前绑定邮箱",
        expires_in=issued.expires_in,
        cooldown_seconds=issued.cooldown_seconds,
        delivered=issued.delivered,
        dev_code=_dev_code(settings, issued.code),
    )


@router.post("/email/verify")
async def verify_own_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """用验证码验证当前账号绑定的邮箱。"""
    email = (current_user.email or "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="当前账号未绑定邮箱")
    try:
        await email_codes.verify_code(
            db, email, EmailCodePurpose.VERIFY_EMAIL.value, body.code
        )
    except EmailCodeError as exc:
        raise _code_error(exc) from exc

    current_user.email_verified = True
    await db.commit()
    await db.refresh(current_user)
    return {"detail": "邮箱验证成功", "email_verified": True}


@router.post("/token", response_model=Token)
@limiter.limit("10/minute")
async def login_for_access_token(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    OAuth2 兼容的 token 登录端点

    username 字段可以是学号或邮箱。
    """
    from app.crud.user import get_user_by_email, get_user_by_student_id
    user = await get_user_by_email(db, form_data.username)
    if not user:
        user = await get_user_by_student_id(db, form_data.username)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="学号/邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_locked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账号已被锁定，请15分钟后再试"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户已被禁用"
        )

    if not user_crud.verify_password(form_data.password, user.hashed_password):
        await user_crud.record_login_failure(db, user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="学号/邮箱或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await user_crud.record_login_success(db, user)

    # 使用 student_id 作为 JWT subject，携带 token_version
    token_data = {"sub": user.student_id, "ver": user.token_version}
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)

    return Token(access_token=access_token, refresh_token=refresh_token, token_type="bearer")


@router.post("/refresh", response_model=Token)
@limiter.limit("30/minute")
async def refresh_access_token(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    使用 Refresh Token 获取新的 Access Token

    Refresh Token 过期后用户需重新登录。
    """
    payload = decode_refresh_token(body.refresh_token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )

    student_id = payload.get("sub")
    if not student_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 格式无效",
        )

    # 验证用户仍然存在且活跃
    user = await user_crud.get_user_by_student_id(db, student_id=student_id)
    if user is None:
        user = await user_crud.get_user_by_email(db, email=student_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    # 校验 token_version，防止旧 Refresh Token 在密码修改后仍可用
    token_ver = payload.get("ver")
    if token_ver is not None and token_ver != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 已失效，请重新登录",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 签发新的 Token 对
    token_data = {"sub": user.student_id, "ver": user.token_version}
    new_access_token = create_access_token(data=token_data)
    new_refresh_token = create_refresh_token(data=token_data)

    return Token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.put("/password")
async def change_password(
    body: PasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    用户自助修改密码

    需提供旧密码验证。
    """
    success = await user_crud.change_user_password(
        db,
        user_id=current_user.id,
        old_password=body.old_password,
        new_password=body.new_password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )
    return {"detail": "密码修改成功"}


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    用户注册

    必须提供学号，邮箱可选。
    若开启注册审批 (REQUIRE_REGISTRATION_APPROVAL=True)，
    新注册用户 is_active=False，需管理员审批后方可登录。
    """
    from app.core.config import get_settings
    settings = get_settings()

    # 检查学号是否已存在
    existing_user = await user_crud.get_user_by_student_id(db, user_data.student_id)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该学号已被注册"
        )

    # 公开用户名（可选）：唯一、归一化后入库，登录与公开页都用它
    if user_data.username:
        username = user_data.username.strip()
        if len(username) < 3 or len(username) > 32:
            raise HTTPException(status_code=422, detail="用户名长度需在 3–32 个字符之间")
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+", username):
            raise HTTPException(status_code=422, detail="用户名只能包含字母、数字、下划线、点和短横线")
        user_data = user_data.model_copy(update={"username": username})
        if await user_crud.get_user_by_username(db, username):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="该用户名已被占用")

    # 如果提供了邮箱，检查邮箱是否已存在
    if user_data.email:
        existing_email = await user_crud.get_user_by_email(db, user_data.email)
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该邮箱已被注册"
            )

    # 邮箱验证码：REQUIRE_EMAIL_VERIFICATION=True 时强制；否则填了也会校验
    email_verified = False
    if settings.REQUIRE_EMAIL_VERIFICATION or user_data.email_code:
        if not user_data.email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="注册需要填写邮箱以接收验证码",
            )
        if not user_data.email_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请填写邮箱验证码",
            )
        try:
            await email_codes.verify_code(
                db, str(user_data.email), EmailCodePurpose.REGISTER.value, user_data.email_code
            )
        except EmailCodeError as exc:
            raise _code_error(exc) from exc
        email_verified = True

    # 创建新用户，若开启审批则默认禁用
    is_active = not settings.REQUIRE_REGISTRATION_APPROVAL
    new_user = await user_crud.create_user(db, user_data, role="user")
    new_user.email_verified = email_verified
    if not is_active:
        new_user.is_active = False
    if email_verified and user_data.email:
        await email_codes.invalidate_codes(db, str(user_data.email), EmailCodePurpose.REGISTER.value)
    await db.commit()
    await db.refresh(new_user)

    return User.model_validate(new_user)
