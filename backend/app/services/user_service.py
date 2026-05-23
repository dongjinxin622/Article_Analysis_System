"""
用户业务逻辑层
全部用户 CRUD + 认证逻辑，Router 不直接操作数据库
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.user import User
from backend.app.core.security import hash_password, verify_password
from backend.app.core.jwt_tools import create_login_tokens
from backend.app.core.config import settings


# ==================== 查询函数 ====================

async def get_user_by_username(db: AsyncSession, username: str) -> User | None:
    """按用户名查询用户"""
    stmt = select(User).where(User.username == username)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    """按邮箱查询用户"""
    if email is None:
        return None
    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_public_id(db: AsyncSession, public_id: str) -> User | None:
    """按 public_id 查询用户"""
    stmt = select(User).where(User.public_id == public_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_or_raise(db: AsyncSession, public_id: str) -> User:
    """按 public_id 获取用户，不存在则抛异常"""
    from backend.app.core.user_exceptions import UserNotFoundError
    user = await get_user_by_public_id(db, public_id)
    if user is None:
        raise UserNotFoundError("用户不存在")
    return user


# ==================== 唯一性校验 ====================

async def ensure_unique_username(db: AsyncSession, username: str, current_user_id: int | None = None) -> None:
    """校验用户名唯一"""
    from backend.app.core.user_exceptions import UserNameConflictError
    existing = await get_user_by_username(db, username)
    if existing is None:
        return
    if current_user_id is not None and existing.id == current_user_id:
        return
    raise UserNameConflictError("用户名已存在")


async def ensure_unique_email(db: AsyncSession, email: str | None, current_user_id: int | None = None) -> None:
    """校验邮箱唯一（空邮箱跳过检查）"""
    from backend.app.core.user_exceptions import UserEmailConflictError
    if email is None:
        return
    existing = await get_user_by_email(db, email)
    if existing is None:
        return
    if current_user_id is not None and existing.id == current_user_id:
        return
    raise UserEmailConflictError("邮箱已被使用")


# ==================== 创建与认证 ====================

async def create_user(db: AsyncSession, username: str, password: str,
                      email: str | None = None, full_name: str | None = None) -> User:
    """创建新用户（含唯一性检查 + 密码哈希）"""
    await ensure_unique_username(db, username)
    await ensure_unique_email(db, email)

    now = datetime.now(timezone.utc)
    user = User(
        public_id=str(uuid4()),
        username=username,
        nickname=full_name,
        email=email,
        password_hash=hash_password(password),
        is_superuser=False,
        sort_order=0,
        created_at=now,
        updated_at=now,
        disabled_at=None,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, username: str, password: str) -> dict:
    """验证用户凭据并签发令牌

    Returns:
        {"access_token": str, "refresh_token": str, "expires_in": int, "user": User}
    """
    from backend.app.core.user_exceptions import InvalidCredentialsError, AccountDisabledError

    user = await get_user_by_username(db, username)
    if user is None:
        raise InvalidCredentialsError("用户名或密码错误")

    if user.is_disabled:
        raise AccountDisabledError("账户已被禁用")

    if not verify_password(password, user.password_hash):
        raise InvalidCredentialsError("用户名或密码错误")

    # 签发令牌
    tokens = await create_login_tokens(public_id=user.public_id, username=user.username)

    # 更新最后登录时间
    await user.update_last_login()
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {**tokens, "user": user}


# ==================== 资料管理 ====================

async def get_current_user(db: AsyncSession, public_id: str) -> User:
    """获取当前登录用户信息"""
    return await get_user_or_raise(db, public_id)


async def update_user_profile(db: AsyncSession, public_id: str,
                               email: str | None = None, full_name: str | None = None) -> User:
    """更新当前用户资料（email / full_name）"""
    user = await get_user_or_raise(db, public_id)

    if email is not None:
        await ensure_unique_email(db, email, current_user_id=user.id)
        user.email = email
    if full_name is not None:
        user.nickname = full_name

    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user_password(db: AsyncSession, public_id: str,
                                old_password: str, new_password: str) -> User:
    """修改当前用户密码（需验证旧密码）"""
    from backend.app.core.user_exceptions import OldPasswordIncorrectError

    user = await get_user_or_raise(db, public_id)

    if not verify_password(old_password, user.password_hash):
        raise OldPasswordIncorrectError("当前密码不正确")

    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# ==================== 管理员引导 ====================

async def ensure_default_admin(db: AsyncSession) -> None:
    """确保数据库中存在默认管理员账号"""
    import logging
    logger = logging.getLogger(__name__)

    # 检查是否已有管理员
    stmt = select(func.count(User.id)).where(User.is_superuser.is_(True))
    result = await db.execute(stmt)
    admin_count = result.scalar()

    if admin_count > 0:
        logger.debug("已有 %d 个管理员账号，跳过默认管理员创建", admin_count)
        return

    # 检查是否已存在同名用户
    existing = await get_user_by_username(db, settings.DEFAULT_ADMIN_USERNAME)
    if existing is not None:
        existing.is_superuser = True
        existing.updated_at = datetime.now(timezone.utc)
        db.add(existing)
        await db.commit()
        logger.info("已将现有用户 '%s' 提升为管理员", settings.DEFAULT_ADMIN_USERNAME)
        return

    # 创建默认管理员
    now = datetime.now(timezone.utc)
    admin = User(
        public_id=str(uuid4()),
        username=settings.DEFAULT_ADMIN_USERNAME,
        nickname="系统管理员",
        email=settings.DEFAULT_ADMIN_EMAIL,
        password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        is_superuser=True,
        sort_order=0,
        created_at=now,
        updated_at=now,
        disabled_at=None,
    )
    db.add(admin)
    await db.commit()
    logger.info("已创建默认管理员: %s", settings.DEFAULT_ADMIN_USERNAME)


# ==================== 管理员 CRUD ====================

async def list_users(db: AsyncSession) -> list[User]:
    """获取全部用户列表（按 sort_order + id 排序）"""
    stmt = select(User).order_by(User.sort_order, User.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_user(
    db: AsyncSession,
    public_id: str,
    *,
    username: str | None = None,
    email: str | None = None,
    nickname: str | None = None,
    avatar_url: str | None = None,
    password: str | None = None,
    sort_order: int | None = None,
    is_superuser: bool | None = None,
    disabled_at: datetime | None = None,
) -> User:
    """管理员更新任意用户的字段"""
    user = await get_user_or_raise(db, public_id)

    if username is not None:
        await ensure_unique_username(db, username, current_user_id=user.id)
        user.username = username
    if email is not None:
        await ensure_unique_email(db, email, current_user_id=user.id)
        user.email = email
    if nickname is not None:
        user.nickname = nickname
    if avatar_url is not None:
        user.avatar_url = avatar_url
    if password is not None:
        user.password_hash = hash_password(password)
    if sort_order is not None:
        user.sort_order = sort_order
    if is_superuser is not None:
        user.is_superuser = is_superuser
    if disabled_at is not None:
        user.disabled_at = disabled_at

    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def disable_user(db: AsyncSession, public_id: str) -> User:
    """禁用用户（软删除）"""
    user = await get_user_or_raise(db, public_id)
    await user.disable()
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def delete_user(db: AsyncSession, public_id: str) -> None:
    """硬删除用户"""
    user = await get_user_or_raise(db, public_id)
    await db.delete(user)
    await db.commit()


# ==================== 头像管理 ====================

import io as _io
from PIL import Image as _Image
from fastapi import UploadFile

_ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/jpg"}
_AVATAR_SIZE = 256
_AVATAR_MAX_BYTES = 5 * 1024 * 1024


async def update_current_user_avatar(db: AsyncSession, public_id: str, avatar_url: str) -> User:
    """更新当前用户头像 URL"""
    user = await get_user_or_raise(db, public_id)
    user.avatar_url = avatar_url
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def upload_current_user_avatar(
    db: AsyncSession,
    public_id: str,
    file: UploadFile,
    output_dir: str,
) -> User:
    """接收上传的图片文件，中心裁剪为 1:1，缩放到 256×256，落盘后回写 avatar_url"""
    import os

    if file.content_type not in _ALLOWED_AVATAR_TYPES:
        raise ValueError("仅支持 PNG/JPEG/JPG 格式的图片")

    data = await file.read()
    if not data:
        raise ValueError("图片内容为空")
    if len(data) > _AVATAR_MAX_BYTES:
        raise ValueError("图片过大，最多支持 5MB")

    try:
        with _Image.open(_io.BytesIO(data)) as image:
            image.load()
            width, height = image.size
            side = min(width, height)
            left = (width - side) // 2
            top = (height - side) // 2
            cropped = image.crop((left, top, left + side, top + side))
            cropped = cropped.resize((_AVATAR_SIZE, _AVATAR_SIZE), _Image.Resampling.LANCZOS)
            if cropped.mode in ("RGBA", "LA"):
                background = _Image.new("RGB", cropped.size, (255, 255, 255))
                background.paste(cropped, mask=cropped.split()[-1])
                cropped = background
            elif cropped.mode != "RGB":
                cropped = cropped.convert("RGB")

            user = await get_user_or_raise(db, public_id)
            avatar_dir = os.path.join(output_dir, "avatars")
            os.makedirs(avatar_dir, exist_ok=True)
            timestamp = int(datetime.now(timezone.utc).timestamp())
            filename = f"{user.public_id}_{timestamp}.jpg"
            target_path = os.path.join(avatar_dir, filename)
            cropped.save(target_path, format="JPEG", quality=88, optimize=True)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"图片解析失败：{exc}") from exc

    user.avatar_url = f"/oss/avatars/{filename}"
    user.updated_at = datetime.now(timezone.utc)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user
