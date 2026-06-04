"""
用户认证 API 路由
Router → Service → Model 三层架构
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import get_db
from backend.app.schemas.user import (
    UserCreate, UserLogin, UserResponse, LoginResponse,
    TokenRefreshRequest, TokenRefreshResponse,
    UserProfileUpdate, UserPasswordUpdate,
)
from backend.app.api.deps_user import get_current_user_required, get_admin_user
from backend.app.core.jwt_tools import create_access_token_from_refresh_token
from backend.app.services import user_service
from backend.app.core.user_exceptions import UserServiceError
from backend.app.schemas.user import AdminUserUpdate, UserAvatarUpdate
from backend.app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _user_to_response(user) -> UserResponse:
    """User 模型 → UserResponse 的辅助转换"""
    return UserResponse(
        public_id=user.public_id,
        username=user.username,
        nickname=user.nickname,
        email=user.email,
        avatar_url=user.avatar_url,
        is_superuser=user.is_superuser,
        disabled=user.is_disabled,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def _raise_as_http(exc: Exception) -> HTTPException:
    """将 Service 层异常转换为 HTTPException"""
    if isinstance(exc, UserServiceError):
        return HTTPException(
            status_code=exc.status_code if hasattr(exc, 'status_code') else status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=exc.detail if hasattr(exc, 'detail') else str(exc),
        )
    if isinstance(exc, ValueError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    logger.exception("未预期的服务层异常")
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="服务器内部错误")


# 注册功能暂时关闭
# @router.post("/users/register", response_model=UserResponse, summary="用户注册")
# async def register_user(
#     user_data: UserCreate,
#     db: AsyncSession = Depends(get_db),
# ):
#     """注册新用户"""
#     try:
#         user = await user_service.create_user(
#             db,
#             username=user_data.username,
#             password=user_data.password,
#             email=user_data.email,
#             full_name=user_data.full_name,
#         )
#         return UserResponse(
#             public_id=user.public_id,
#             username=user.username,
#             nickname=user.nickname,
#             email=user.email,
#             avatar_url=user.avatar_url,
#             is_superuser=user.is_superuser,
#             disabled=user.is_disabled,
#             created_at=user.created_at,
#             last_login_at=user.last_login_at,
#         )
#     except UserServiceError as exc:
#         raise _raise_as_http(exc)
#     except ValueError as exc:
#         raise _raise_as_http(exc)


@router.post("/users/login", response_model=LoginResponse, summary="用户登录")
async def login_user(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """用户登录，返回双令牌"""
    try:
        result = await user_service.authenticate_user(
            db,
            username=login_data.username,
            password=login_data.password,
        )
        user = result["user"]
        return LoginResponse(
            success=True,
            message="登录成功",
            access_token=str(result["access_token"]),
            refresh_token=str(result["refresh_token"]),
            expires_in=int(result["expires_in"]),
            user=UserResponse(
                public_id=user.public_id,
                username=user.username,
                nickname=user.nickname,
                email=user.email,
                avatar_url=user.avatar_url,
                is_superuser=user.is_superuser,
                disabled=user.is_disabled,
                created_at=user.created_at,
                last_login_at=user.last_login_at,
            ),
        )
    except UserServiceError as exc:
        raise _raise_as_http(exc)


@router.post("/users/refresh", response_model=TokenRefreshResponse, summary="刷新 Access Token")
async def refresh_token(
    req: TokenRefreshRequest,
):
    """使用 refresh token 换取新的 access token"""
    try:
        tokens = await create_access_token_from_refresh_token(req.refresh_token)
        return TokenRefreshResponse(
            access_token=str(tokens["access_token"]),
            expires_in=int(tokens["expires_in"]),
        )
    except (ValueError, Exception) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token 无效或已过期",
        )


@router.get("/users/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_current_user_info(
    user=Depends(get_current_user_required),
):
    """获取当前登录用户信息"""
    return UserResponse(
        public_id=user.public_id,
        username=user.username,
        nickname=user.nickname,
        email=user.email,
        avatar_url=user.avatar_url,
        is_superuser=user.is_superuser,
        disabled=user.is_disabled,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.put("/users/me/profile", response_model=UserResponse, summary="更新当前用户资料")
async def update_current_user_profile(
    update_data: UserProfileUpdate,
    user=Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """更新当前登录用户的邮箱和姓名"""
    try:
        updated = await user_service.update_user_profile(
            db,
            public_id=user.public_id,
            email=update_data.email,
            full_name=update_data.full_name,
        )
        return UserResponse(
            public_id=updated.public_id,
            username=updated.username,
            nickname=updated.nickname,
            email=updated.email,
            avatar_url=updated.avatar_url,
            is_superuser=updated.is_superuser,
            disabled=updated.is_disabled,
            created_at=updated.created_at,
            last_login_at=updated.last_login_at,
        )
    except UserServiceError as exc:
        raise _raise_as_http(exc)


@router.put("/users/me/password", response_model=UserResponse, summary="修改当前用户密码")
async def update_current_user_password(
    pw_data: UserPasswordUpdate,
    user=Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """修改当前登录用户密码（需验证旧密码）"""
    try:
        updated = await user_service.update_user_password(
            db,
            public_id=user.public_id,
            old_password=pw_data.old_password,
            new_password=pw_data.new_password,
        )
        return UserResponse(
            public_id=updated.public_id,
            username=updated.username,
            nickname=updated.nickname,
            email=updated.email,
            avatar_url=updated.avatar_url,
            is_superuser=updated.is_superuser,
            disabled=updated.is_disabled,
            created_at=updated.created_at,
            last_login_at=updated.last_login_at,
        )
    except UserServiceError as exc:
        raise _raise_as_http(exc)
    except ValueError as exc:
        raise _raise_as_http(exc)


# ==================== 管理端点（需管理员权限） ====================


@router.get("/users/", response_model=list[UserResponse], summary="获取用户列表")
async def list_all_users(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员获取全部用户列表"""
    users = await user_service.list_users(db)
    return [_user_to_response(u) for u in users]


@router.get("/users/{public_id}", response_model=UserResponse, summary="获取用户详情")
async def get_user_detail(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员获取任意用户详情"""
    try:
        user = await user_service.get_user_or_raise(db, public_id)
        return _user_to_response(user)
    except UserServiceError as exc:
        raise _raise_as_http(exc)


@router.post("/users/", response_model=UserResponse, status_code=status.HTTP_201_CREATED, summary="管理员创建用户")
async def admin_create_user(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员创建新用户"""
    try:
        user = await user_service.create_user(
            db,
            username=user_data.username,
            password=user_data.password,
            email=user_data.email,
            full_name=user_data.full_name,
        )
        return _user_to_response(user)
    except UserServiceError as exc:
        raise _raise_as_http(exc)
    except ValueError as exc:
        raise _raise_as_http(exc)


@router.put("/users/{public_id}", response_model=UserResponse, summary="管理员更新用户")
async def admin_update_user(
    public_id: str,
    update_data: AdminUserUpdate,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员更新任意用户的字段"""
    try:
        fields = update_data.model_dump(exclude_unset=True)
        updated = await user_service.update_user(db, public_id, **fields)
        return _user_to_response(updated)
    except UserServiceError as exc:
        raise _raise_as_http(exc)


@router.patch("/users/{public_id}/disable", response_model=UserResponse, summary="管理员禁用用户")
async def admin_disable_user(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员禁用用户（软删除）"""
    try:
        updated = await user_service.disable_user(db, public_id)
        return _user_to_response(updated)
    except UserServiceError as exc:
        raise _raise_as_http(exc)


@router.delete("/users/{public_id}", status_code=status.HTTP_204_NO_CONTENT, summary="管理员删除用户")
async def admin_delete_user(
    public_id: str,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员删除用户（硬删除）"""
    from fastapi.responses import Response
    try:
        await user_service.delete_user(db, public_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except UserServiceError as exc:
        raise _raise_as_http(exc)


# ==================== 头像端点 ====================


@router.put("/users/me/avatar", response_model=UserResponse, summary="更新当前用户头像")
async def update_current_user_avatar(
    avatar_data: UserAvatarUpdate,
    user=Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """更新当前登录用户头像地址"""
    try:
        updated = await user_service.update_current_user_avatar(
            db, user.public_id, avatar_data.avatar_url,
        )
        return _user_to_response(updated)
    except UserServiceError as exc:
        raise _raise_as_http(exc)


@router.post("/users/me/avatar/upload", response_model=UserResponse, summary="上传当前用户头像图片")
async def upload_current_user_avatar(
    file: UploadFile = File(..., description="头像图片（PNG/JPEG/JPG，≤5MB）"),
    user=Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """上传并裁剪当前登录用户头像"""
    try:
        import os
        output_dir = os.path.join(settings.BASE_DIR, "data", "oss")
        updated = await user_service.upload_current_user_avatar(
            db, user.public_id, file, output_dir,
        )
        return _user_to_response(updated)
    except UserServiceError as exc:
        raise _raise_as_http(exc)
    except ValueError as exc:
        raise _raise_as_http(exc)
