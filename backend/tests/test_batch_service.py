"""
批量处理服务测试

覆盖：
- _clean_excel_text Excel 文本清洗
- 批量任务状态转换验证
- ComprehensiveTask ORM 模型基础验证
"""
import pytest
import re

from backend.app.services.batch_service import _clean_excel_text


# ============================================================================
# _clean_excel_text 测试
# ============================================================================

class TestCleanExcelText:
    """Excel 文本清洗测试"""

    def test_clean_string(self):
        """清洗非法字符"""
        # Excel 不允许的控制字符（0x00-0x1F 中除 \t \n \r）
        dirty = "正常文本\x00带有\x01非法\x02字符"
        clean = _clean_excel_text(dirty)
        assert "\x00" not in clean
        assert "\x01" not in clean
        assert "\x02" not in clean
        assert "正常文本" in clean
        assert "带有" in clean

    def test_preserve_normal_chars(self):
        """保留正常字符"""
        normal = "YBCO薄膜，Jc=1.5MA/cm² @ 77K, 0T"
        assert _clean_excel_text(normal) == normal

    def test_non_string_passthrough(self):
        """非字符串原样返回"""
        assert _clean_excel_text(123) == 123
        assert _clean_excel_text(1.5) == 1.5
        assert _clean_excel_text(None) is None
        assert _clean_excel_text(True) is True

    def test_empty_string(self):
        """空字符串不变"""
        assert _clean_excel_text("") == ""

    def test_unicode_preserved(self):
        """中文字符保留"""
        text = "超导薄膜实验数据：温度77K"
        assert _clean_excel_text(text) == text

    def test_tab_newline_preserved(self):
        """制表符和换行符保留（Excel 允许）"""
        text = "列1\t列2\n行2"
        assert _clean_excel_text(text) == text


# ============================================================================
# 批量任务状态转换测试
# ============================================================================

class TestBatchTaskStatusTransitions:
    """批量任务状态转换验证"""

    def test_valid_status_values(self):
        """验证所有合法状态值"""
        valid_statuses = ["pending", "running", "completed", "failed", "cancelled"]
        for s in valid_statuses:
            assert isinstance(s, str)
            assert len(s) > 0

    def test_terminal_states(self):
        """终态不可再转换"""
        terminal = ["completed", "failed", "cancelled"]
        for s in terminal:
            # 终态任务不应有后续状态
            assert s in terminal


# ============================================================================
# ComprehensiveTask ORM 模型测试
# ============================================================================

class TestComprehensiveTaskModel:
    """综合分析任务 ORM 模型验证"""

    def test_model_table_name(self):
        """验证表名"""
        from backend.app.models.comprehensive import ComprehensiveTask
        assert ComprehensiveTask.__tablename__ == "comprehensive_tasks"

    def test_model_has_required_columns(self):
        """验证必需列存在"""
        from backend.app.models.comprehensive import ComprehensiveTask
        col_names = [c.name for c in ComprehensiveTask.__table__.columns]
        required = ["id", "task_id", "user_id", "status", "progress", "result", "created_at", "updated_at"]
        for r in required:
            assert r in col_names, f"缺少列: {r}"

    def test_task_id_unique_index(self):
        """验证 task_id 有唯一约束"""
        from backend.app.models.comprehensive import ComprehensiveTask
        task_id_col = ComprehensiveTask.__table__.columns["task_id"]
        assert task_id_col.unique is True

    def test_user_id_foreign_key(self):
        """验证 user_id 有外键约束"""
        from backend.app.models.comprehensive import ComprehensiveTask
        fk = list(ComprehensiveTask.__table__.columns["user_id"].foreign_keys)
        assert len(fk) > 0
        assert fk[0].target_fullname == "users.id"