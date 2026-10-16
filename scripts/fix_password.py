"""
修复用户密码哈希
生成正确的 bcrypt 哈希并更新数据库
"""
import asyncio
import sys
sys.path.insert(0, '.')

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import bcrypt

# 数据库配置
DATABASE_URL = "mysql+aiomysql://root:Djx3861599!@localhost:3306/article_analysis_v3"


def hash_password(password: str) -> str:
    """使用 bcrypt 直接哈希密码"""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


async def fix_user_password():
    """修复用户密码"""
    # 创建异步引擎
    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 生成正确的密码哈希
    password = "admin123"  # 新密码
    hashed_password = hash_password(password)
    print(f"生成的密码哈希: {hashed_password}")

    async with async_session() as session:
        # 查看当前用户
        result = await session.execute(text("SELECT id, username, hashed_password FROM users"))
        users = result.fetchall()
        print(f"\n当前用户列表:")
        for user in users:
            print(f"  ID: {user[0]}, Username: {user[1]}, Hash: {user[2][:30]}..." if len(str(user[2])) > 30 else f"  ID: {user[0]}, Username: {user[1]}, Hash: {user[2]}")

        # 更新所有用户的密码哈希
        await session.execute(
            text("UPDATE users SET hashed_password = :hash"),
            {"hash": hashed_password}
        )
        await session.commit()
        print(f"\n已更新所有用户的密码为: {password}")

        # 验证更新
        result = await session.execute(text("SELECT id, username, hashed_password FROM users"))
        users = result.fetchall()
        print(f"\n更新后的用户列表:")
        for user in users:
            print(f"  ID: {user[0]}, Username: {user[1]}, Hash: {user[2][:50]}...")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(fix_user_password())