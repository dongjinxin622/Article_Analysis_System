"""
数据库连接管理 - 异步版本
使用 asyncpg 实现异步数据库操作
针对远程PostgreSQL服务器连接不稳定问题进行优化
"""
import logging
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import OperationalError
from typing import AsyncGenerator
from contextlib import asynccontextmanager

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

# 创建异步数据库引擎
# PostgreSQL (asyncpg) 配置：
# - pool_pre_ping: 每次使用前检查连接有效性
# - pool_recycle: 1小时回收连接（PG 默认不回收）
# - pool_timeout: 获取连接超时时间
# - echo: 调试模式下显示SQL
engine = create_async_engine(
    settings.DATABASE_URL_ASYNC,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_timeout=30,
    echo=settings.DEBUG,
    pool_size=5,
    max_overflow=10,
)

# 创建异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False
)

# 模型基类
Base = declarative_base()


async def init_db():
    """异步初始化数据库（创建所有表）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    获取异步数据库会话（用于依赖注入）
    包含连接错误重试机制
    """
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            async with AsyncSessionLocal() as session:
                try:
                    yield session
                    await session.commit()
                    return  # 成功完成，退出
                except OperationalError as e:
                    # 连接错误，尝试重试
                    if 'server closed the connection' in str(e) or 'connection was closed' in str(e):
                        logger.warning(f"数据库连接丢失，尝试重试 ({attempt + 1}/{max_retries}): {e}")
                        await session.rollback()
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                            continue
                        raise
                    else:
                        await session.rollback()
                        raise
                except Exception:
                    await session.rollback()
                    raise
        except OperationalError as e:
            # 创建会话时的连接错误
            if 'Lost connection' in str(e) or '2013' in str(e) or '2006' in str(e):
                logger.warning(f"数据库连接失败，尝试重试 ({attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                raise
            else:
                raise

    raise OperationalError("数据库连接失败，超过最大重试次数")


@asynccontextmanager
async def get_db_context():
    """
    异步数据库会话上下文管理器
    包含连接错误重试机制
    """
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            async with AsyncSessionLocal() as session:
                try:
                    yield session
                    await session.commit()
                    return  # 成功完成，退出
                except OperationalError as e:
                    # 连接错误，尝试重试
                    if 'server closed the connection' in str(e) or 'connection was closed' in str(e):
                        logger.warning(f"数据库连接丢失，尝试重试 ({attempt + 1}/{max_retries}): {e}")
                        await session.rollback()
                        if attempt < max_retries - 1:
                            await asyncio.sleep(retry_delay * (attempt + 1))
                            continue
                        raise
                    else:
                        await session.rollback()
                        raise
                except Exception:
                    await session.rollback()
                    raise
        except OperationalError as e:
            # 创建会话时的连接错误
            if 'Lost connection' in str(e) or '2013' in str(e) or '2006' in str(e):
                logger.warning(f"数据库连接失败，尝试重试 ({attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                    continue
                raise
            else:
                raise

    raise OperationalError("数据库连接失败，超过最大重试次数")