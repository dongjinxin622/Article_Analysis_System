"""
异步任务数据模型 — SQLAlchemy 版本

包含 TaskJob（任务主表）、TaskItem（子项表）、TaskDeadLetter（死信表）。
基于 case_one 的 SQLModel 模型，适配 SciPDF 项目的 SQLAlchemy 声明式模型。
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, Enum, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


def _utc_now() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def _new_public_id() -> str:
    """生成新的 public_id。"""
    return str(uuid4())


# ── 任务状态枚举 ──

class TaskStatus(str, enum.Enum):
    """异步任务状态枚举。"""
    PENDING = "pending"       # 待处理
    QUEUED = "queued"         # 已入队
    RUNNING = "running"       # 运行中
    SUCCEEDED = "succeeded"   # 成功
    FAILED = "failed"         # 失败
    CANCELLED = "cancelled"   # 已取消
    PARTIAL = "partial"       # 部分成功
    PAUSED = "paused"         # 已暂停


# ── 任务主表 ──

class TaskJob(Base):
    """任务作业 — 一个 TaskJob 对应一次批量任务提交。"""
    __tablename__ = "task_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String(36), unique=True, nullable=False, index=True, default=_new_public_id)
    task_type = Column(String(100), nullable=False, index=True)
    queue_name = Column(String(100), default="", nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True)
    priority = Column(Integer, default=0, nullable=False)

    total_items = Column(Integer, default=0, nullable=False)
    completed_items = Column(Integer, default=0, nullable=False)
    failed_items = Column(Integer, default=0, nullable=False)

    payload = Column(JSON, default={}, nullable=False)
    result = Column(JSON, default={}, nullable=False)
    error_code = Column(String(100), default="", nullable=False)
    error_message = Column(Text, default="", nullable=False)

    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    created_by = Column(String(36), default="", nullable=False)
    project_public_id = Column(String(36), default="", nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    # 关系
    items = relationship("TaskItem", back_populates="job", cascade="all, delete-orphan", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TaskJob {self.public_id} type={self.task_type} status={self.status}>"


# ── 任务子项表 ──

class TaskItem(Base):
    """任务子项 — TaskJob 下的每个独立执行单元。"""
    __tablename__ = "task_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    public_id = Column(String(36), unique=True, nullable=False, index=True, default=_new_public_id)
    job_id = Column(Integer, ForeignKey("task_jobs.id", ondelete="CASCADE"), nullable=False, index=True)

    task_type = Column(String(100), nullable=False)
    item_type = Column(String(100), default="", nullable=False)
    item_key = Column(String(255), default="", nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True)
    priority = Column(Integer, default=0, nullable=False)

    payload = Column(JSON, default={}, nullable=False)
    result = Column(JSON, default={}, nullable=False)
    error_code = Column(String(100), default="", nullable=False)
    error_message = Column(Text, default="", nullable=False)

    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    worker_id = Column(String(100), default="", nullable=False)

    heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    stream_id = Column(String(100), default="", nullable=False)

    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False)

    # 关系
    job = relationship("TaskJob", back_populates="items")

    def __repr__(self) -> str:
        return f"<TaskItem {self.public_id} type={self.task_type} status={self.status}>"


# ── 死信表 ──

class TaskDeadLetter(Base):
    """任务死信 — 超过最大重试次数的任务子项记录。"""
    __tablename__ = "task_dead_letters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_type = Column(String(100), nullable=False, index=True)
    item_type = Column(String(100), default="", nullable=False)
    item_key = Column(String(255), default="", nullable=False)

    payload = Column(JSON, default={}, nullable=False)
    error_code = Column(String(100), default="", nullable=False)
    error_message = Column(Text, default="", nullable=False)

    attempt_count = Column(Integer, default=0, nullable=False)
    max_attempts = Column(Integer, default=3, nullable=False)
    original_item_public_id = Column(String(36), default="", nullable=False)
    worker_id = Column(String(100), default="", nullable=False)
    stream_id = Column(String(100), default="", nullable=False)

    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False, index=True)

    def __repr__(self) -> str:
        return f"<TaskDeadLetter type={self.task_type} error={self.error_code}>"
