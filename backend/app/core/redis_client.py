"""
Redis 异步客户端单例管理
"""
import logging
from typing import Optional
import redis.asyncio as aioredis

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """获取 Redis 异步客户端单例，首次调用时自动初始化连接"""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            encoding="utf-8",
        )
        await _redis_client.ping()
        logger.info("Redis 连接已建立: %s", settings.REDIS_URL)
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接池"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis 连接已关闭")
