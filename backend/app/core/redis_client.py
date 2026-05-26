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
    """获取 Redis 异步客户端单例，首次调用时自动初始化连接

    当已缓存的连接不可用时（断线/超时），自动重置并重新建立连接。
    """
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            encoding="utf-8",
        )
        try:
            await _redis_client.ping()
            logger.info("Redis 连接已建立: %s", settings.REDIS_URL)
        except Exception:
            _redis_client = None
            raise
    else:
        # 检测已缓存连接是否仍然可用
        try:
            await _redis_client.ping()
        except Exception as exc:
            logger.warning("Redis 连接已断开 (%s)，正在重新连接...", exc)
            try:
                await _redis_client.close()
            except Exception:
                pass
            _redis_client = None
            # 递归重试一次
            return await get_redis()
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接池"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
        logger.info("Redis 连接已关闭")
