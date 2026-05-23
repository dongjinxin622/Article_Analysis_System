"""
Excel 批量提取相关 Schema
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum

from backend.app.core.config import settings


class ExcelExtractionTaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    VALIDATING = "validating"
    PROCESSING = "processing"
    HITL_WAITING = "hitl_waiting"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RowStatus(str, Enum):
    """行数据状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CheckType(str, Enum):
    """检查类型"""
    FIELD = "field"
    QUALITY = "quality"
    FILTER = "filter"
    PROMPT = "prompt"
    EVAL = "eval"


class UserAction(str, Enum):
    """用户动作"""
    CONTINUE = "continue"
    MODIFY = "modify"
    TERMINATE = "terminate"
    ACCEPT = "accept"
    EDIT = "edit"
    REGENERATE = "regenerate"
    USE_DEFAULT = "use_default"
    RETRY = "retry"
    VIEW_FAILED = "view_failed"
    ASK_MORE = "ask_more"  # 用户提问


# ==================== 请求 Schema ====================

class ExcelUploadRequest(BaseModel):
    """Excel 上传请求"""
    pass  # 使用 multipart/form-data


class TaskConfig(BaseModel):
    """任务配置"""
    domain_fields: List[Dict[str, str]] = Field(
        default_factory=list,
        description="领域特定字段定义"
    )
    extract_fields: List[str] = Field(
        default=["related", "institution", "summary", "key_technologies", "application_areas"],
        description="要提取的字段列表"
    )
    llm_model: str = Field(default_factory=lambda: settings.MODEL_NAME, description="LLM 模型")
    hitl_llm_model: str = Field(default_factory=lambda: settings.MODEL_NAME, description="HITL 对话 LLM 模型")
    max_concurrent: int = Field(default=5, ge=1, le=20, description="LLM 调用最大并发数")
    dedup_field: str = Field(default="doi", description="去重字段")
    quality_threshold: float = Field(default=0.6, ge=0.0, le=1.0, description="质量评分阈值")
    enable_hitl: bool = Field(default=True, description="是否启用 HITL")
    enable_smart_hitl: bool = Field(default=True, description="是否启用智能对话 HITL")
    strategy_docx_path: Optional[str] = Field(None, description="策略 Word 文档路径")


class CreateTaskRequest(BaseModel):
    """创建任务请求"""
    task_name: str = Field(..., description="任务名称")
    session_id: str = Field(..., description="WebSocket 会话 ID")
    config: TaskConfig = Field(..., description="任务配置")


class UserInputRequest(BaseModel):
    """用户输入请求（HITL 对话）"""
    session_id: str = Field(..., description="会话 ID")
    input_type: str = Field(..., description="输入类型: text/action")
    text: Optional[str] = Field(None, description="文本内容")
    action: Optional[str] = Field(None, description="快捷动作")
    data: Optional[Dict[str, Any]] = Field(None, description="附加数据")


# ==================== 响应 Schema ====================

class UploadPreviewResponse(BaseModel):
    """上传预览响应"""
    success: bool
    message: str
    session_id: str
    preview: Dict[str, Any] = Field(default_factory=dict)
    # {
    #   "columns": ["DOI", "Title", "Abstract", ...],
    #   "row_count": 100,
    #   "quality_stats": {"missing_doi": 15, "missing_abstract": 3, ...},
    #   "preview_rows": [...],  # 前 10 行数据
    # }


class TaskCreateResponse(BaseModel):
    """任务创建响应"""
    success: bool
    message: str
    task_id: str
    session_id: str
    status: ExcelExtractionTaskStatus
    total_rows: int


class TaskDetailResponse(BaseModel):
    """任务详情响应"""
    model_config = {
        "populate_by_name": True,
        # 不排除 None 值，确保所有字段都包含在响应中
    }

    task_id: str
    task_name: str
    session_id: Optional[str] = Field(default=None, description="WebSocket 会话 ID")
    status: ExcelExtractionTaskStatus
    total_rows: int = 0
    processed_rows: int = 0
    success_rows: int = 0
    failed_rows: int = 0
    progress: float = 0.0
    current_step: Optional[str] = None
    current_node: Optional[str] = None
    pending_check: Optional[CheckType] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    chat_history: List[Dict[str, str]] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    output_file_path: Optional[str] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    items: List[TaskDetailResponse]
    total: int
    page: int
    page_size: int


class RowDetailResponse(BaseModel):
    """行数据详情"""
    id: int
    row_index: int
    unique_key: Optional[str]
    raw_data: Dict[str, Any]
    quality_score: Optional[float]
    quality_issues: Optional[List[str]]
    status: RowStatus
    extraction_result: Optional[Dict[str, Any]]
    error_message: Optional[str]


class RowListResponse(BaseModel):
    """行数据列表响应"""
    items: List[RowDetailResponse]
    total: int
    page: int
    page_size: int


class SuggestedAction(BaseModel):
    """建议动作"""
    value: str = Field(..., description="动作值")
    label: str = Field(..., description="显示文本")
    type: str = Field(default="default", description="按钮类型: primary/success/warning/danger")


class IssueDetails(BaseModel):
    """问题详情"""
    summary: str = Field(..., description="问题摘要")
    details: str = Field(..., description="问题详情")
    affected_count: int = Field(default=0, description="受影响数量")
    affected_records: List[Dict[str, Any]] = Field(default_factory=list, description="受影响记录预览")


# ==================== WebSocket 消息 Schema ====================

class WSProgressMessage(BaseModel):
    """进度消息"""
    type: str = Field(default="progress")
    content: Dict[str, Any]  # {step, progress, message, details}


class WSLLMChatMessage(BaseModel):
    """LLM 对话消息"""
    type: str = Field(default="llm_chat")
    content: Dict[str, Any]  # {role, message, suggested_actions, issue_details}


class WSCompletedMessage(BaseModel):
    """完成消息"""
    type: str = Field(default="completed")
    content: Dict[str, Any]  # {output_file_path, results_summary}


class WSFailedMessage(BaseModel):
    """失败消息"""
    type: str = Field(default="failed")
    content: Dict[str, Any]  # {error}


class WSLogMessage(BaseModel):
    """日志消息"""
    type: str = Field(default="log")
    content: Dict[str, Any]  # {level, node, message}