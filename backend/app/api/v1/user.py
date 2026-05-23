"""
用户认证 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime

from backend.app.schemas.user import UserCreate, UserLogin, LoginResponse, UserResponse, UserUpdate, Token
from backend.app.api.deps import get_db, get_current_user_required, get_admin_user
from backend.app.core.security import create_access_token, verify_token, hash_password, verify_password
from sqlalchemy import select

router = APIRouter()


@router.post("/users/register", response_model=UserResponse, summary="用户注册")
async def register_user(
    user_data: UserCreate,
    db = Depends(get_db)
):
    """
    注册新用户

    - **username**: 用户名
    - **password**: 密码
    - **email**: 邮箱（可选）
    """
    from backend.app.models.user import User

    # 检查用户名是否已存在
    stmt = select(User).where(User.username == user_data.username)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )

    # 创建新用户
    new_user = User(
        username=user_data.username,
        hashed_password=hash_password(user_data.password),  # 使用 hashed_password
        email=user_data.email,
        full_name=user_data.full_name
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        email=new_user.email,
        full_name=new_user.full_name,
        is_active=new_user.is_active,
        is_admin=new_user.is_admin,
        created_at=new_user.created_at
    )


@router.post("/users/login", response_model=LoginResponse, summary="用户登录")
async def login_user(
    login_data: UserLogin,
    db = Depends(get_db)
):
    """
    用户登录

    - **username**: 用户名
    - **password**: 密码
    """
    from backend.app.models.user import User
    from backend.app.core.config import settings

    # 查询用户
    stmt = select(User).where(User.username == login_data.username)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="账户已被禁用"
        )

    # 更新最后登录时间
    user.last_login = datetime.utcnow()
    await db.commit()

    # 生成 Token
    access_token = create_access_token(user_id=user.id, username=user.username)

    return LoginResponse(
        success=True,
        message="登录成功",
        token=Token(access_token=access_token, expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60),
        user=UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_admin=user.is_admin
        )
    )


@router.get("/users/me", response_model=UserResponse, summary="获取当前用户信息")
async def get_current_user_info(
    user = Depends(get_current_user_required)
):
    """
    获取当前登录用户信息
    """
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_admin=user.is_admin
    )


@router.put("/users/me", response_model=UserResponse, summary="更新用户信息")
async def update_user_info(
    update_data: UserUpdate,
    user = Depends(get_current_user_required),
    db = Depends(get_db)
):
    """
    更新当前用户信息

    - **email**: 邮箱
    - **full_name**: 全名
    - **password**: 新密码
    """
    # TODO: 实现更新用户信息逻辑
    return UserResponse(
        id=user.id,
        username=user.username,
        email=update_data.email,
        full_name=update_data.full_name,
        is_active=user.is_active
    )