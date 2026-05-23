"""
Prompt 模板用户隔离功能测试
覆盖：数据迁移、CRUD、权限检查、用户隔离、同名共存
"""
import asyncio
import sys
import os
import time
import io

# 强制 UTF-8 编码输出
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 禁用 SQLAlchemy 日志
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.base import AsyncSessionLocal, engine, init_db
from backend.app.models.user import User
from backend.app.models.prompt import PromptTemplate
from backend.app.services.prompt_service import get_prompt_service, migrate_prompt_table


# ===== 辅助函数 =====

async def ensure_test_users(db: AsyncSession):
    """确保测试用户存在"""
    users = {}
    for username, is_admin in [("test_user_a", False), ("test_user_b", False), ("test_admin", True)]:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if not user:
            user = User(
                username=username,
                hashed_password="test_hash",
                email=f"{username}@test.com",
                is_admin=is_admin
            )
            db.add(user)
            await db.flush()
        users[username] = user
    return users


async def cleanup_test_data(db: AsyncSession):
    """清理测试数据"""
    # 删除测试用户创建的 prompt 模板
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name.like("test_%"))
    )
    for template in result.scalars().all():
        await db.delete(template)

    # 删除测试用户
    for username in ["test_user_a", "test_user_b", "test_admin"]:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user:
            await db.delete(user)


# ===== 测试用例 =====

class TestResults:
    """测试结果收集"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def record(self, name: str, passed: bool, detail: str = ""):
        if passed:
            self.passed += 1
            print(f"  [PASS] {name}")
        else:
            self.failed += 1
            self.errors.append((name, detail))
            print(f"  [FAIL] {name}: {detail}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"测试结果: {self.passed}/{total} 通过")
        if self.errors:
            print(f"\n失败项:")
            for name, detail in self.errors:
                print(f"  - {name}: {detail}")
        print(f"{'='*60}")
        return self.failed == 0


results = TestResults()


async def test_migration_idempotent():
    """测试1：数据迁移幂等性"""
    print("\n[测试1] 数据迁移幂等性")
    try:
        # 第一次迁移
        await migrate_prompt_table()
        # 第二次迁移（应无错误）
        await migrate_prompt_table()

        # 验证列存在
        async with engine.connect() as conn:
            r = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.COLUMNS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'prompt_templates' "
                "AND COLUMN_NAME = 'user_id'"
            ))
            exists = r.scalar() > 0
            results.record("迁移幂等执行", exists, "user_id 列不存在")

            # 验证复合唯一约束存在
            r2 = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS "
                "WHERE TABLE_SCHEMA = DATABASE() "
                "AND TABLE_NAME = 'prompt_templates' "
                "AND CONSTRAINT_NAME = 'uix_prompt_name_user'"
            ))
            constraint_exists = r2.scalar() > 0
            results.record("复合唯一约束存在", constraint_exists, "uix_prompt_name_user 约束不存在")
    except Exception as e:
        results.record("迁移幂等性", False, str(e))


async def test_seed_default_prompts():
    """测试2：默认模板种子数据（user_id 为 NULL）"""
    print("\n[测试2] 默认模板种子数据")
    try:
        service = get_prompt_service()
        count = await service.seed_default_prompts()
        results.record("种子数据导入", count >= 0, f"导入 {count} 个模板")

        # 验证默认模板 user_id 为 NULL
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(PromptTemplate).where(PromptTemplate.name == "material_ner")
            )
            template = r.scalar_one_or_none()
            if template:
                results.record("material_ner user_id 为 NULL", template.user_id is None,
                             f"user_id={template.user_id}")
            else:
                results.record("material_ner 存在", False, "模板不存在")
    except Exception as e:
        results.record("种子数据", False, str(e))


async def test_create_user_owned_template():
    """测试3：创建用户私有模板"""
    print("\n[测试3] 创建用户私有模板")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id

        service = get_prompt_service()

        # 清理可能残留的同名测试模板
        try:
            await service.delete_prompt("test_user_a_ner", user_id=user_a_id)
        except Exception:
            pass

        template = await service.create_prompt(
            name="test_user_a_ner",
            content="这是一个测试 NER prompt",
            description="测试描述",
            category="ner",
            domain="test",
            user_id=user_a_id
        )

        results.record("创建私有模板成功", template is not None)
        results.record("user_id 正确", template["user_id"] == user_a_id,
                     f"期望 {user_a_id}, 实际 {template['user_id']}")
        results.record("category 正确", template["category"] == "ner")

        # 验证数据库
        async with AsyncSessionLocal() as db:
            r = await db.execute(
                select(PromptTemplate).where(
                    PromptTemplate.name == "test_user_a_ner",
                    PromptTemplate.user_id == user_a_id
                )
            )
            db_template = r.scalar_one_or_none()
            results.record("数据库记录存在", db_template is not None)
    except Exception as e:
        results.record("创建私有模板", False, str(e))


async def test_list_prompt_isolation():
    """测试4：列表查询用户隔离"""
    print("\n[测试4] 列表查询用户隔离")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id
            user_b_id = users["test_user_b"].id

        service = get_prompt_service()

        # 确保用户 B 有自己的模板
        try:
            await service.create_prompt(
                name="test_user_b_ner",
                content="用户 B 的 NER prompt",
                category="ner",
                domain="test",
                user_id=user_b_id
            )
        except ValueError:
            pass  # 已存在，忽略

        # 用户 A 的列表
        list_a = await service.list_prompts(user_id=user_a_id)
        names_a = [t["name"] for t in list_a]

        # 用户 B 的列表
        list_b = await service.list_prompts(user_id=user_b_id)
        names_b = [t["name"] for t in list_b]

        # 用户 A 应看到自己的模板 + 共享模板，不应看到用户 B 的模板
        results.record("用户A看到自己的模板", "test_user_a_ner" in names_a,
                     f"列表: {names_a}")
        results.record("用户A看不到用户B的模板", "test_user_b_ner" not in names_a,
                     f"列表: {names_a}")
        results.record("用户A看到共享模板", "material_ner" in names_a,
                     f"列表: {names_a}")

        # 用户 B 应看到自己的模板 + 共享模板，不应看到用户 A 的模板
        results.record("用户B看到自己的模板", "test_user_b_ner" in names_b,
                     f"列表: {names_b}")
        results.record("用户B看不到用户A的模板", "test_user_a_ner" not in names_b,
                     f"列表: {names_b}")
        results.record("用户B看到共享模板", "material_ner" in names_b,
                     f"列表: {names_b}")
    except Exception as e:
        results.record("列表隔离", False, str(e))


async def test_same_name_different_user():
    """测试5：同名模板不同用户共存"""
    print("\n[测试5] 同名模板不同用户共存")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id
            user_b_id = users["test_user_b"].id

        service = get_prompt_service()

        # 清理可能残留的测试模板
        for uid in [user_a_id, user_b_id]:
            try:
                await service.delete_prompt("test_same_name", user_id=uid)
            except Exception:
                pass

        # 用户 A 创建同名模板
        template_a = await service.create_prompt(
            name="test_same_name",
            content="用户A的版本",
            category="ner",
            user_id=user_a_id
        )
        results.record("用户A创建同名模板", template_a is not None)

        # 用户 B 创建同名模板（应成功，因为复合唯一约束允许不同用户同名）
        template_b = await service.create_prompt(
            name="test_same_name",
            content="用户B的版本",
            category="ner",
            user_id=user_b_id
        )
        results.record("同名模板不同用户可创建", template_b is not None)

        # 各自获取自己的模板
        prompt_a = await service.get_prompt("test_same_name", user_id=user_a_id)
        prompt_b = await service.get_prompt("test_same_name", user_id=user_b_id)

        # 注意：get_prompt 可能优先返回共享模板或第一个匹配的
        # 需要验证 user_id 是否正确
        if prompt_a and prompt_b:
            results.record("用户A获取到模板", prompt_a["user_id"] == user_a_id,
                         f"user_id={prompt_a['user_id']}")
            results.record("用户B获取到模板", prompt_b["user_id"] == user_b_id,
                         f"user_id={prompt_b['user_id']}")
        else:
            results.record("同名模板获取", False, f"A={prompt_a}, B={prompt_b}")

    except Exception as e:
        results.record("同名模板共存", False, str(e))


async def test_delete_shared_template_denied():
    """测试6：删除共享模板被拒绝"""
    print("\n[测试6] 删除共享模板被拒绝")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id

        service = get_prompt_service()

        # 尝试删除共享模板 material_ner
        success = await service.delete_prompt("material_ner", user_id=user_a_id)
        results.record("不能删除共享模板", not success, "共享模板被成功删除了（不应该）")

        # 验证模板仍存在
        template = await service.get_prompt("material_ner", user_id=user_a_id)
        results.record("共享模板仍存在", template is not None)
    except Exception as e:
        results.record("删除共享模板保护", False, str(e))


async def test_delete_own_template():
    """测试7：删除自己的模板"""
    print("\n[测试7] 删除自己的模板")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id

        service = get_prompt_service()

        # 创建一个要删除的模板
        try:
            await service.create_prompt(
                name="test_to_delete",
                content="即将被删除",
                category="ner",
                user_id=user_a_id
            )
        except ValueError:
            pass

        # 删除
        success = await service.delete_prompt("test_to_delete", user_id=user_a_id)
        results.record("删除私有模板成功", success)

        # 验证不存在
        template = await service.get_prompt("test_to_delete", user_id=user_a_id)
        results.record("删除后模板不存在", template is None, f"模板仍存在: {template}")
    except Exception as e:
        results.record("删除私有模板", False, str(e))


async def test_update_permission():
    """测试8：更新权限检查"""
    print("\n[测试8] 更新权限检查")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id
            admin_id = users["test_admin"].id

        service = get_prompt_service()

        # 用户可以更新自己的模板
        updated = await service.update_prompt(
            "test_user_a_ner",
            user_id=user_a_id,
            content="更新后的内容"
        )
        results.record("用户可更新自己的模板", updated is not None)
        if updated:
            results.record("内容已更新", updated["content"] == "更新后的内容",
                         f"实际内容: {updated['content']}")

        # 管理员可以更新共享模板（service 层允许 user_id=None 时查找共享）
        admin_updated = await service.update_prompt(
            "material_ner",
            user_id=None,  # 管理员模式
            description="管理员更新的描述"
        )
        results.record("管理员可更新共享模板", admin_updated is not None)

        # 恢复原描述
        await service.update_prompt(
            "material_ner",
            user_id=None,
            description="超导材料领域实体识别Prompt模板"
        )
    except Exception as e:
        results.record("更新权限", False, str(e))


async def test_get_prompt_content_with_user_id():
    """测试9：get_prompt_content 传入 user_id"""
    print("\n[测试9] get_prompt_content 传入 user_id")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id
            user_b_id = users["test_user_b"].id

        service = get_prompt_service()

        # 用户 A 获取自己的模板内容
        content_a = await service.get_prompt_content("test_user_a_ner", user_id=user_a_id)
        results.record("用户A获取自己的模板内容", content_a is not None)

        # 用户 B 获取不到用户 A 的模板
        content_b = await service.get_prompt_content("test_user_a_ner", user_id=user_b_id)
        results.record("用户B获取不到用户A的模板", content_b is None,
                     f"获取到了: {content_b[:50] if content_b else 'None'}")

        # 所有用户都能获取共享模板
        shared_content = await service.get_prompt_content("material_ner", user_id=user_a_id)
        results.record("用户A获取共享模板", shared_content is not None)

        shared_content_b = await service.get_prompt_content("material_ner", user_id=user_b_id)
        results.record("用户B获取共享模板", shared_content_b is not None)

        # 不传 user_id 时获取共享模板
        shared_no_user = await service.get_prompt_content("material_ner", user_id=None)
        results.record("无user_id获取共享模板", shared_no_user is not None)
    except Exception as e:
        results.record("get_prompt_content", False, str(e))


async def test_category_filter():
    """测试10：分类筛选"""
    print("\n[测试10] 分类筛选")
    try:
        async with AsyncSessionLocal() as db:
            users = await ensure_test_users(db)
            user_a_id = users["test_user_a"].id

        service = get_prompt_service()

        # 确保有 RE 模板
        try:
            await service.create_prompt(
                name="test_user_a_re",
                content="测试 RE prompt",
                category="re",
                domain="test",
                user_id=user_a_id
            )
        except ValueError:
            pass

        # 筛选 NER
        ner_list = await service.list_prompts(user_id=user_a_id, category="ner")
        all_ner = all(t["category"] == "ner" for t in ner_list)
        results.record("NER 筛选正确", all_ner, f"列表: {[t['name'] for t in ner_list]}")

        # 筛选 RE
        re_list = await service.list_prompts(user_id=user_a_id, category="re")
        all_re = all(t["category"] == "re" for t in re_list)
        results.record("RE 筛选正确", all_re, f"列表: {[t['name'] for t in re_list]}")
    except Exception as e:
        results.record("分类筛选", False, str(e))


async def test_cleanup():
    """清理测试数据"""
    print("\n[清理] 删除测试数据")
    try:
        async with AsyncSessionLocal() as db:
            await cleanup_test_data(db)
        print("  清理完成")
    except Exception as e:
        print(f"  清理失败: {e}")


async def main():
    print("=" * 60)
    print("Prompt 模板用户隔离功能测试")
    print("=" * 60)

    t0 = time.time()

    # 确保数据库表已初始化
    await init_db()

    # 按顺序执行测试
    await test_migration_idempotent()
    await test_seed_default_prompts()
    await test_create_user_owned_template()
    await test_list_prompt_isolation()
    await test_same_name_different_user()
    await test_delete_shared_template_denied()
    await test_delete_own_template()
    await test_update_permission()
    await test_get_prompt_content_with_user_id()
    await test_category_filter()

    # 清理
    await test_cleanup()

    elapsed = time.time() - t0
    print(f"\n总耗时: {elapsed:.2f}s")
    results.summary()

    return results.failed == 0


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
