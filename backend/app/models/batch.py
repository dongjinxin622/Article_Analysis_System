"""
批量任务数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class BatchTask(Base):
    """批量任务表"""
    __tablename__ = "batch_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    task_name = Column(String(255))
    task_type = Column(String(50))  # ner_batch, re_batch, extraction_workflow
    result_ids = Column(JSON)  # 存储处理结果 ID 列表
    config = Column(JSON)  # 任务配置
    enable_hitl = Column(Integer, default=0)  # 是否启用 HITL
    status = Column(String(50), default="pending")  # pending/processing/completed/failed/cancelled
    total_count = Column(Integer, default=0)
    processed_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    progress = Column(Float, default=0.0)
    current_step = Column(String(100))  # 当前步骤名称
    error_message = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TaskLog(Base):
    """任务日志表"""
    __tablename__ = "task_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), ForeignKey("batch_tasks.task_id", ondelete="CASCADE"))
    step_name = Column(String(100))
    action = Column(String(50))  # start/complete/error/review
    message = Column(Text)
    data = Column(JSON)  # 日志数据
    created_at = Column(DateTime, default=datetime.now)


class HITLCheckpoint(Base):
    """HITL 检查点表"""
    __tablename__ = "hitl_checkpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    checkpoint_id = Column(String(255), unique=True, nullable=False, index=True)
    task_id = Column(String(255), ForeignKey("batch_tasks.task_id", ondelete="CASCADE"))
    step_name = Column(String(100))
    checkpoint_data = Column(JSON)
    requires_review = Column(Integer, default=1)
    reviewed = Column(Integer, default=0)
    review_result = Column(String(50))  # approve/reject/modify
    review_comment = Column(Text)
    reviewer_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)
    reviewed_at = Column(DateTime)