"""
JWT 令牌工具模块
提供令牌创建、解码、刷新、吊销功能，双令牌 + Redis jti 存储
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from jose import jwt, JWTError

from backend.app.core.config import settings
from backend.app.core import redis_client as _redis_client

logger = logging.getLogger(__name__)


def _token_cache_key(jti: str) -> str:
    """生成 token 在 Redis 中的缓存键"""
    return f"{settings.REDIS_TOKEN_KEY_PREFIX}{jti}"


async def _cache_token(jti: str, public_id: str, token_type: str, expires_at: int) -> None:
    """将 token 标识缓存到 Redis，用于后续校验和吊销"""
    redis_client = await _redis_client.get_redis()
    ttl_seconds = expires_at - int(datetime.now(timezone.utc).timestamp())
    if ttl_seconds <= 0:
        return

    value = json.dumps(
        {
            "public_id": public_id,
            "token_type": token_type,
            "expires_at": expires_at,
        },
        separators=(",", ":"),
    )
    await redis_client.set(_token_cache_key(jti), value, ex=ttl_seconds)


async def _create_token(public_id: str, username: str, token_type: str, expires_seconds: int) -> tuple:
    """创建单个 JWT 令牌

    Args:
        public_id: 用户对外唯一标识
        username: 用户名
        token_type: 令牌类型 (access / refresh)
        expires_seconds: 过期秒数

    Returns:
        (token字符串, jti, expires_in秒数)
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=expires_seconds)
    jti = uuid4().hex

    payload = {
        "sub": public_id,
        "username": username,
        "type": token_type,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    await _cache_token(jti, public_id, token_type, int(expire.timestamp()))
    return token, jti, expires_seconds


async def create_login_tokens(public_id: str, username: str) -> dict:
    """生成登录所需的 access token 和 refresh token

    Returns:
        {"access_token": str, "refresh_token": str, "expires_in": int}
    """
    access_token, _, expires_in = await _create_token(
        public_id=public_id,
        username=username,
        token_type="access",
        expires_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    refresh_token, _, _ = await _create_token(
        public_id=public_id,
        username=username,
        token_type="refresh",
        expires_seconds=settings.REFRESH_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
    }


async def decode_token(token: str, *, refresh_access_ttl: bool = False) -> dict:
    """解析并校验 JWT，同时验证 Redis 中的 jti 存在性

    Args:
        token: 待解析的 JWT 字符串
        refresh_access_ttl: 是否续期 access token 在 Redis 中的 TTL

    Returns:
        解析后的 token payload

    Raises:
        ValueError: 令牌已被吊销或无效
    """
    redis_client = await _redis_client.get_redis()

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as exc:
        raise ValueError("令牌无效或已过期") from exc

    jti = str(payload.get("jti", ""))
    if not jti:
        raise ValueError("令牌格式无效")

    cache_key = _token_cache_key(jti)
    cached = await redis_client.get(cache_key)
    if cached is None:
        raise ValueError("令牌已被吊销或已过期")

    # 续期 access token 的 Redis TTL
    if refresh_access_ttl and payload.get("type") == "access":
        await redis_client.expire(cache_key, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    return payload


async def create_access_token_from_refresh_token(refresh_token: str) -> dict:
    """使用 refresh token 换取新的 access token（refresh token 轮换）

    Returns:
        {"access_token": str, "expires_in": int}
    """
    payload = await decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise ValueError("需要 refresh token")

    public_id = str(payload.get("sub", ""))
    username = str(payload.get("username", ""))
    if not public_id or not username:
        raise ValueError("无效的 refresh token payload")

    # 吊销旧的 refresh token（实现轮换）
    old_jti = str(payload.get("jti", ""))
    await revoke_token(old_jti)

    access_token, _, expires_in = await _create_token(
        public_id=public_id,
        username=username,
        token_type="access",
        expires_seconds=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {
        "access_token": access_token,
        "expires_in": expires_in,
    }


async def revoke_token(jti: str) -> None:
    """从 Redis 中吊销指定 token"""
    redis_client = await _redis_client.get_redis()
    await redis_client.delete(_token_cache_key(jti))
    logger.debug("已吊销 token: %s...", jti[:16])
