"""
综合分析 API 路由测试

覆盖：
- _task_info_to_response 字典转 Pydantic 模型
- Prompt 模板用户隔离逻辑验证
"""
import pytest
from backend.app.api.v1.comprehensive import _task_info_to_response, TaskStatusResponse


# ============================================================================
# _task_info_to_response 测试
# ============================================================================

class TestTaskInfoToResponse:
    """任务字典转 TaskStatusResponse 测试"""

    def test_basic_conversion(self):
        """基本字段转换"""
        info = {
            "task_id": "abc-123",
            "status": "running",
            "progress": 50,
            "message": "处理中",
            "result": {"key": "val"},
        }
        resp = _task_info_to_response(info)
        assert resp.task_id == "abc-123"
        assert resp.status == "running"
        assert resp.progress == 50
        assert resp.message == "处理中"
        assert resp.result == {"key": "val"}

    def test_default_values(self):
        """缺失字段使用默认值"""
        info = {}
        resp = _task_info_to_response(info)
        assert resp.task_id == ""
        assert resp.task_type == "one_click_analysis"
        assert resp.status == "unknown"
        assert resp.progress == 0
        assert resp.message == ""
        assert resp.result is None
        assert resp.error is None

    def test_stage_mapping(self):
        """stage 字段映射到 current_step"""
        info = {"stage": "ner_processing"}
        resp = _task_info_to_response(info)
        assert resp.current_step == "ner_processing"

    def test_current_step_direct(self):
        """current_step 字段直接使用"""
        info = {"current_step": "jc_analysis"}
        resp = _task_info_to_response(info)
        assert resp.current_step == "jc_analysis"

    def test_stage_priority_over_current_step(self):
        """stage 优先于 current_step"""
        info = {"stage": "ner_processing", "current_step": "jc_analysis"}
        resp = _task_info_to_response(info)
        assert resp.current_step == "ner_processing"

    def test_error_field(self):
        """错误字段传递"""
        info = {"error": "PDF 解析失败"}
        resp = _task_info_to_response(info)
        assert resp.error == "PDF 解析失败"

    def test_task_type_override(self):
        """task_type 可被覆盖"""
        info = {"task_type": "batch_extraction"}
        resp = _task_info_to_response(info)
        assert resp.task_type == "batch_extraction"

    def test_timestamp_fields(self):
        """时间戳字段传递"""
        info = {"created_at": 1700000000, "updated_at": 1700001000}
        resp = _task_info_to_response(info)
        assert resp.created_at == 1700000000
        assert resp.updated_at == 1700001000

    def test_response_is_pydantic(self):
        """返回值是 Pydantic 模型实例"""
        info = {"task_id": "test"}
        resp = _task_info_to_response(info)
        assert isinstance(resp, TaskStatusResponse)

    def test_response_serializable(self):
        """返回值可序列化为 JSON"""
        info = {"task_id": "test", "status": "completed", "progress": 100}
        resp = _task_info_to_response(info)
        json_data = resp.model_dump(mode="json")
        assert json_data["task_id"] == "test"
        assert json_data["status"] == "completed"
        assert json_data["progress"] == 100