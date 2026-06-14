"""
异步任务 Schema 测试

验证 Pydantic Schema 的字段校验、默认值和序列化行为。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.models.tasks import TaskStatus
from backend.app.schemas.tasks import (
    TaskItemCreate,
    TaskJobCreate,
    TaskStatusUpdate,
    TaskItemRead,
    TaskJobRead,
    TaskJobDetail,
    TaskJobPage,
    TaskStreamMessage,
    TaskStreamRecord,
)
from datetime import datetime, timezone


# ==================== TaskItemCreate 测试 ====================

class TestTaskItemCreate:
    """TaskItemCreate Schema 测试"""

    def test_create_basic(self):
        """测试基本创建"""
        item = TaskItemCreate(
            item_type="single",
            payload={"key": "value"},
        )
        assert item.item_type == "single"
        assert item.payload == {"key": "value"}
        assert item.priority == 0  # 默认值
        assert item.max_attempts == 3  # 默认值

    def test_create_with_all_fields(self):
        """测试全字段创建"""
        scheduled = datetime(2026, 6, 13, 12, 0, 0, tzinfo=timezone.utc)
        item = TaskItemCreate(
            item_type="batch",
            item_key="unique_key_001",
            priority=10,
            max_attempts=5,
            payload={"data": [1, 2, 3]},
            scheduled_at=scheduled,
        )
        assert item.item_type == "batch"
        assert item.item_key == "unique_key_001"
        assert item.priority == 10
        assert item.max_attempts == 5
        assert item.payload == {"data": [1, 2, 3]}
        assert item.scheduled_at == scheduled

    def test_max_attempts_validation(self):
        """测试 max_attempts 范围校验"""
        # 正常范围
        item = TaskItemCreate(max_attempts=1)
        assert item.max_attempts == 1

        item = TaskItemCreate(max_attempts=100)
        assert item.max_attempts == 100

        # 超出范围
        with pytest.raises(ValidationError):
            TaskItemCreate(max_attempts=0)

        with pytest.raises(ValidationError):
            TaskItemCreate(max_attempts=101)

    def test_item_type_max_length(self):
        """测试 item_type 最大长度"""
        # 正常长度
        item = TaskItemCreate(item_type="a" * 100)
        assert len(item.item_type) == 100

        # 超出长度
        with pytest.raises(ValidationError):
            TaskItemCreate(item_type="a" * 101)


# ==================== TaskJobCreate 测试 ====================

class TestTaskJobCreate:
    """TaskJobCreate Schema 测试"""

    def test_create_basic(self):
        """测试基本创建"""
        job = TaskJobCreate(
            task_type="scipdf.pdf.parse",
            payload={"file": "test.pdf"},
        )
        assert job.task_type == "scipdf.pdf.parse"
        assert job.queue_name == "default"
        assert job.created_by == ""
        assert job.project_public_id == ""
        assert job.priority == 0
        assert job.payload == {"file": "test.pdf"}
        assert job.items == []

    def test_create_with_items(self):
        """测试带子项的创建"""
        job = TaskJobCreate(
            task_type="scipdf.ner.batch",
            items=[
                TaskItemCreate(item_type="single", payload={"id": 1}),
                TaskItemCreate(item_type="single", payload={"id": 2}),
            ],
        )
        assert len(job.items) == 2
        assert job.items[0].payload == {"id": 1}
        assert job.items[1].payload == {"id": 2}

    def test_task_type_min_length(self):
        """测试 task_type 最小长度"""
        # 空字符串应失败
        with pytest.raises(ValidationError):
            TaskJobCreate(task_type="")

        # 正常字符串
        job = TaskJobCreate(task_type="a")
        assert job.task_type == "a"

    def test_queue_name_max_length(self):
        """测试 queue_name 最大长度"""
        # 正常长度
        job = TaskJobCreate(task_type="test", queue_name="a" * 120)
        assert len(job.queue_name) == 120

        # 超出长度
        with pytest.raises(ValidationError):
            TaskJobCreate(task_type="test", queue_name="a" * 121)


# ==================== TaskStatusUpdate 测试 ====================

class TestTaskStatusUpdate:
    """TaskStatusUpdate Schema 测试"""

    def test_update_success(self):
        """测试成功状态更新"""
        update = TaskStatusUpdate(
            status=TaskStatus.SUCCEEDED,
            result={"count": 100},
        )
        assert update.status == TaskStatus.SUCCEEDED
        assert update.result == {"count": 100}
        assert update.error_code == ""
        assert update.error_message == ""

    def test_update_failed(self):
        """测试失败状态更新"""
        update = TaskStatusUpdate(
            status=TaskStatus.FAILED,
            error_code="parse_error",
            error_message="PDF 解析失败",
            worker_id="worker_001",
        )
        assert update.status == TaskStatus.FAILED
        assert update.error_code == "parse_error"
        assert update.error_message == "PDF 解析失败"
        assert update.worker_id == "worker_001"


# ==================== TaskStreamMessage 测试 ====================

class TestTaskStreamMessage:
    """TaskStreamMessage Schema 测试"""

    def test_create_message(self):
        """测试创建 Stream 消息"""
        now = datetime.now(timezone.utc)
        msg = TaskStreamMessage(
            job_public_id="job_001",
            item_public_id="item_001",
            task_type="scipdf.pdf.parse",
            payload={"file": "test.pdf"},
            created_at=now,
        )
        assert msg.event == "task.item.queued"  # 默认事件
        assert msg.job_public_id == "job_001"
        assert msg.item_public_id == "item_001"
        assert msg.task_type == "scipdf.pdf.parse"
        assert msg.queue_name == "default"
        assert msg.priority == 0

    def test_message_min_length_validation(self):
        """测试消息字段最小长度校验"""
        # 空 public_id 应失败
        with pytest.raises(ValidationError):
            TaskStreamMessage(
                job_public_id="",
                item_public_id="",
                task_type="",
                created_at=datetime.now(timezone.utc),
            )


# ==================== TaskJobPage 测试 ====================

class TestTaskJobPage:
    """TaskJobPage 分页响应测试"""

    def test_page_empty(self):
        """测试空分页"""
        page = TaskJobPage(data=[], total=0, page=1, limit=20)
        assert page.total == 0
        assert len(page.data) == 0
        assert page.page == 1
        assert page.limit == 20

    def test_page_with_data(self):
        """测试带数据的分页"""
        jobs = []
        for i in range(5):
            job = TaskJobRead(
                id=i + 1,
                public_id=f"job_{i:03d}",
                task_type=f"scipdf.type_{i}",
                queue_name="default",
                status=TaskStatus.PENDING,
                created_by="",
                project_public_id="",
                priority=0,
                total_items=0,
                completed_items=0,
                failed_items=0,
                payload={},
                result={},
                error_code="",
                error_message="",
                scheduled_at=None,
                started_at=None,
                finished_at=None,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            jobs.append(job)

        page = TaskJobPage(data=jobs, total=5, page=1, limit=20)
        assert page.total == 5
        assert len(page.data) == 5
        assert page.data[0].task_type == "scipdf.type_0"


# ==================== TaskJobDetail 测试 ====================

class TestTaskJobDetail:
    """TaskJobDetail 详情响应测试"""

    def test_detail_without_items(self):
        """测试无子项的详情"""
        job = TaskJobRead(
            id=1,
            public_id="job_001",
            task_type="scipdf.pdf.parse",
            queue_name="default",
            status=TaskStatus.PENDING,
            created_by="",
            project_public_id="",
            priority=0,
            total_items=0,
            completed_items=0,
            failed_items=0,
            payload={},
            result={},
            error_code="",
            error_message="",
            scheduled_at=None,
            started_at=None,
            finished_at=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        detail = TaskJobDetail(**job.model_dump())
        assert detail.items == []

    def test_detail_with_items(self):
        """测试带子项的详情"""
        job_data = {
            "id": 1,
            "public_id": "job_001",
            "task_type": "scipdf.pdf.parse",
            "queue_name": "default",
            "status": TaskStatus.PENDING,
            "created_by": "",
            "project_public_id": "",
            "priority": 0,
            "total_items": 2,
            "completed_items": 0,
            "failed_items": 0,
            "payload": {},
            "result": {},
            "error_code": "",
            "error_message": "",
            "scheduled_at": None,
            "started_at": None,
            "finished_at": None,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }
        items_data = [
            {
                "id": 1,
                "public_id": "item_001",
                "job_id": 1,
                "task_type": "scipdf.pdf.parse",
                "item_type": "single",
                "item_key": None,
                "status": TaskStatus.PENDING,
                "priority": 0,
                "attempt_count": 0,
                "max_attempts": 3,
                "worker_id": "",
                "payload": {},
                "result": {},
                "error_code": "",
                "error_message": "",
                "scheduled_at": None,
                "started_at": None,
                "heartbeat_at": None,
                "finished_at": None,
                "stream_id": "",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        ]
        detail = TaskJobDetail(**job_data, items=items_data)
        assert len(detail.items) == 1
        assert detail.items[0].public_id == "item_001"
