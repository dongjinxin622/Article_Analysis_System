"""
完整测试 API 数据流
"""
import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.models.base import AsyncSessionLocal
from backend.app.models.excel_extraction import ExcelExtractionTask
from backend.app.schemas.excel_extraction import TaskDetailResponse, ExcelExtractionTaskStatus
from sqlalchemy import select

async def test_api_flow():
    """测试完整 API 数据流"""
    async with AsyncSessionLocal() as session:
        # 模拟 list_tasks 的查询
        result = await session.execute(
            select(ExcelExtractionTask)
            .order_by(ExcelExtractionTask.created_at.desc())
            .limit(1)
        )
        task = result.scalar_one_or_none()

        if task:
            print("\n===== 1. SQLAlchemy 模型属性 =====")
            print(f"task.task_id: {task.task_id}")
            print(f"task.session_id: {task.session_id}")
            print(f"type(task.session_id): {type(task.session_id)}")

            # 检查对象内部
            print("\n===== 2. task.__dict__ =====")
            print(f"session_id in __dict__: {task.__dict__.get('session_id')}")

            print("\n===== 3. 创建 Pydantic Response =====")
            response = TaskDetailResponse(
                task_id=task.task_id,
                task_name=task.task_name or "",
                session_id=task.session_id,  # 这里传入
                status=ExcelExtractionTaskStatus(task.status),
                total_rows=task.total_rows or 0,
                processed_rows=task.processed_rows or 0,
                success_rows=task.success_rows or 0,
                failed_rows=task.failed_rows or 0,
                progress=task.progress or 0.0,
                current_step=task.current_step,
                current_node=task.current_node,
                pending_check=task.pending_check,
                config=task.config or {},
                chat_history=task.chat_history or [],
                created_at=task.created_at,
                started_at=task.started_at,
                completed_at=task.completed_at,
                error_message=task.error_message,
                output_file_path=task.output_file_path,
            )

            print(f"response.session_id: {response.session_id}")

            print("\n===== 4. model_dump() =====")
            dumped = response.model_dump()
            print(f"dumped session_id: {dumped.get('session_id')}")

            print("\n===== 5. model_dump(mode='json') =====")
            dumped_json = response.model_dump(mode='json')
            print(f"dumped_json session_id: {dumped_json.get('session_id')}")

            print("\n===== 6. 最终 JSON =====")
            json_str = json.dumps(dumped_json, ensure_ascii=False, indent=2)
            print(json_str[:500])

            # 检查 session_id 是否在 JSON 中
            if 'session_id' in json_str:
                print("\n✅ session_id 在 JSON 中")
            else:
                print("\n❌ session_id 不在 JSON 中")

if __name__ == "__main__":
    asyncio.run(test_api_flow())