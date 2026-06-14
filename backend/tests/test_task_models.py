"""
异步任务数据模型测试

验证 TaskJob / TaskItem / TaskDeadLetter 模型的创建、关联和基本属性。
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.tasks import TaskJob, TaskItem, TaskDeadLetter, TaskStatus, _utc_now


# ==================== TaskJob 模型测试 ====================

@pytest.mark.asyncio
class TestTaskJobModel:
    """TaskJob 模型基本测试"""

    async def test_create_task_job(self, test_db_session: AsyncSession):
        """测试创建任务主记录"""
        job = TaskJob(
            task_type="scipdf.pdf.parse",
            queue_name="default",
            status=TaskStatus.PENDING,
            created_by="test_user_001",
            project_public_id="project_001",
            priority=5,
            total_items=3,
            payload={"file_path": "/tmp/test.pdf"},
        )
        test_db_session.add(job)
        await test_db_session.commit()
        await test_db_session.refresh(job)

        assert job.id is not None
        assert job.public_id is not None and len(job.public_id) == 36
        assert job.task_type == "scipdf.pdf.parse"
        assert job.queue_name == "default"
        assert job.status == TaskStatus.PENDING
        assert job.created_by == "test_user_001"
        assert job.project_public_id == "project_001"
        assert job.priority == 5
        assert job.total_items == 3
        assert job.payload == {"file_path": "/tmp/test.pdf"}
        assert job.completed_items == 0
        assert job.failed_items == 0
        assert job.created_at is not None
        assert job.updated_at is not None

    async def test_task_job_default_values(self, test_db_session: AsyncSession):
        """测试 TaskJob 默认值"""
        job = TaskJob(
            task_type="scipdf.ner.extract",
            status=TaskStatus.PENDING,
        )
        test_db_session.add(job)
        await test_db_session.commit()
        await test_db_session.refresh(job)

        assert job.queue_name == ""
        assert job.created_by == ""
        assert job.project_public_id == ""
        assert job.priority == 0
        assert job.total_items == 0
        assert job.payload == {}
        assert job.result == {}
        assert job.error_code == ""
        assert job.error_message == ""

    async def test_task_job_repr(self, test_db_session: AsyncSession):
        """测试 TaskJob 的 __repr__"""
        job = TaskJob(
            task_type="scipdf.pdf.parse",
            status=TaskStatus.PENDING,
        )
        test_db_session.add(job)
        await test_db_session.commit()
        await test_db_session.refresh(job)

        repr_str = repr(job)
        assert "TaskJob" in repr_str
        assert job.public_id in repr_str
        assert "scipdf.pdf.parse" in repr_str


# ==================== TaskItem 模型测试 ====================

@pytest.mark.asyncio
class TestTaskItemModel:
    """TaskItem 模型基本测试"""

    async def test_create_task_item(self, test_db_session: AsyncSession):
        """测试创建任务子项"""
        job = TaskJob(
            task_type="scipdf.ner.batch",
            status=TaskStatus.PENDING,
            total_items=2,
        )
        test_db_session.add(job)
        await test_db_session.flush()

        item = TaskItem(
            job_id=job.id,
            task_type="scipdf.ner.extract",
            item_type="single",
            item_key="item_001",
            status=TaskStatus.PENDING,
            priority=3,
            payload={"result_id": "result_001"},
            max_attempts=5,
        )
        test_db_session.add(item)
        await test_db_session.commit()
        await test_db_session.refresh(item)

        assert item.id is not None
        assert item.public_id is not None and len(item.public_id) == 36
        assert item.job_id == job.id
        assert item.task_type == "scipdf.ner.extract"
        assert item.item_type == "single"
        assert item.item_key == "item_001"
        assert item.status == TaskStatus.PENDING
        assert item.priority == 3
        assert item.payload == {"result_id": "result_001"}
        assert item.attempt_count == 0
        assert item.max_attempts == 5
        assert item.worker_id == ""
        assert item.heartbeat_at is None

    async def test_task_item_default_values(self, test_db_session: AsyncSession):
        """测试 TaskItem 默认值"""
        job = TaskJob(task_type="scipdf.re.extract", status=TaskStatus.PENDING)
        test_db_session.add(job)
        await test_db_session.flush()

        item = TaskItem(job_id=job.id, task_type="scipdf.re.extract", status=TaskStatus.PENDING)
        test_db_session.add(item)
        await test_db_session.commit()
        await test_db_session.refresh(item)

        assert item.item_type == ""
        assert item.item_key == ""
        assert item.priority == 0
        assert item.payload == {}
        assert item.result == {}
        assert item.error_code == ""
        assert item.error_message == ""
        assert item.attempt_count == 0
        assert item.max_attempts == 3  # 默认最大重试次数

    async def test_task_item_relationship(self, test_db_session: AsyncSession):
        """测试 TaskItem 与 TaskJob 的关联关系"""
        job = TaskJob(task_type="scipdf.ner.batch", status=TaskStatus.PENDING)
        test_db_session.add(job)
        await test_db_session.flush()

        item = TaskItem(job_id=job.id, task_type="scipdf.ner.extract", status=TaskStatus.PENDING)
        test_db_session.add(item)
        await test_db_session.commit()
        await test_db_session.refresh(item)
        await test_db_session.refresh(job)

        # 验证关系
        assert item.job == job
        assert item in job.items


# ==================== TaskDeadLetter 模型测试 ====================

@pytest.mark.asyncio
class TestTaskDeadLetterModel:
    """TaskDeadLetter 模型基本测试"""

    async def test_create_dead_letter(self, test_db_session: AsyncSession):
        """测试创建死信记录"""
        dl = TaskDeadLetter(
            task_type="scipdf.ner.extract",
            item_type="single",
            item_key="item_failed",
            payload={"result_id": "result_failed"},
            error_code="ner_extraction_failed",
            error_message="NER 提取超时",
            attempt_count=3,
            max_attempts=3,
            original_item_public_id="original_item_001",
            worker_id="worker_001",
            stream_id="stream_123",
        )
        test_db_session.add(dl)
        await test_db_session.commit()
        await test_db_session.refresh(dl)

        assert dl.id is not None
        assert dl.task_type == "scipdf.ner.extract"
        assert dl.error_code == "ner_extraction_failed"
        assert dl.error_message == "NER 提取超时"
        assert dl.attempt_count == 3
        assert dl.max_attempts == 3
        assert dl.original_item_public_id == "original_item_001"
        assert dl.worker_id == "worker_001"
        assert dl.stream_id == "stream_123"
        assert dl.created_at is not None

    async def test_dead_letter_default_values(self, test_db_session: AsyncSession):
        """测试 TaskDeadLetter 默认值"""
        dl = TaskDeadLetter(
            task_type="scipdf.re.extract",
            payload={},
        )
        test_db_session.add(dl)
        await test_db_session.commit()
        await test_db_session.refresh(dl)

        assert dl.item_type == ""
        assert dl.item_key == ""
        assert dl.error_code == ""
        assert dl.error_message == ""
        assert dl.attempt_count == 0
        assert dl.max_attempts == 3
        assert dl.original_item_public_id == ""
        assert dl.worker_id == ""
        assert dl.stream_id == ""


# ==================== TaskStatus 枚举测试 ====================

class TestTaskStatus:
    """TaskStatus 枚举测试"""

    def test_status_values(self):
        """测试所有状态枚举值"""
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.QUEUED == "queued"
        assert TaskStatus.RUNNING == "running"
        assert TaskStatus.SUCCEEDED == "succeeded"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"
        assert TaskStatus.PARTIAL == "partial"
        assert TaskStatus.PAUSED == "paused"

    def test_status_from_string(self):
        """测试从字符串创建状态"""
        assert TaskStatus("pending") == TaskStatus.PENDING
        assert TaskStatus("running") == TaskStatus.RUNNING
        assert TaskStatus("succeeded") == TaskStatus.SUCCEEDED


# ==================== UTC 时间工具测试 ====================

class TestUtcNow:
    """_utc_now 工具函数测试"""

    def test_utc_now_returns_datetime(self):
        """测试 _utc_now 返回 datetime 对象"""
        now = _utc_now()
        assert isinstance(now, type(_utc_now()))

    def test_utc_now_has_timezone(self):
        """测试 _utc_now 返回的 datetime 带时区信息"""
        now = _utc_now()
        assert now.tzinfo is not None
