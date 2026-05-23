"""
Prompt模板服务层
管理NER/RE Prompt模板的CRUD操作
支持用户隔离：user_id=NULL表示全局共享模板
"""
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from sqlalchemy import select, or_, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.prompt import PromptTemplate
from backend.app.models.base import get_db_context, engine
from backend.app.core.config import BASE_DIR

logger = logging.getLogger(__name__)


async def migrate_prompt_table():
    """
    数据迁移：为 prompt_templates 表添加 user_id 列和复合唯一约束
    PostgreSQL 版本。幂等安全。
    """
    try:
        async with engine.connect() as conn:
            # 检查 user_id 列是否已存在（PostgreSQL information_schema）
            result = await conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_catalog = current_database() "
                "AND table_name = 'prompt_templates' "
                "AND column_name = 'user_id'"
            ))
            exists = result.scalar() > 0

            if not exists:
                logger.info("开始迁移 prompt_templates 表...")

                # 添加 user_id 列（可空）
                await conn.execute(text(
                    "ALTER TABLE prompt_templates ADD COLUMN user_id INTEGER DEFAULT NULL"
                ))

                # 添加索引（PostgreSQL 语法）
                await conn.execute(text(
                    "CREATE INDEX ix_prompt_user_id ON prompt_templates (user_id)"
                ))

                # 添加外键
                try:
                    await conn.execute(text(
                        "ALTER TABLE prompt_templates ADD FOREIGN KEY (user_id) REFERENCES users(id)"
                    ))
                except Exception as e:
                    logger.warning(f"添加外键约束失败（可能已存在）: {e}")

                # 移除旧的 name 唯一索引
                for idx_name in ["ix_prompt_templates_name", "prompt_templates_name_key"]:
                    try:
                        await conn.execute(text(f"DROP INDEX IF EXISTS {idx_name}"))
                        logger.info(f"已移除旧索引: {idx_name}")
                    except Exception as e:
                        logger.warning(f"移除旧索引 {idx_name} 失败（可能不存在）: {e}")

                # 添加复合唯一约束
                try:
                    await conn.execute(text(
                        "ALTER TABLE prompt_templates ADD CONSTRAINT uix_prompt_name_user UNIQUE (name, user_id)"
                    ))
                except Exception as e:
                    logger.warning(f"添加复合唯一约束失败（可能已存在）: {e}")

                await conn.commit()
                logger.info("prompt_templates 表迁移完成：已添加 user_id 列")
            else:
                logger.info("prompt_templates 表已包含 user_id 列，检查旧索引...")

                # PostgreSQL：检查 name 列上的旧唯一约束
                check = await conn.execute(text(
                    "SELECT constraint_name FROM information_schema.table_constraints "
                    "WHERE table_catalog = current_database() "
                    "AND table_name = 'prompt_templates' "
                    "AND constraint_type = 'UNIQUE' "
                    "AND constraint_name != 'uix_prompt_name_user'"
                ))
                stale_constraints = [row[0] for row in check.fetchall()]

                if stale_constraints:
                    logger.info(f"发现旧的唯一约束: {stale_constraints}，正在移除...")
                    for name in stale_constraints:
                        try:
                            await conn.execute(text(
                                f"ALTER TABLE prompt_templates DROP CONSTRAINT IF EXISTS {name}"
                            ))
                            logger.info(f"已移除旧约束: {name}")
                        except Exception as e:
                            logger.warning(f"移除旧约束 {name} 失败: {e}")
                    await conn.commit()
                else:
                    logger.info("未发现需要清理的旧索引")

    except Exception as e:
        logger.error(f"prompt_templates 表迁移失败: {e}")
        raise


class PromptService:
    """Prompt模板服务"""

    async def list_prompts(
        self,
        user_id: int,  # 必填：用户ID
        category: Optional[str] = None,
        domain: Optional[str] = None,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        获取Prompt模板列表（用户私有 + 全局共享）

        Args:
            user_id: 用户ID，返回该用户的模板 + 全局共享模板
            category: 分类筛选（ner/re）
            domain: 领域筛选
            active_only: 是否只返回活跃模板

        Returns:
            Prompt模板列表
        """
        async with get_db_context() as db:
            query = select(PromptTemplate)

            # 用户隔离：用户私有 + 全局共享
            query = query.where(
                or_(PromptTemplate.user_id == user_id, PromptTemplate.user_id == None)
            )

            if category:
                query = query.where(PromptTemplate.category == category)
            if domain:
                query = query.where(PromptTemplate.domain == domain)
            if active_only:
                query = query.where(PromptTemplate.is_active == True)

            query = query.order_by(PromptTemplate.user_id.desc(), PromptTemplate.name)  # 用户模板优先

            result = await db.execute(query)
            templates = result.scalars().all()

            return [
                {
                    "name": t.name,
                    "content": t.content,
                    "description": t.description,
                    "category": t.category,
                    "domain": t.domain,
                    "is_active": t.is_active,
                    "user_id": t.user_id,  # 新增：用于区分归属
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                    "updated_at": t.updated_at.isoformat() if t.updated_at else None
                }
                for t in templates
            ]

    async def get_prompt(self, name: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        获取单个Prompt模板

        Args:
            name: 模板名称
            user_id: 用户ID（可选），传入时按用户过滤

        Returns:
            Prompt模板详情，不存在返回None
        """
        async with get_db_context() as db:
            query = select(PromptTemplate).where(PromptTemplate.name == name)

            # 如果传入 user_id，按用户过滤
            if user_id is not None:
                query = query.where(
                    or_(PromptTemplate.user_id == user_id, PromptTemplate.user_id == None)
                )

            result = await db.execute(query)
            template = result.scalar_one_or_none()

            if not template:
                return None

            return {
                "name": template.name,
                "content": template.content,
                "description": template.description,
                "category": template.category,
                "domain": template.domain,
                "is_active": template.is_active,
                "user_id": template.user_id,
                "created_at": template.created_at.isoformat() if template.created_at else None,
                "updated_at": template.updated_at.isoformat() if template.updated_at else None
            }

    async def get_prompt_content(self, name: str, user_id: Optional[int] = None) -> Optional[str]:
        """
        获取Prompt模板内容（供NER/RE服务使用）

        Args:
            name: 模板名称
            user_id: 用户ID（可选），传入时按用户过滤

        Returns:
            Prompt内容文本，不存在返回None
        """
        template = await self.get_prompt(name, user_id=user_id)
        if template:
            return template["content"]
        return None

    async def create_prompt(
        self,
        name: str,
        content: str,
        description: Optional[str] = None,
        category: str = "ner",
        domain: Optional[str] = None,
        user_id: Optional[int] = None  # 新增：用户ID，None表示全局共享
    ) -> Dict[str, Any]:
        """
        创建Prompt模板

        Args:
            name: 模板名称
            content: 模板内容
            description: 描述
            category: 分类（ner/re）
            domain: 领域
            user_id: 用户ID，None表示全局共享（仅seed时使用）

        Returns:
            创建的模板详情
        """
        async with get_db_context() as db:
            # 检查是否已存在（同用户内名称唯一）
            query = select(PromptTemplate).where(
                PromptTemplate.name == name,
                PromptTemplate.user_id == user_id
            )
            result = await db.execute(query)
            existing = result.scalar_one_or_none()

            if existing:
                raise ValueError(f"Prompt模板 '{name}' 已存在")

            template = PromptTemplate(
                name=name,
                content=content,
                description=description,
                category=category,
                domain=domain,
                is_active=True,
                user_id=user_id  # 设置用户ID
            )

            db.add(template)
            await db.flush()

            return {
                "name": template.name,
                "content": template.content,
                "description": template.description,
                "category": template.category,
                "domain": template.domain,
                "is_active": template.is_active,
                "user_id": template.user_id,
                "created_at": template.created_at.isoformat() if template.created_at else None,
                "updated_at": template.updated_at.isoformat() if template.updated_at else None
            }

    async def update_prompt(
        self,
        name: str,
        user_id: Optional[int] = None,  # 新增：用户ID
        content: Optional[str] = None,
        description: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Dict[str, Any]]:
        """
        更新Prompt模板

        Args:
            name: 模板名称
            user_id: 用户ID，用于定位模板
            content: 新内容
            description: 新描述
            is_active: 是否活跃

        Returns:
            更新后的模板详情，不存在返回None
        """
        async with get_db_context() as db:
            query = select(PromptTemplate).where(PromptTemplate.name == name)

            # 按用户过滤（可以更新自己的模板或共享模板）
            if user_id is not None:
                query = query.where(
                    or_(PromptTemplate.user_id == user_id, PromptTemplate.user_id == None)
                )

            result = await db.execute(query)
            template = result.scalar_one_or_none()

            if not template:
                return None

            if content is not None:
                template.content = content
            if description is not None:
                template.description = description
            if is_active is not None:
                template.is_active = is_active

            await db.flush()

            return {
                "name": template.name,
                "content": template.content,
                "description": template.description,
                "category": template.category,
                "domain": template.domain,
                "is_active": template.is_active,
                "user_id": template.user_id,
                "created_at": template.created_at.isoformat() if template.created_at else None,
                "updated_at": template.updated_at.isoformat() if template.updated_at else None
            }

    async def delete_prompt(self, name: str, user_id: Optional[int] = None) -> bool:
        """
        删除Prompt模板（只能删除用户自己的模板，不能删除共享模板）

        Args:
            name: 模板名称
            user_id: 用户ID，用于验证所有权

        Returns:
            是否成功删除
        """
        async with get_db_context() as db:
            query = select(PromptTemplate).where(
                PromptTemplate.name == name,
                PromptTemplate.user_id == user_id  # 只能删除用户自己的
            )
            result = await db.execute(query)
            template = result.scalar_one_or_none()

            if not template:
                return False

            await db.delete(template)
            return True

    async def seed_default_prompts(self) -> int:
        """
        从文件系统导入默认Prompt模板到数据库

        注意：默认模板的 user_id 为 NULL（全局共享）

        导入的文件：
        - scipdf/ner_queries/material_ner.txt → name="material_ner", category="ner", domain="material"
        - scipdf/re_queries/material_re.txt → name="material_re", category="re", domain="material"

        Returns:
            导入的模板数量
        """
        default_prompts = [
            {
                "name": "material_ner",
                "file_path": BASE_DIR / "scipdf" / "ner_queries" / "material_ner.txt",
                "category": "ner",
                "domain": "material",
                "description": "超导材料领域实体识别Prompt模板"
            },
            {
                "name": "material_re",
                "file_path": BASE_DIR / "scipdf" / "re_queries" / "material_re.txt",
                "category": "re",
                "domain": "material",
                "description": "超导材料领域关系抽取Prompt模板"
            }
        ]

        imported_count = 0

        for prompt_config in default_prompts:
            file_path = prompt_config["file_path"]

            if not file_path.exists():
                logger.warning(f"Prompt文件不存在: {file_path}")
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # 检查是否已存在（不限 user_id，查找全局共享模板）
                existing = await self.get_prompt(prompt_config["name"], user_id=None)
                if existing:
                    # 已存在则更新内容（保持 user_id=NULL）
                    await self.update_prompt(
                        prompt_config["name"],
                        user_id=None,  # 不限用户，可更新共享模板
                        content=content,
                        description=prompt_config["description"]
                    )
                    logger.info(f"已更新Prompt模板: {prompt_config['name']}")
                else:
                    # 不存在则创建（user_id=None，全局共享）
                    await self.create_prompt(
                        name=prompt_config["name"],
                        content=content,
                        description=prompt_config["description"],
                        category=prompt_config["category"],
                        domain=prompt_config["domain"],
                        user_id=None  # 全局共享
                    )
                    logger.info(f"已导入Prompt模板: {prompt_config['name']}")

                imported_count += 1

            except Exception as e:
                logger.error(f"导入Prompt模板失败: {prompt_config['name']}, {e}")

        return imported_count


# 全局服务实例
_prompt_service_instance = None


def get_prompt_service() -> PromptService:
    """获取Prompt服务单例"""
    global _prompt_service_instance
    if _prompt_service_instance is None:
        _prompt_service_instance = PromptService()
    return _prompt_service_instance