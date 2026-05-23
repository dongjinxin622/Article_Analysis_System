"""
用户认证依赖注入
提供 JWT + Redis 双校验的认证依赖函数
"""
from typing import Optional
from fastapi import Depends, Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_db
from backend.app.core.jwt_tools import decode_token
from backend.app.services import user_service

# HTTP Bearer 认证方案
http_bearer = HTTPBearer(auto_error=False)

# RFC 7235 规范要求的 WWW-Authenticate 响应头
BEARER_AUTH_HEADER = {"WWW-Authenticate": "Bearer"}


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer),
    db: AsyncSession = Depends(get_db),
) -> Optional[object]:
    """从 JWT 解析当前用户（可选认证，未提供 token 返回 None）"""
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        return None

    try:
        payload = await decode_token(credentials.credentials, refresh_access_ttl=True)
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="access token 无效或已过期",
            headers=BEARER_AUTH_HEADER,
        )

    if payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请提供 access token",
            headers=BEARER_AUTH_HEADER,
        )

    public_id = str(payload["sub"])
    user = await user_service.get_user_by_public_id(db, public_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
            headers=BEARER_AUTH_HEADER,
        )

    return user


async def get_current_user_required(
    user: Optional[object] = Depends(get_current_user),
) -> object:
    """获取当前用户（必须认证，未登录抛 401）"""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要认证",
            headers=BEARER_AUTH_HEADER,
        )
    return user


async def get_admin_user(
    user: object = Depends(get_current_user_required),
) -> object:
    """获取管理员用户（非管理员抛 403）"""
    if not getattr(user, "is_superuser", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return user
