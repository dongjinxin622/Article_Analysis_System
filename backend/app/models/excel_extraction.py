"""
Excel 批量提取任务数据库模型
用于处理 Excel 题录数据的 LLM 评估提取（智能对话模式）
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON, Float, Boolean
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class ExcelExtractionTask(Base):
    """Excel 批量提取任务表"""
    __tablename__ = "excel_extraction_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    task_name = Column(String(255))
    user_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String(64), index=True)  # WebSocket 会话 ID

    # 输入文件信息
    original_filenames = Column(JSON)  # 上传的 Excel 文件名列表
    strategy_file_path = Column(String(500))  # 策略 Word 文档路径（可选）

    # 任务状态
    # pending -> validating -> processing -> hitl_waiting -> exporting -> completed/failed/cancelled
    status = Column(String(50), default="pending")

    # 进度跟踪
    total_rows = Column(Integer, default=0)  # 总数据行数（去重后）
    processed_rows = Column(Integer, default=0)
    success_rows = Column(Integer, default=0)
    failed_rows = Column(Integer, default=0)
    progress = Column(Float, default=0.0)
    current_step = Column(String(100))
    error_message = Column(Text)

    # 配置
    config = Column(JSON)
    # {
    #   "domain_fields": [{"name": "...", "description": "..."}],
    #   "llm_model": "qwen-plus",
    #   "max_concurrent": 5,
    #   "dedup_field": "doi",
    #   "quality_threshold": 0.6,
    #   "enable_hitl": false,
    #   "extract_fields": ["related", "institution", "summary", ...]
    # }

    # LangGraph 工作流状态（用于断点续传）
    workflow_state = Column(JSON)  # AgentState 的 JSON 序列化
    current_node = Column(String(100))  # 当前执行的节点
    pending_check = Column(String(50))  # 当前待审核的检查类型

    # 对话历史（LLM HITL）
    chat_history = Column(JSON)  # [{"role": "assistant/user", "content": "..."}]
    hitl_turns = Column(Integer, default=0)  # HITL 对话轮次

    # 输出文件路径
    output_file_path = Column(String(500))

    # 时间戳
    created_at = Column(DateTime, default=datetime.now)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ExcelExtractionRow(Base):
    """Excel 提取行数据表 - 跟踪每行的处理状态和结果"""
    __tablename__ = "excel_extraction_rows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), ForeignKey("excel_extraction_tasks.task_id", ondelete="CASCADE"))
    row_index = Column(Integer)  # 原始 Excel 行号

    # 原始数据
    raw_data = Column(JSON)
    # {"doi": "...", "authors": "...", "title": "...", "abstract": "...", ...}

    # 唯一标识（用于去重）
    unique_key = Column(String(255), index=True)  # 通常是 DOI

    # 质量评分
    quality_score = Column(Float)  # 0.0 - 1.0
    quality_issues = Column(JSON)  # ["missing_abstract", "short_title", ...]

    # 处理状态
    # pending -> processing -> completed -> failed
    status = Column(String(50), default="pending")

    # LLM 提取结果
    extraction_result = Column(JSON)
    # {
    #   "related": true/false,
    #   "institution": "...",
    #   "summary": "...",
    #   "key_technologies": [...],
    #   "application_areas": [...],
    #   "domain_specific": {...},
    # }

    # 错误信息
    error_message = Column(Text)
    retry_count = Column(Integer, default=0)

    # 时间戳
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class ExcelExtractionSession(Base):
    """Excel 提取会话表 - 用于 WebSocket HITL 对话"""
    __tablename__ = "excel_extraction_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(64), unique=True, nullable=False, index=True)
    task_id = Column(String(64), ForeignKey("excel_extraction_tasks.task_id"))

    # WebSocket 连接状态
    is_connected = Column(Boolean, default=False)
    last_ping = Column(DateTime)

    # HITL 状态
    hitl_pending = Column(Boolean, default=False)  # 是否等待用户响应
    hitl_request = Column(JSON)  # 当前 HITL 请求内容
    hitl_response = Column(JSON)  # 用户响应

    # 时间戳
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)