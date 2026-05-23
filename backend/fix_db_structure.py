"""
修复数据库表结构 - 添加缺失的 session_id 列
"""
import asyncio
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.models.base import engine, Base
from backend.app.models.excel_extraction import ExcelExtractionTask
from sqlalchemy import text

async def fix_database():
    """检查并添加缺失的列"""
    async with engine.begin() as conn:
        # 检查表是否存在
        try:
            result = await conn.execute(text("SHOW TABLES LIKE 'excel_extraction_tasks'"))
            table_exists = result.fetchone() is not None

            if table_exists:
                # 检查 session_id 列是否存在
                result = await conn.execute(text("SHOW COLUMNS FROM excel_extraction_tasks LIKE 'session_id'"))
                column_exists = result.fetchone() is not None

                if not column_exists:
                    print("添加 session_id 列...")
                    await conn.execute(text("""
                        ALTER TABLE excel_extraction_tasks
                        ADD COLUMN session_id VARCHAR(64)
                    """))
                    print("session_id 列已添加")
                else:
                    print("session_id 列已存在")

                # 检查其他可能缺失的列
                columns_to_check = ['current_step', 'current_node', 'pending_check', 'chat_history']
                for col in columns_to_check:
                    result = await conn.execute(text(f"SHOW COLUMNS FROM excel_extraction_tasks LIKE '{col}'"))
                    if not result.fetchone():
                        print(f"添加 {col} 列...")
                        if col == 'chat_history':
                            await conn.execute(text(f"ALTER TABLE excel_extraction_tasks ADD COLUMN {col} JSON"))
                        else:
                            await conn.execute(text(f"ALTER TABLE excel_extraction_tasks ADD COLUMN {col} VARCHAR(100)"))
                        print(f"{col} 列已添加")
            else:
                print("表不存在，创建新表...")
                await conn.run_sync(Base.metadata.create_all)
                print("表已创建")

        except Exception as e:
            print(f"错误: {e}")
            raise

    print("数据库修复完成")

if __name__ == "__main__":
    asyncio.run(fix_database())