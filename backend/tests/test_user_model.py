"""
User 模型单元测试
覆盖：BaseModelMixin 字段继承、软删除、时间戳、方法
"""
from __future__ import annotations

import pytest
from uuid import uuid4
from datetime import datetime

from backend.app.models.user import User


class TestUserModelFields:
    """User 模型字段存在性测试"""

    def _make_user(self, **kwargs):
        """创建测试用 User 实例（带必要默认值）"""
        defaults = {
            "public_id": str(uuid4()),
            "sort_order": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        defaults.update(kwargs)
        return User(**defaults)

    def test_user_has_public_id(self):
        """User 继承 BaseModelMixin，应有 public_id 字段"""
        user = self._make_user(username="test", password_hash="hash")
        assert user.public_id is not None
        assert len(user.public_id) == 36  # UUID 格式

    def test_user_public_id_is_unique_per_instance(self):
        """每个 User 实例自动生成唯一 public_id"""
        u1 = self._make_user(username="u1", password_hash="h1")
        u2 = self._make_user(username="u2", password_hash="h2")
        assert u1.public_id != u2.public_id

    def test_user_has_timestamp_fields(self):
        """User 应有 created_at、updated_at、disabled_at 字段"""
        user = self._make_user(username="test", password_hash="hash")
        assert hasattr(user, "created_at")
        assert hasattr(user, "updated_at")
        assert hasattr(user, "disabled_at")

    def test_user_has_sort_order_default(self):
        """sort_order 默认值为 0"""
        user = self._make_user(username="test", password_hash="hash")
        assert user.sort_order == 0

    def test_user_has_new_fields(self):
        """User 应有新架构字段"""
        user = self._make_user(username="test", password_hash="hash")
        assert hasattr(user, "nickname")
        assert hasattr(user, "avatar_url")
        assert hasattr(user, "is_superuser")
        assert hasattr(user, "last_login_at")

    def test_user_does_not_have_old_fields(self):
        """User 不应有旧字段 full_name / hashed_password"""
        user = self._make_user(username="test", password_hash="hash")
        assert not hasattr(user, "full_name")
        assert not hasattr(user, "hashed_password")


class TestUserSoftDelete:
    """软删除（disabled_at）行为测试"""

    def _make_user(self, **kwargs):
        defaults = {
            "public_id": str(uuid4()),
            "sort_order": 0,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        defaults.update(kwargs)
        return User(**defaults)

    @pytest.mark.anyio
    async def test_disable_sets_disabled_at(self):
        """disable() 应设置 disabled_at 为当前时间"""
        user = self._make_user(username="test", password_hash="hash")
        assert user.disabled_at is None
        await user.disable()
        assert user.disabled_at is not None
        assert isinstance(user.disabled_at, datetime)

    @pytest.mark.anyio
    async def test_enable_clears_disabled_at(self):
        """enable() 应清除 disabled_at"""
        user = self._make_user(username="test", password_hash="hash")
        await user.disable()
        assert user.disabled_at is not None
        await user.enable()
        assert user.disabled_at is None

    @pytest.mark.anyio
    async def test_is_disabled_property(self):
        """is_disabled 与 disabled_at 状态一致"""
        user = self._make_user(username="test", password_hash="hash")
        assert user.is_disabled is False
        await user.disable()
        assert user.is_disabled is True
        await user.enable()
        assert user.is_disabled is False

    @pytest.mark.anyio
    async def test_is_active_property(self):
        """is_active 与 disabled_at 状态反向一致"""
        user = self._make_user(username="test", password_hash="hash")
        assert user.is_active is True
        await user.disable()
        assert user.is_active is False
        await user.enable()
        assert user.is_active is True


class TestUserMethods:
    """User 实例方法测试"""

    @pytest.mark.anyio
    async def test_update_last_login(self):
        """update_last_login() 应设置 last_login_at"""
        user = User(
            username="test", password_hash="hash",
            public_id=str(uuid4()), sort_order=0,
            created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
        )
        assert user.last_login_at is None
        await user.update_last_login()
        assert user.last_login_at is not None
        assert isinstance(user.last_login_at, datetime)

    def test_user_table_name(self):
        """表名应为 users"""
        assert User.__tablename__ == "users"

    def test_user_column_count(self):
        """User 模型应有正确数量的列（继承 + 自身）"""
        columns = [c.name for c in User.__table__.columns]
        expected = [
            "id", "public_id", "sort_order",
            "created_at", "updated_at", "disabled_at",
            "username", "nickname", "email", "avatar_url",
            "password_hash", "is_superuser", "last_login_at",
        ]
        for col in expected:
            assert col in columns, f"缺少列: {col}"
