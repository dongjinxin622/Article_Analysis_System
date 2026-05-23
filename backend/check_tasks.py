"""
检查数据库中的任务数据
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.models.base import engine
from sqlalchemy import text

async def check_tasks():
    """检查任务数据"""
    async with engine.begin() as conn:
        result = await conn.execute(text("""
            SELECT task_id, task_name, session_id, status, progress
            FROM excel_extraction_tasks
            ORDER BY created_at DESC
            LIMIT 10
        """))
        rows = result.fetchall()

        print("\n最近的任务数据:")
        print("-" * 80)
        for row in rows:
            task_id, task_name, session_id, status, progress = row
            print(f"task_id: {task_id}")
            print(f"task_name: {task_name}")
            print(f"session_id: {session_id or 'NULL'}")
            print(f"status: {status}")
            print(f"progress: {progress}")
            print("-" * 40)

if __name__ == "__main__":
    asyncio.run(check_tasks())