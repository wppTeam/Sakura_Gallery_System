"""邮箱验证码签发与校验

- 验证码只存 HMAC-SHA256 摘要，不存明文
- 同一邮箱 + 用途有冷却时间与每小时上限，防轰炸
- 单条验证码有尝试次数上限，防止暴力猜解
- 签发成功后真实发信失败会回滚记录并返回明确错误
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.email_code import EmailVerificationCode
from app.services.email import EmailDeliveryError, send_verification_code_email

logger = logging.getLogger(__name__)

VALID_PURPOSES = ("register", "login", "reset_password", "verify_email")


class EmailCodeError(Exception):
    """验证码相关的可预期错误，路由层转成对应 HTTP 响应。"""

    def __init__(self, message: str, *, status_code: int = 400, retry_after: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass
class IssuedCode:
    code: str
    expires_in: int
    cooldown_seconds: int
    delivered: bool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _hash_code(email: str, purpose: str, code: str) -> str:
    settings = get_settings()
    key = (settings.SECRET_KEY or "sakura-gallery").encode("utf-8")
    payload = f"{email}:{purpose}:{code}".encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _generate_code(length: int) -> str:
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(max(4, length)))


async def _purge_expired(db: AsyncSession) -> None:
    """清理一天前的过期验证码，避免表无限增长。"""
    cutoff = _utcnow() - timedelta(days=1)
    try:
        await db.execute(
            delete(EmailVerificationCode).where(EmailVerificationCode.expires_at < cutoff)
        )
        await db.commit()
    except Exception:  # pragma: no cover - 清理失败不影响主流程
        await db.rollback()
        logger.warning("清理过期邮箱验证码失败", exc_info=True)


async def issue_code(
    db: AsyncSession,
    email: str,
    purpose: str,
    *,
    request_ip: Optional[str] = None,
) -> IssuedCode:
    """签发验证码并尝试发送邮件。"""
    if purpose not in VALID_PURPOSES:
        raise EmailCodeError("不支持的验证码用途", status_code=422)

    settings = get_settings()
    email = normalize_email(email)
    if not email:
        raise EmailCodeError("请填写邮箱", status_code=422)

    await _purge_expired(db)

    now = _utcnow()
    cooldown = max(0, int(settings.EMAIL_CODE_COOLDOWN_SECONDS))
    ttl = max(60, int(settings.EMAIL_CODE_TTL_SECONDS))

    latest = (
        await db.execute(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is not None and cooldown:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < cooldown:
            retry_after = int(cooldown - elapsed) + 1
            raise EmailCodeError(
                f"发送过于频繁，请 {retry_after} 秒后再试",
                status_code=429,
                retry_after=retry_after,
            )

    hourly_limit = max(1, int(settings.EMAIL_CODE_HOURLY_LIMIT))
    hour_ago = now - timedelta(hours=1)
    sent_last_hour = (
        await db.execute(
            select(func.count())
            .select_from(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.created_at >= hour_ago,
            )
        )
    ).scalar_one()
    if sent_last_hour >= hourly_limit:
        raise EmailCodeError(
            "该邮箱验证码发送次数过多，请稍后再试",
            status_code=429,
            retry_after=3600,
        )

    code = _generate_code(int(settings.EMAIL_CODE_LENGTH or 6))
    record = EmailVerificationCode(
        email=email,
        purpose=purpose,
        code_hash=_hash_code(email, purpose, code),
        expires_at=now + timedelta(seconds=ttl),
        request_ip=(request_ip or "")[:64] or None,
    )
    db.add(record)
    await db.commit()

    try:
        delivered = await send_verification_code_email(email, code, purpose, ttl)
    except EmailDeliveryError as exc:
        logger.warning("验证码邮件发送失败 email=%s purpose=%s: %s", email, purpose, exc)
        await db.delete(record)
        await db.commit()
        raise EmailCodeError(
            "邮件发送失败，请稍后重试或联系站点管理员", status_code=503
        ) from exc

    return IssuedCode(
        code=code,
        expires_in=ttl,
        cooldown_seconds=cooldown,
        delivered=delivered,
    )


async def verify_code(db: AsyncSession, email: str, purpose: str, code: str) -> None:
    """校验验证码；成功即消费。失败抛 EmailCodeError。"""
    settings = get_settings()
    email = normalize_email(email)
    code = (code or "").strip()

    record = (
        await db.execute(
            select(EmailVerificationCode)
            .where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
            )
            .order_by(EmailVerificationCode.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if record is None:
        raise EmailCodeError("验证码已失效，请重新获取")
    if record.expires_at <= _utcnow():
        raise EmailCodeError("验证码已过期，请重新获取")

    max_attempts = max(1, int(settings.EMAIL_CODE_MAX_ATTEMPTS))
    if record.attempts >= max_attempts:
        raise EmailCodeError("验证码尝试次数过多，请重新获取")

    expected = _hash_code(email, purpose, code)
    if not hmac.compare_digest(expected, record.code_hash):
        record.attempts += 1
        await db.commit()
        remaining = max(0, max_attempts - record.attempts)
        if remaining <= 0:
            raise EmailCodeError("验证码尝试次数过多，请重新获取")
        raise EmailCodeError(f"验证码不正确，还可尝试 {remaining} 次")

    record.consumed_at = _utcnow()
    await db.commit()


async def invalidate_codes(db: AsyncSession, email: str, purpose: str) -> None:
    """使该邮箱该用途的所有未消费验证码失效（注册成功/重置成功后调用）。"""
    email = normalize_email(email)
    records = (
        await db.execute(
            select(EmailVerificationCode).where(
                EmailVerificationCode.email == email,
                EmailVerificationCode.purpose == purpose,
                EmailVerificationCode.consumed_at.is_(None),
            )
        )
    ).scalars().all()
    if not records:
        return
    now = _utcnow()
    for record in records:
        record.consumed_at = now
    await db.commit()
