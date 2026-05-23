"""
测试 SQLAlchemy 模型加载 session_id
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.models.base import AsyncSessionLocal
from backend.app.models.excel_extraction import ExcelExtractionTask
from sqlalchemy import select

async def test_model():
    """测试模型加载"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ExcelExtractionTask)
            .order_by(ExcelExtractionTask.created_at.desc())
            .limit(1)
        )
        task = result.scalar_one_or_none()

        if task:
            print(f"\n任务属性:")
            print(f"  task_id: {task.task_id}")
            print(f"  task_name: {task.task_name}")
            print(f"  session_id: {task.session_id}")
            print(f"  status: {task.status}")
            print(f"  progress: {task.progress}")

            # 检查是否有 __dict__ 属性
            print(f"\n任务对象 __dict__:")
            for key, value in task.__dict__.items():
                if not key.startswith('_'):
                    print(f"  {key}: {value}")
        else:
            print("没有找到任务")

if __name__ == "__main__":
    asyncio.run(test_model())