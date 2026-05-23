"""
用户系统测试基础设施
提供 SQLite 内存数据库 + Redis Mock 的隔离测试环境
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# 添加项目根目录（backend/ 的父目录）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ==================== Fake Redis ====================

class FakeRedis:
    """内存中的 Redis 模拟，用于 JWT jti 缓存"""

    def __init__(self):
        self._store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def expire(self, key: str, ttl: int) -> None:
        pass

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._store.clear()


# ==================== 数据库 Fixture ====================

@pytest.fixture
async def test_engine():
    """创建 SQLite 异步内存引擎"""
    from backend.app.models.base import Base

    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def test_db_session(test_engine) -> AsyncSession:
    """创建独立数据库会话，自动回滚"""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


# ==================== 全局 Redis Mock ====================

@pytest.fixture(autouse=True)
def _mock_redis_globally():
    """全局自动 Mock Redis，确保所有测试（包括 service 测试）不依赖真实 Redis"""
    fake_redis = FakeRedis()

    async def _get_redis():
        return fake_redis

    patchers = [
        patch("backend.app.core.redis_client.get_redis", _get_redis),
        patch("backend.app.core.redis_client.close_redis", AsyncMock()),
    ]
    for p in patchers:
        p.start()

    yield

    for p in patchers:
        p.stop()


# ==================== HTTP 客户端 Fixture ====================

@pytest.fixture
async def test_client(test_engine) -> "AsyncClient":
    """创建 httpx 异步测试客户端，挂载 FastAPI 应用

    Redis mock 由 _mock_redis_globally (autouse) 全局提供。
    """
    from httpx import ASGITransport, AsyncClient

    # 替换数据库引擎为测试引擎
    import backend.app.models.base as base_mod
    base_mod.engine = test_engine
    base_mod.AsyncSessionLocal = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False,
    )

    from backend.app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


# ==================== 辅助函数 ====================

async def create_test_user(session: AsyncSession, **kwargs) -> "User":
    """在测试数据库中快速创建用户"""
    from backend.app.models.user import User
    from uuid import uuid4
    from datetime import datetime

    user = User(
        public_id=kwargs.get("public_id", str(uuid4())),
        username=kwargs.get("username", "testuser"),
        nickname=kwargs.get("nickname", "测试用户"),
        email=kwargs.get("email", "test@example.com"),
        password_hash=kwargs.get("password_hash", "hashed"),
        is_superuser=kwargs.get("is_superuser", False),
        sort_order=kwargs.get("sort_order", 0),
        created_at=kwargs.get("created_at", datetime.utcnow()),
        updated_at=kwargs.get("updated_at", datetime.utcnow()),
        disabled_at=kwargs.get("disabled_at", None),
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def login_and_get_tokens(client: "AsyncClient", username: str = "testuser", password: str = "test123456") -> dict:
    """辅助函数：注册并登录，返回 tokens"""
    await client.post("/api/v1/users/register", json={
        "username": username,
        "password": password,
        "repassword": password,
        "email": f"{username}@test.com",
    })
    resp = await client.post("/api/v1/users/login", json={
        "username": username,
        "password": password,
    })
    assert resp.status_code == 200
    return resp.json()
