# -*- coding: utf-8 -*-
"""
任务状态相关 Schema
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="状态")
    progress: int = Field(default=0, description="进度（0-100）")
    message: str = Field(default="", description="消息")
    stage: Optional[str] = Field(None, description="当前阶段")
    result: Optional[Dict[str, Any]] = Field(None, description="结果")
    error: Optional[str] = Field(None, description="错误信息")
    created_at: Optional[float] = Field(None, description="创建时间戳")
    updated_at: Optional[float] = Field(None, description="更新时间戳")


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[Dict[str, Any]] = Field(default_factory=list, description="任务列表")
    count: int = Field(..., description="返回数量")
    total: int = Field(..., description="总数")


class TaskCancelResponse(BaseModel):
    """任务取消响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="状态")
    message: str = Field(..., description="消息")


class TaskCreateRequest(BaseModel):
    """任务创建请求"""
    file_path: Optional[str] = Field(None, description="PDF 文件路径")
    file_paths: Optional[List[str]] = Field(None, description="PDF 文件路径列表")
    result_id: Optional[str] = Field(None, description="PDF 处理结果 ID")
    ner_id: Optional[str] = Field(None, description="NER 结果 ID")
    config_id: Optional[int] = Field(None, description="Prompt 配置 ID")
    domain: Optional[str] = Field(None, description="领域标识")
    options: Optional[Dict[str, Any]] = Field(None, description="处理选项")


class TaskCreateResponse(BaseModel):
    """任务创建响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(default="pending", description="状态")
    message: str = Field(..., description="消息")