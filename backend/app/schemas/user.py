"""
用户认证相关 Schema
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserCreate(BaseModel):
    """用户创建请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    email: Optional[str] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")


class UserLogin(BaseModel):
    """用户登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class Token(BaseModel):
    """Token 响应"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")


class TokenData(BaseModel):
    """Token 数据"""
    user_id: Optional[int] = Field(None, description="用户 ID")
    username: Optional[str] = Field(None, description="用户名")


class UserResponse(BaseModel):
    """用户响应"""
    id: int = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, description="全名")
    is_active: bool = Field(default=True, description="是否激活")
    is_admin: bool = Field(default=False, description="是否管理员")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    last_login: Optional[datetime] = Field(None, description="最后登录时间")


class UserUpdate(BaseModel):
    """用户更新请求"""
    email: Optional[str] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, description="全名")
    password: Optional[str] = Field(None, min_length=6, description="新密码")


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    token: Optional[Token] = Field(None, description="令牌信息")
    user: Optional[UserResponse] = Field(None, description="用户信息")