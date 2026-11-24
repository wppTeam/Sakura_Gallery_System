"""邮箱验证码 / 认证增强相关的 Pydantic schema"""
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.schemas.user import validate_password_strength


class EmailCodePurpose(str, Enum):
    REGISTER = "register"
    LOGIN = "login"
    RESET_PASSWORD = "reset_password"
    VERIFY_EMAIL = "verify_email"


class EmailCodeRequest(BaseModel):
    """请求发送邮箱验证码"""

    email: EmailStr
    purpose: EmailCodePurpose


class EmailCodeResponse(BaseModel):
    ok: bool = True
    message: str = "验证码已发送，请查收邮箱"
    expires_in: int
    cooldown_seconds: int
    delivered: bool = True
    # 仅本地开发（EMAIL_ENABLED=false 且 DEBUG=true）返回，生产永远为 None
    dev_code: Optional[str] = None


class EmailCodeLoginRequest(BaseModel):
    """邮箱验证码免密登录"""

    email: EmailStr
    code: str = Field(..., min_length=4, max_length=12)


class ForgotPasswordRequest(BaseModel):
    """发起找回密码：identifier 可为邮箱 / 学号 / 用户名"""

    identifier: str = Field(..., min_length=1, max_length=255)


class ForgotPasswordResponse(BaseModel):
    ok: bool = True
    message: str = "如果该账号绑定了邮箱，验证码已发送"
    cooldown_seconds: int = 60
    dev_code: Optional[str] = None


class ResetPasswordRequest(BaseModel):
    identifier: str = Field(..., min_length=1, max_length=255)
    code: str = Field(..., min_length=4, max_length=12)
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class VerifyEmailRequest(BaseModel):
    """登录用户验证自己的邮箱（邮箱已在账号资料中）"""

    code: str = Field(..., min_length=4, max_length=12)
