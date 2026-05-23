"""
用户认证相关 Schema（请求/响应 DTO）
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    repassword: str = Field(..., min_length=6, max_length=100, description="确认密码")
    email: Optional[str] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")

    @model_validator(mode="after")
    def validate_passwords_match(self) -> "UserCreate":
        if self.password != self.repassword:
            raise ValueError("两次输入的密码不一致")
        return self


class AdminUserUpdate(BaseModel):
    """管理员更新用户请求（所有字段可选）"""
    username: Optional[str] = Field(None, min_length=3, max_length=64)
    email: Optional[str] = Field(None, max_length=255)
    nickname: Optional[str] = Field(None, max_length=64)
    avatar_url: Optional[str] = Field(None, max_length=512)
    password: Optional[str] = Field(None, min_length=6, max_length=100)
    sort_order: Optional[int] = Field(None)
    is_superuser: Optional[bool] = Field(None)
    disabled_at: Optional[datetime] = Field(None)


class UserAvatarUpdate(BaseModel):
    """用户头像 URL 更新请求"""
    avatar_url: str = Field(..., max_length=512, description="头像地址")


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户信息响应"""
    public_id: str = Field(..., description="用户公开标识")
    username: str = Field(..., description="用户名")
    nickname: Optional[str] = Field(None, description="昵称")
    email: Optional[str] = Field(None, description="邮箱")
    avatar_url: Optional[str] = Field(None, description="头像地址")
    is_superuser: bool = Field(default=False, description="是否管理员")
    disabled: bool = Field(default=False, description="是否已禁用")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")

    class Config:
        from_attributes = True


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool = Field(default=True, description="是否成功")
    message: str = Field(default="登录成功", description="响应消息")
    access_token: str = Field(..., description="访问令牌")
    refresh_token: str = Field(..., description="刷新令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="有效期（秒）")
    user: Optional[UserResponse] = Field(None, description="用户信息")


class TokenRefreshRequest(BaseModel):
    """刷新 Access Token 请求"""
    refresh_token: str = Field(..., description="刷新令牌")


class TokenRefreshResponse(BaseModel):
    """刷新 Access Token 响应"""
    access_token: str = Field(..., description="新访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="有效期（秒）")


class UserProfileUpdate(BaseModel):
    """当前用户资料更新请求"""
    email: Optional[str] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")


class UserPasswordUpdate(BaseModel):
    """当前用户密码修改请求"""
    old_password: str = Field(..., min_length=6, max_length=100, description="旧密码")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")
    confirm_password: str = Field(..., min_length=6, max_length=100, description="确认新密码")

    @model_validator(mode="after")
    def validate_passwords(self) -> "UserPasswordUpdate":
        if self.new_password != self.confirm_password:
            raise ValueError("两次输入的新密码不一致")
        if self.old_password == self.new_password:
            raise ValueError("新密码不能与当前密码相同")
        return self
