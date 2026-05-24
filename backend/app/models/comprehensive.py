"""
综合分析任务 PostgreSQL 持久化模型

Redis 中任务结果有 2 小时 TTL，任务完成后同步写入 PostgreSQL 以实现永久存储。
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON

from backend.app.models.base import Base


class ComprehensiveTask(Base):
    """综合分析任务结果表"""
    __tablename__ = "comprehensive_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), unique=True, nullable=False, index=True, comment="任务 UUID")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True, comment="用户 ID")
    status = Column(String(50), default="pending", comment="状态: pending/running/completed/failed")
    progress = Column(Integer, default=0, comment="进度 0-100")
    current_step = Column(String(100), comment="当前步骤")
    message = Column(Text, comment="状态消息")
    result = Column(JSON, comment="完整分析结果")
    error = Column(Text, comment="错误信息")
    params = Column(JSON, comment="任务参数")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")
    completed_at = Column(DateTime, comment="完成时间")
