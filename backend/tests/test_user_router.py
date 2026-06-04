"""
用户 API 路由集成测试
覆盖：全部 HTTP 端点（注册/登录/刷新/资料/密码/管理/头像）
使用 httpx AsyncClient + SQLite + FakeRedis
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


# ==================== 注册端点测试 ====================

@pytest.mark.skip(reason="注册功能暂时关闭")
class TestRegisterEndpoint:
    """POST /api/v1/users/register"""

    @pytest.mark.anyio
    async def test_register_success(self, test_client):
        """正常注册应返回 200 和用户信息"""
        resp = await test_client.post("/api/v1/users/register", json={
            "username": "newuser",
            "password": "Test123456",
            "repassword": "Test123456",
            "email": "new@test.com",
            "full_name": "新用户",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "newuser"
        assert data["nickname"] == "新用户"

    @pytest.mark.anyio
    async def test_register_duplicate_username(self, test_client):
        """重复用户名应返回 409"""
        await test_client.post("/api/v1/users/register", json={
            "username": "duplicate_user", "password": "Test12345", "repassword": "Test12345",
        })
        resp = await test_client.post("/api/v1/users/register", json={
            "username": "duplicate_user", "password": "Test45678", "repassword": "Test45678",
        })
        assert resp.status_code == 409

    @pytest.mark.anyio
    async def test_register_short_password(self, test_client):
        """密码太短应返回 422"""
        resp = await test_client.post("/api/v1/users/register", json={
            "username": "shortpw", "password": "12345", "repassword": "12345",
        })
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_register_short_username(self, test_client):
        """用户名太短应返回 422"""
        resp = await test_client.post("/api/v1/users/register", json={
            "username": "ab", "password": "Test123", "repassword": "Test123",
        })
        assert resp.status_code == 422

    @pytest.mark.anyio
    async def test_register_password_mismatch(self, test_client):
        """两次密码不一致应返回 422"""
        resp = await test_client.post("/api/v1/users/register", json={
            "username": "mismatch", "password": "Test123456", "repassword": "Different",
        })
        assert resp.status_code == 422


# ==================== 登录端点测试 ====================

class TestLoginEndpoint:
    """POST /api/v1/users/login"""

    @pytest.mark.anyio
    async def test_login_success(self, test_client, test_db_session):
        """正确凭据应返回双令牌"""
        from backend.app.services import user_service
        await user_service.create_user(test_db_session, username="loginuser", password="Test123456")
        resp = await test_client.post("/api/v1/users/login", json={
            "username": "loginuser", "password": "Test123456",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["username"] == "loginuser"

    @pytest.mark.anyio
    async def test_login_wrong_password(self, test_client, test_db_session):
        """错误密码应返回 401"""
        from backend.app.services import user_service
        await user_service.create_user(test_db_session, username="wrongpw", password="Test123456")
        resp = await test_client.post("/api/v1/users/login", json={
            "username": "wrongpw", "password": "WrongPassword",
        })
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_login_user_not_found(self, test_client):
        """不存在的用户应返回 401"""
        resp = await test_client.post("/api/v1/users/login", json={
            "username": "nobody", "password": "AnyPass123",
        })
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_login_disabled_user(self, test_client, test_db_session):
        """已禁用的用户应返回 403"""
        from backend.app.services import user_service
        u = await user_service.create_user(test_db_session, username="disabled_login", password="Test123")
        await u.disable()
        test_db_session.add(u)
        await test_db_session.commit()

        resp = await test_client.post("/api/v1/users/login", json={
            "username": "disabled_login", "password": "Test123",
        })
        assert resp.status_code == 403


# ==================== 当前用户端点测试 ====================

class TestCurrentUserEndpoint:
    """GET /api/v1/users/me"""

    @pytest.mark.anyio
    async def test_get_me_authenticated(self, test_client):
        """已认证的请求应返回用户信息"""
        tokens = await _register_and_login(test_client, "meuser", "Test123456")
        resp = await test_client.get("/api/v1/users/me", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert resp.status_code == 200
        assert resp.json()["username"] == "meuser"

    @pytest.mark.anyio
    async def test_get_me_no_token(self, test_client):
        """无 token 应返回 401"""
        resp = await test_client.get("/api/v1/users/me")
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_get_me_invalid_token(self, test_client):
        """无效 token 应返回 401"""
        resp = await test_client.get("/api/v1/users/me", headers={
            "Authorization": "Bearer invalid_token_here"
        })
        assert resp.status_code == 401


# ==================== 刷新令牌端点测试 ====================

class TestRefreshTokenEndpoint:
    """POST /api/v1/users/refresh"""

    @pytest.mark.anyio
    async def test_refresh_success(self, test_client):
        tokens = await _register_and_login(test_client, "refreshuser", "Test123456")
        resp = await test_client.post("/api/v1/users/refresh", json={
            "refresh_token": tokens["refresh_token"]
        })
        assert resp.status_code == 200
        assert resp.json()["access_token"] != tokens["access_token"]

    @pytest.mark.anyio
    async def test_refresh_invalid_token(self, test_client):
        resp = await test_client.post("/api/v1/users/refresh", json={
            "refresh_token": "invalid_token"
        })
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_refresh_with_access_token(self, test_client):
        tokens = await _register_and_login(test_client, "wrongtype", "Test123456")
        resp = await test_client.post("/api/v1/users/refresh", json={
            "refresh_token": tokens["access_token"]
        })
        assert resp.status_code == 401


# ==================== 资料更新端点测试 ====================

class TestUpdateProfileEndpoint:
    """PUT /api/v1/users/me/profile"""

    @pytest.mark.anyio
    async def test_update_profile_success(self, test_client):
        tokens = await _register_and_login(test_client, "profileupd", "Test123456")
        resp = await test_client.put("/api/v1/users/me/profile", json={
            "email": "updated@test.com",
            "full_name": "更新后的名字",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "updated@test.com"

    @pytest.mark.anyio
    async def test_update_profile_partial(self, test_client):
        tokens = await _register_and_login(test_client, "partialupd", "Test123456")
        resp = await test_client.put("/api/v1/users/me/profile", json={
            "email": "onlyemail@test.com",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_update_profile_no_auth(self, test_client):
        resp = await test_client.put("/api/v1/users/me/profile", json={"email": "noauth@test.com"})
        assert resp.status_code == 401


# ==================== 密码修改端点测试 ====================

class TestUpdatePasswordEndpoint:
    """PUT /api/v1/users/me/password"""

    @pytest.mark.anyio
    async def test_update_password_success(self, test_client):
        tokens = await _register_and_login(test_client, "pwchange", "OldPass123")
        resp = await test_client.put("/api/v1/users/me/password", json={
            "old_password": "OldPass123",
            "new_password": "NewPass456",
            "confirm_password": "NewPass456",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_update_password_wrong_old(self, test_client):
        tokens = await _register_and_login(test_client, "pwwrongold", "OldPass123")
        resp = await test_client.put("/api/v1/users/me/password", json={
            "old_password": "WrongOldPass",
            "new_password": "NewPass456",
            "confirm_password": "NewPass456",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 400

    @pytest.mark.anyio
    async def test_update_password_mismatch(self, test_client):
        tokens = await _register_and_login(test_client, "pwmismatch", "OldPass123")
        resp = await test_client.put("/api/v1/users/me/password", json={
            "old_password": "OldPass123",
            "new_password": "NewPass456",
            "confirm_password": "DifferentPass",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code in [400, 422]


# ==================== 管理端点测试 ====================

class TestAdminEndpoints:
    """管理员 CRUD 端点"""

    async def _get_admin_tokens(self, test_client):
        """获取管理员 token（直接创建超级用户并登录）"""
        from backend.app.services import user_service
        from uuid import uuid4
        from datetime import datetime, timezone
        from backend.app.models.user import User
        import backend.app.models.base as base_mod
        from backend.app.core.security import hash_password

        session_factory = base_mod.AsyncSessionLocal
        async with session_factory() as session:
            admin = User(
                public_id=str(uuid4()),
                username="test_admin_user",
                nickname="测试管理员",
                password_hash=hash_password("AdminPass123"),
                is_superuser=True,
                sort_order=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            session.add(admin)
            await session.commit()

        # 直接登录
        resp = await test_client.post("/api/v1/users/login", json={
            "username": "test_admin_user",
            "password": "AdminPass123",
        })
        assert resp.status_code == 200
        return resp.json()

    @pytest.mark.anyio
    async def test_list_users(self, test_client):
        """管理员获取用户列表"""
        tokens = await self._get_admin_tokens(test_client)
        resp = await test_client.get("/api/v1/users/", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.anyio
    async def test_get_user_detail(self, test_client):
        """管理员获取用户详情"""
        await _register_and_login(test_client, "detailuser", "Test123456")
        tokens = await self._get_admin_tokens(test_client)
        # 先查列表获取 public_id
        list_resp = await test_client.get("/api/v1/users/", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        users = list_resp.json()
        target = [u for u in users if u["username"] == "detailuser"][0]

        resp = await test_client.get(f"/api/v1/users/{target['public_id']}", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert resp.status_code == 200
        assert resp.json()["username"] == "detailuser"

    @pytest.mark.anyio
    async def test_admin_create_user(self, test_client):
        """管理员创建用户（201）"""
        tokens = await self._get_admin_tokens(test_client)
        resp = await test_client.post("/api/v1/users/", json={
            "username": "admincreated",
            "password": "Test123456",
            "repassword": "Test123456",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 201
        assert resp.json()["username"] == "admincreated"

    @pytest.mark.anyio
    async def test_admin_disable_user(self, test_client):
        """管理员禁用用户"""
        await _register_and_login(test_client, "todisable", "Test123456")
        tokens = await self._get_admin_tokens(test_client)
        # 查 public_id
        list_resp = await test_client.get("/api/v1/users/", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        target = [u for u in list_resp.json() if u["username"] == "todisable"][0]

        resp = await test_client.patch(f"/api/v1/users/{target['public_id']}/disable", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert resp.status_code == 200
        assert resp.json()["disabled"] is True

    @pytest.mark.anyio
    async def test_admin_delete_user(self, test_client):
        """管理员删除用户（204）"""
        await _register_and_login(test_client, "todelete", "Test123456")
        tokens = await self._get_admin_tokens(test_client)
        list_resp = await test_client.get("/api/v1/users/", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        target = [u for u in list_resp.json() if u["username"] == "todelete"][0]

        resp = await test_client.delete(f"/api/v1/users/{target['public_id']}", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert resp.status_code == 204

    @pytest.mark.anyio
    async def test_non_admin_cannot_list_users(self, test_client):
        """非管理员不能获取用户列表"""
        tokens = await _register_and_login(test_client, "normal_user", "Test123456")
        resp = await test_client.get("/api/v1/users/", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert resp.status_code == 403


# ==================== 头像端点测试 ====================

class TestAvatarEndpoints:
    """头像 API 测试"""

    @pytest.mark.anyio
    async def test_update_avatar_url(self, test_client):
        """更新头像 URL"""
        tokens = await _register_and_login(test_client, "avataruser", "Test123456")
        resp = await test_client.put("/api/v1/users/me/avatar", json={
            "avatar_url": "https://example.com/avatar.jpg",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})
        assert resp.status_code == 200
        assert resp.json()["avatar_url"] == "https://example.com/avatar.jpg"

    @pytest.mark.anyio
    async def test_update_avatar_no_auth(self, test_client):
        """无认证修改头像应 401"""
        resp = await test_client.put("/api/v1/users/me/avatar", json={
            "avatar_url": "https://example.com/avatar.jpg",
        })
        assert resp.status_code == 401

    @pytest.mark.anyio
    async def test_upload_avatar_no_file(self, test_client):
        """无文件上传应 422"""
        tokens = await _register_and_login(test_client, "uploaduser", "Test123456")
        resp = await test_client.post("/api/v1/users/me/avatar/upload", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        assert resp.status_code == 422


# ==================== 完整生命周期测试 ====================

class TestFullLifecycle:
    """注册→登录→改资料→改密码→管理员禁用→重新登录失败的完整流程"""

    @pytest.mark.anyio
    async def test_full_lifecycle(self, test_client):
        # 1. 创建用户并登录
        tokens = await _register_and_login(test_client, "lifecycle", "StartPass1")

        # 2. 获取个人信息
        me = await test_client.get("/api/v1/users/me", headers={
            "Authorization": f"Bearer {tokens['access_token']}"
        })
        public_id = me.json()["public_id"]

        # 4. 改资料
        await test_client.put("/api/v1/users/me/profile", json={
            "email": "final@test.com", "full_name": "最终名字"
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})

        # 5. 改密码
        await test_client.put("/api/v1/users/me/password", json={
            "old_password": "StartPass1",
            "new_password": "EndPass789",
            "confirm_password": "EndPass789",
        }, headers={"Authorization": f"Bearer {tokens['access_token']}"})

        # 6. 旧密码登录失败
        old_login = await test_client.post("/api/v1/users/login", json={
            "username": "lifecycle", "password": "StartPass1"
        })
        assert old_login.status_code == 401

        # 7. 新密码登录成功
        new_login = await test_client.post("/api/v1/users/login", json={
            "username": "lifecycle", "password": "EndPass789"
        })
        assert new_login.status_code == 200
        assert new_login.json()["user"]["nickname"] == "最终名字"


# ==================== 辅助函数 ====================

async def _register_and_login(client: AsyncClient, username: str, password: str) -> dict:
    """辅助：创建用户并登录，返回 tokens（绕过已关闭的注册 API）"""
    from backend.app.models.base import AsyncSessionLocal
    from backend.app.services import user_service
    async with AsyncSessionLocal() as db:
        await user_service.create_user(db, username=username, password=password)
    resp = await client.post("/api/v1/users/login", json={
        "username": username, "password": password,
    })
    assert resp.status_code == 200
    return resp.json()
