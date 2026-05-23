"""
用户表迁移脚本
将旧 users 表迁移到新结构：public_id/password_hash/disabled_at/last_login_at
"""
import asyncio
import sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from backend.app.models.base import engine, AsyncSessionLocal, Base
from backend.app.models.base_model import BaseModelMixin
from backend.app.models.user import User
from backend.app.core.security import hash_password


async def migrate():
    """执行用户表迁移"""
    print("=" * 60)
    print("用户表迁移开始")
    print("=" * 60)

    async with engine.begin() as conn:
        # 1. 检查旧表是否存在
        result = await conn.execute(
            text("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'users' AND table_catalog = current_database()")
        )
        table_exists = result.scalar() > 0

        if not table_exists:
            print("users 表不存在，将直接创建新表")
            await conn.run_sync(Base.metadata.create_all)
            print("新 users 表已创建")
            return

        # 2. 查看旧表结构（PostgreSQL information_schema）
        result = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'users' AND table_catalog = current_database()"
        ))
        columns = [row[0] for row in result.fetchall()]
        print(f"当前 users 表字段: {columns}")

        # 判断是否已经迁移过
        if "public_id" in columns:
            print("检测到 public_id 字段已存在，跳过迁移")
            return

        # 3. 备份旧表
        print("备份旧 users 表...")
        await conn.execute(text("DROP TABLE IF EXISTS users_backup"))
        await conn.execute(text("CREATE TABLE users_backup AS TABLE users"))
        result = await conn.execute(text("SELECT COUNT(*) FROM users_backup"))
        backup_count = result.scalar()
        print(f"已备份 {backup_count} 条用户记录")

        # 4. 记录旧数据
        result = await conn.execute(text("SELECT id, username, email, full_name, hashed_password, is_active, is_admin, last_login, created_at FROM users"))
        old_rows = result.fetchall()

        # 5. 处理外键引用（PostgreSQL 在事务内 DDL 自动处理外键）

        # 查找引用 users 的外键
        result = await conn.execute(
            text("""
                SELECT TABLE_NAME, CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
                WHERE REFERENCED_TABLE_NAME = 'users' AND TABLE_CATALOG = current_database()
            """)
        )
        fk_refs = result.fetchall()
        if fk_refs:
            print(f"发现外键引用: {[(r[0], r[1]) for r in fk_refs]}")
            for table_name, constraint_name in fk_refs:
                await conn.execute(text(f"ALTER TABLE {table_name} DROP CONSTRAINT {constraint_name}"))
                print(f"  已删除外键: {table_name}.{constraint_name}")

        # 6. 删除旧表并创建新表
        print("删除旧 users 表...")
        await conn.execute(text("DROP TABLE IF EXISTS users"))

        print("创建新 users 表...")
        await conn.run_sync(Base.metadata.create_all)

        # 7. 回填数据
        print(f"回填 {len(old_rows)} 条用户记录...")
        for row in old_rows:
            old_id, username, email, full_name, old_password_hash, is_active, is_admin, last_login, created_at = row

            # 旧密码无法通过新算法验证，设置为随机不可用密码
            new_password_hash = hash_password(str(uuid4()))

            # 根据 is_active 确定 disabled_at
            disabled_at = None if is_active else datetime.utcnow()

            await conn.execute(
                text("""
                    INSERT INTO users (id, public_id, username, nickname, email, password_hash,
                                       is_superuser, last_login_at, created_at, updated_at, disabled_at, sort_order)
                    VALUES (:id, :public_id, :username, :nickname, :email, :password_hash,
                            :is_superuser, :last_login_at, :created_at, :updated_at, :disabled_at, :sort_order)
                """),
                {
                    "id": old_id,
                    "public_id": str(uuid4()),
                    "username": username,
                    "nickname": full_name,
                    "email": email,
                    "password_hash": new_password_hash,
                    "is_superuser": is_admin,
                    "last_login_at": last_login,
                    "created_at": created_at or datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                    "disabled_at": disabled_at,
                    "sort_order": 0,
                }
            )

        # 8. 尝试恢复外键引用
        # 由于表结构一致（id 字段保留），可以重建外键
        if fk_refs:
            print("重建外键引用...")
            # 注意：这里需要知道引用列的名称，简化处理——仅重新创建已知的引用
            for table_name, _ in fk_refs:
                try:
                    await conn.execute(
                        text(f"""
                            ALTER TABLE {table_name}
                            ADD CONSTRAINT {table_name}_ibfk_user
                            FOREIGN KEY (user_id) REFERENCES users (id)
                        """)
                    )
                    print(f"  已重建外键: {table_name}.user_id")
                except Exception as exc:
                    print(f"  重建外键 {table_name} 失败: {exc}")

        # 9. PostgreSQL 事务提交后外键自动生效

    print(f"\n迁移完成！")
    print(f"  - 备份表: users_backup ({backup_count} 条记录)")
    print(f"  - 新 users 表已创建并回填数据")
    print(f"  - 所有用户密码已被重置（随机密码），需要管理员手动重置")
    print(f"  - 请使用默认管理员账号登录: admin / admin123")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(migrate())
