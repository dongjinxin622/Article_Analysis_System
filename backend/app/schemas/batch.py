"""
批量处理相关 Schema
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class BatchTaskStatus(str, Enum):
    """批量任务状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchTaskRequest(BaseModel):
    """批量任务请求"""
    task_name: str = Field(..., description="任务名称")
    result_ids: List[str] = Field(..., description="处理结果 ID 列表")
    config: Dict[str, Any] = Field(default_factory=dict, description="任务配置")
    enable_hitl: bool = Field(default=False, description="是否启用 HITL")


class BatchTaskResponse(BaseModel):
    """批量任务响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    task_id: str = Field(..., description="任务 ID")
    status: BatchTaskStatus = Field(..., description="任务状态")
    total_count: int = Field(..., description="总数")
    processed_count: int = Field(default=0, description="已处理数量")


class BatchTaskDetail(BaseModel):
    """批量任务详情"""
    task_id: str = Field(..., description="任务 ID")
    task_name: str = Field(..., description="任务名称")
    status: BatchTaskStatus = Field(..., description="任务状态")
    total_count: int = Field(..., description="总数")
    processed_count: int = Field(default=0, description="已处理数量")
    completed_count: int = Field(default=0, description="成功数量")
    failed_count: int = Field(default=0, description="失败数量")
    progress: float = Field(default=0.0, description="进度百分比")
    config: Dict[str, Any] = Field(default_factory=dict, description="任务配置")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    results: List[Dict[str, Any]] = Field(default_factory=list, description="处理结果")
    errors: List[Dict[str, Any]] = Field(default_factory=list, description="错误列表")


class BatchTaskListResponse(BaseModel):
    """批量任务列表响应"""
    items: List[BatchTaskDetail] = Field(default_factory=list, description="任务列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页数量")


class TaskProgress(BaseModel):
    """任务进度"""
    task_id: str = Field(..., description="任务 ID")
    step: str = Field(..., description="当前步骤")
    progress: float = Field(..., description="进度百分比")
    message: str = Field(..., description="进度消息")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    current_file: Optional[str] = Field(None, description="当前处理文件")
    total_files: int = Field(default=0, description="总文件数")


class HITLCheckpoint(BaseModel):
    """HITL 检查点"""
    checkpoint_id: str = Field(..., description="检查点 ID")
    step_name: str = Field(..., description="步骤名称")
    data: Dict[str, Any] = Field(default_factory=dict, description="检查点数据")
    requires_review: bool = Field(default=True, description="是否需要人工审核")
    reviewed: bool = Field(default=False, description="是否已审核")
    review_result: Optional[str] = Field(None, description="审核结果：approve/reject/modify")


class BatchExtractionRequest(BaseModel):
    """批量提取请求"""
    result_ids: List[str] = Field(..., description="处理结果 ID 列表")
    extraction_config: Dict[str, Any] = Field(..., description="提取配置")
    enable_hitl: bool = Field(default=True, description="是否启用 HITL")
    workflow_type: str = Field(default="extraction", description="工作流类型")