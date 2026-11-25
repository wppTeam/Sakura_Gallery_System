"""
User Pydantic schemas

用户相关的数据传输对象定义。
支持 student_id (学号/工号) 作为核心身份标识。
"""
from datetime import datetime
from typing import Optional
from enum import Enum
from pydantic import BaseModel, EmailStr, Field, field_validator


def validate_password_strength(password: str) -> str:
    if len(password) < 8:
        raise ValueError("密码至少8位")
    if not any(c.islower() for c in password):
        raise ValueError("密码需包含小写字母")
    if not any(c.isupper() for c in password):
        raise ValueError("密码需包含大写字母")
    if not any(c.isdigit() for c in password):
        raise ValueError("密码需包含数字")
    return password


class RoleEnum(str, Enum):
    """
    用户角色枚举
    
    - admin: 超级管理员，拥有所有权限
    - auditor: 审核员，可审核照片和编辑标签
    - tagger: 学生标注员，只能处理分配给自己的标注任务
    - dept_user: 部门用户，预留扩展
    - user: 普通用户
    """
    ADMIN = "admin"
    AUDITOR = "auditor"
    TAGGER = "tagger"
    DEPT_USER = "dept_user"
    USER = "user"


class UserBase(BaseModel):
    """Base user schema"""
    student_id: str  # 学号/工号，核心身份标识，必填
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    # 公开身份：公开页只展示这两个字段，学号/真名永不对外（AGENTS.md §5）
    username: Optional[str] = None
    display_name: Optional[str] = None


class UserCreate(UserBase):
    """用户注册 schema (公开注册)

    email_code：邮箱验证码。REQUIRE_EMAIL_VERIFICATION=True 时必填；
    为 False 时如果填了也会校验（用于「注册即验证」的可选流程）。
    """
    password: str
    email_code: Optional[str] = Field(default=None, min_length=4, max_length=12)
    invite_code: Optional[str] = Field(default=None, max_length=64)

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class RegistrationConfig(BaseModel):
    """公开的注册配置，前端据此决定展示邀请码 / 关闭注册提示。"""

    enabled: bool = True
    invite_required: bool = False
    email_verification_required: bool = False
    approval_required: bool = False


class UserCreateByAdmin(UserBase):
    """
    管理员创建用户 schema
    
    允许管理员在创建用户时指定角色和学号。
    student_id 为必填字段。
    """
    password: str
    role: RoleEnum = RoleEnum.USER

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class UserUpdate(BaseModel):
    """用户自我更新 schema"""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None


class UserUpdateByAdmin(BaseModel):
    """
    管理员更新用户 schema
    
    允许管理员修改用户的激活状态、角色和学号。
    """
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    password: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[RoleEnum] = None
    student_id: Optional[str] = None
    email_verified: Optional[bool] = None


class UserRoleUpdate(BaseModel):
    """
    管理员修改用户角色 schema
    """
    role: RoleEnum


class UserInDB(UserBase):
    """User in database schema"""
    # 响应侧对 email 宽松：DB 中历史/导入数据可能是非法邮箱，
    # 不应因为响应校验失败让 /auth/me 等接口 500（输入侧仍用 EmailStr 校验）。
    email: Optional[str] = None
    id: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None
    login_count: int = 0
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    token_version: int = 1
    email_verified: bool = False

    class Config:
        from_attributes = True


class User(UserInDB):
    """User response schema"""
    pass


class UserList(BaseModel):
    """用户列表响应 schema"""
    users: list[User]
    total: int


class PasswordChange(BaseModel):
    """用户自助修改密码"""
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class AdminPasswordReset(BaseModel):
    """管理员重置用户密码"""
    new_password: str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return validate_password_strength(v)


class AccountDeleteRequest(BaseModel):
    """作者自助注销账号。

    confirm 必须为「注销」两个字，password 用于二次确认身份；两者都不可省，
    防止误触与令牌泄露后的恶意注销。
    """

    password: str = Field(..., min_length=1, max_length=128)
    confirm: str = Field(..., min_length=1, max_length=16)
