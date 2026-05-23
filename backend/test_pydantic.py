"""
测试 Pydantic 模型序列化
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.schemas.excel_extraction import TaskDetailResponse, ExcelExtractionTaskStatus
import json

# 创建测试数据
response = TaskDetailResponse(
    task_id="test-123",
    task_name="测试任务",
    session_id="abc123-session",
    status=ExcelExtractionTaskStatus.PROCESSING,
    total_rows=100,
    processed_rows=50,
    success_rows=40,
    failed_rows=10,
    progress=50.0,
    current_step="processing",
    current_node=None,
    pending_check=None,
    config={"test": "value"},
    chat_history=[],
    created_at=None,
    started_at=None,
    completed_at=None,
    error_message=None,
    output_file_path=None,
)

print("\n===== Pydantic v2 model_dump() =====")
dumped = response.model_dump()
print(f"session_id in dumped: {dumped.get('session_id')}")

print("\n===== Pydantic v2 model_dump(mode='json') =====")
dumped_json = response.model_dump(mode='json')
print(f"session_id in dumped_json: {dumped_json.get('session_id')}")

print("\n===== JSON 序列化 =====")
json_str = json.dumps(dumped)
print(f"JSON: {json_str[:200]}...")

# 测试 None 值的情况
print("\n===== 测试 session_id=None =====")
response_none = TaskDetailResponse(
    task_id="test-456",
    task_name="测试任务2",
    session_id=None,  # None 值
    status=ExcelExtractionTaskStatus.PENDING,
    total_rows=0,
    processed_rows=0,
    success_rows=0,
    failed_rows=0,
    progress=0.0,
    config={},
    chat_history=[],
)
dumped_none = response_none.model_dump()
print(f"session_id in dumped_none: {dumped_none.get('session_id')}")
print(f"Full dumped_none keys: {list(dumped_none.keys())}")

json_str_none = json.dumps(dumped_none)
print(f"JSON with None: {json_str_none}")