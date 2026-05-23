"""
User Service 层测试
覆盖：CRUD 流程、认证、密码管理、默认管理员引导
使用 SQLite 内存数据库 + FakeRedis Mock
"""
from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime

from backend.app.services import user_service
from backend.app.core import security
from backend.app.core.user_exceptions import (
    UserNotFoundError,
    UserNameConflictError,
    UserEmailConflictError,
    InvalidCredentialsError,
    AccountDisabledError,
    OldPasswordIncorrectError,
)


# ==================== 用户创建测试 ====================

class TestCreateUser:
    """create_user 测试"""

    @pytest.mark.anyio
    async def test_create_user_success(self, test_db_session):
        """正常创建用户"""
        user = await user_service.create_user(
            test_db_session,
            username="newuser",
            password="Test123456",
            email="new@test.com",
            full_name="新用户",
        )
        assert user.id is not None
        assert user.public_id is not None
        assert len(user.public_id) == 36
        assert user.username == "newuser"
        assert user.nickname == "新用户"
        assert user.email == "new@test.com"
        assert user.password_hash != "Test123456"
        assert user.is_superuser is False
        assert user.disabled_at is None
        assert security.verify_password("Test123456", user.password_hash)

    @pytest.mark.anyio
    async def test_create_user_duplicate_username(self, test_db_session):
        """重名用户名应抛出异常"""
        await user_service.create_user(test_db_session, username="dup", password="Pass123")
        with pytest.raises(UserNameConflictError):
            await user_service.create_user(test_db_session, username="dup", password="Pass456")

    @pytest.mark.anyio
    async def test_create_user_duplicate_email(self, test_db_session):
        """重复邮箱应抛出异常"""
        await user_service.create_user(test_db_session, username="u1", password="Pass123", email="same@test.com")
        with pytest.raises(UserEmailConflictError):
            await user_service.create_user(test_db_session, username="u2", password="Pass456", email="same@test.com")

    @pytest.mark.anyio
    async def test_create_user_without_email(self, test_db_session):
        """无邮箱创建用户也应成功"""
        user = await user_service.create_user(test_db_session, username="noemail", password="Pass123")
        assert user.email is None


# ==================== 查询函数测试 ====================

class TestQueryFunctions:
    """查询函数测试"""

    @pytest.mark.anyio
    async def test_get_user_by_username_found(self, test_db_session):
        """按用户名查找：存在"""
        u = await user_service.create_user(test_db_session, username="findme", password="Pass123")
        found = await user_service.get_user_by_username(test_db_session, "findme")
        assert found is not None
        assert found.public_id == u.public_id

    @pytest.mark.anyio
    async def test_get_user_by_username_not_found(self, test_db_session):
        """按用户名查找：不存在返回 None"""
        found = await user_service.get_user_by_username(test_db_session, "nobody")
        assert found is None

    @pytest.mark.anyio
    async def test_get_user_by_public_id(self, test_db_session):
        """按 public_id 查找"""
        u = await user_service.create_user(test_db_session, username="pidtest", password="Pass123")
        found = await user_service.get_user_by_public_id(test_db_session, u.public_id)
        assert found is not None
        assert found.username == "pidtest"

    @pytest.mark.anyio
    async def test_get_user_or_raise_not_found(self, test_db_session):
        """get_user_or_raise: 不存在应抛异常"""
        with pytest.raises(UserNotFoundError):
            await user_service.get_user_or_raise(test_db_session, "nonexistent-id")


# ==================== 认证测试 ====================

class TestAuthenticateUser:
    """authenticate_user 测试"""

    @pytest.mark.anyio
    async def test_authenticate_success(self, test_db_session):
        """正确凭据应返回 tokens 和 user"""
        await user_service.create_user(test_db_session, username="authuser", password="CorrectPass1")
        result = await user_service.authenticate_user(test_db_session, "authuser", "CorrectPass1")
        assert "access_token" in result
        assert "refresh_token" in result
        assert "expires_in" in result
        assert result["user"].username == "authuser"

    @pytest.mark.anyio
    async def test_authenticate_wrong_password(self, test_db_session):
        """错误密码应抛出异常"""
        await user_service.create_user(test_db_session, username="authuser2", password="CorrectPass1")
        with pytest.raises(InvalidCredentialsError):
            await user_service.authenticate_user(test_db_session, "authuser2", "WrongPass")

    @pytest.mark.anyio
    async def test_authenticate_user_not_found(self, test_db_session):
        """不存在的用户应抛出异常"""
        with pytest.raises(InvalidCredentialsError):
            await user_service.authenticate_user(test_db_session, "nobody", "anypass")

    @pytest.mark.anyio
    async def test_authenticate_disabled_user(self, test_db_session):
        """已禁用的用户应抛出异常"""
        u = await user_service.create_user(test_db_session, username="disabled", password="Pass123")
        await u.disable()
        test_db_session.add(u)
        await test_db_session.commit()
        with pytest.raises(AccountDisabledError):
            await user_service.authenticate_user(test_db_session, "disabled", "Pass123")

    @pytest.mark.anyio
    async def test_authenticate_updates_last_login(self, test_db_session):
        """登录成功应更新 last_login_at"""
        u = await user_service.create_user(test_db_session, username="lastlogin", password="Pass123")
        assert u.last_login_at is None
        result = await user_service.authenticate_user(test_db_session, "lastlogin", "Pass123")
        # authenticate_user 返回的 user 对象应有 last_login_at
        assert result["user"].last_login_at is not None


# ==================== 资料管理测试 ====================

class TestUpdateProfile:
    """资料更新测试"""

    @pytest.mark.anyio
    async def test_update_profile_email(self, test_db_session):
        """更新邮箱"""
        u = await user_service.create_user(test_db_session, username="profile1", password="Pass123")
        updated = await user_service.update_user_profile(test_db_session, u.public_id, email="new@email.com")
        assert updated.email == "new@email.com"

    @pytest.mark.anyio
    async def test_update_profile_full_name(self, test_db_session):
        """更新姓名（映射到 nickname）"""
        u = await user_service.create_user(test_db_session, username="profile2", password="Pass123")
        updated = await user_service.update_user_profile(test_db_session, u.public_id, full_name="新名字")
        assert updated.nickname == "新名字"

    @pytest.mark.anyio
    async def test_update_profile_partial(self, test_db_session):
        """部分更新：只改邮箱，不改姓名"""
        u = await user_service.create_user(test_db_session, username="profile3", password="Pass123", full_name="原始名")
        updated = await user_service.update_user_profile(test_db_session, u.public_id, email="new@email.com")
        assert updated.email == "new@email.com"
        assert updated.nickname == "原始名"


# ==================== 密码管理测试 ====================

class TestUpdatePassword:
    """密码修改测试"""

    @pytest.mark.anyio
    async def test_update_password_success(self, test_db_session):
        """正确旧密码时应成功修改"""
        u = await user_service.create_user(test_db_session, username="pwuser", password="OldPass123")
        updated = await user_service.update_user_password(test_db_session, u.public_id, "OldPass123", "NewPass456")
        assert security.verify_password("NewPass456", updated.password_hash)

    @pytest.mark.anyio
    async def test_update_password_wrong_old(self, test_db_session):
        """错误旧密码应抛出异常"""
        u = await user_service.create_user(test_db_session, username="pwuser2", password="OldPass123")
        with pytest.raises(OldPasswordIncorrectError):
            await user_service.update_user_password(test_db_session, u.public_id, "WrongOld", "NewPass456")

    @pytest.mark.anyio
    async def test_update_password_user_not_found(self, test_db_session):
        """不存在的用户应抛出异常"""
        with pytest.raises(UserNotFoundError):
            await user_service.update_user_password(test_db_session, "nonexistent", "old", "new")


# ==================== 默认管理员引导测试 ====================

class TestEnsureDefaultAdmin:
    """ensure_default_admin 测试"""

    @pytest.mark.anyio
    async def test_creates_admin_when_empty(self, test_db_session, monkeypatch):
        """数据库为空时应创建默认管理员"""
        monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "admin")
        monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "admin123")
        monkeypatch.setenv("DEFAULT_ADMIN_EMAIL", "admin@example.com")

        import importlib
        from backend.app.core import config
        importlib.reload(config)

        await user_service.ensure_default_admin(test_db_session)
        admin = await user_service.get_user_by_username(test_db_session, "admin")
        assert admin is not None
        assert admin.is_superuser is True

    @pytest.mark.anyio
    async def test_skips_when_admin_exists(self, test_db_session, monkeypatch):
        """已有管理员时应跳过创建"""
        monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "admin")
        monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "admin123")

        import importlib
        from backend.app.core import config
        importlib.reload(config)

        # 先手动创建一个管理员
        from uuid import uuid4
        from backend.app.models.user import User
        admin = User(
            public_id=str(uuid4()),
            username="existing_admin",
            password_hash=security.hash_password("pass"),
            is_superuser=True,
            sort_order=0,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        test_db_session.add(admin)
        await test_db_session.commit()

        # 调用 ensure_default_admin 不应创建新管理员
        await user_service.ensure_default_admin(test_db_session)
        # 确认 admin 用户没有被创建
        default_admin = await user_service.get_user_by_username(test_db_session, "admin")
        assert default_admin is None
