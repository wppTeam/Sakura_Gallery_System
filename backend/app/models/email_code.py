"""邮箱验证码模型

用于注册验证、邮箱验证码登录、找回密码、邮箱归属验证。
只存验证码哈希（HMAC-SHA256），不存明文；验证码短时效、一次性、有尝试次数上限。
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, String

from app.core.database import Base


def _utcnow_naive() -> datetime:
    """统一用 naive UTC 存库（与项目其它时间字段一致，避免 SQLite/PG 时区差异）。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EmailVerificationCode(Base):
    """邮箱验证码

    Attributes:
        email: 归一化（小写去空格）后的邮箱
        purpose: register | login | reset_password | verify_email
        code_hash: HMAC-SHA256(email:purpose:code, SECRET_KEY) 的十六进制摘要
        expires_at: 过期时间
        consumed_at: 已使用时间（非空表示已消费）
        attempts: 已尝试次数（超过上限即失效）
        request_ip: 申请来源 IP，便于审计与滥用排查
    """

    __tablename__ = "email_verification_codes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, index=True)
    purpose = Column(String(32), nullable=False)
    code_hash = Column(String(128), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, default=0, nullable=False)
    request_ip = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=_utcnow_naive, nullable=False)

    __table_args__ = (
        Index("ix_email_codes_email_purpose", "email", "purpose"),
        Index("ix_email_codes_expires_at", "expires_at"),
    )

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<EmailVerificationCode(email='{self.email}', purpose='{self.purpose}', consumed={self.consumed_at is not None})>"
