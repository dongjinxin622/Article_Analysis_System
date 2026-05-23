"""
NER 相关 Schema
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class NERRequest(BaseModel):
    """NER 请求"""
    result_id: str = Field(..., description="处理结果 ID")
    skip_introduction: bool = Field(default=True, description="是否跳过 introduction 部分")
    sentence_group_size: int = Field(default=5, ge=1, le=20, description="每组句子数量（默认 5，范围 1-20）")
    query_file: str = Field(..., description="Prompt 模板文件路径（必填）")
    task_name: str = Field(default="NER_task", description="任务名称")


class EntityInfo(BaseModel):
    """实体信息"""
    entity_type: str = Field(..., description="实体类型")
    entity_text: str = Field(..., description="实体文本")
    start_pos: int = Field(..., description="起始位置")
    end_pos: int = Field(..., description="结束位置")
    confidence: Optional[float] = Field(None, description="置信度")
    section_idx: Optional[int] = Field(None, description="章节索引")
    group_idx: Optional[int] = Field(None, description="分组索引")
    sentence_idx: Optional[int] = Field(None, description="句子索引")


class NERResponse(BaseModel):
    """NER 响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    ner_id: Optional[str] = Field(None, description="NER 结果 ID")
    result_id: str = Field(..., description="关联的处理结果 ID")
    entity_count: Optional[int] = Field(None, description="识别实体数量")
    ner_json_path: Optional[str] = Field(None, description="JSON 结果路径")
    ner_excel_path: Optional[str] = Field(None, description="Excel 结果路径")
    ner_pkl_path: Optional[str] = Field(None, description="PKL 结果路径")
    group_count: Optional[int] = Field(None, description="分组数量")


class NERResultDetail(BaseModel):
    """NER 结果详情"""
    ner_id: str = Field(..., description="NER 结果 ID")
    result_id: str = Field(..., description="关联的处理结果 ID")
    entities: List[EntityInfo] = Field(default_factory=list, description="实体列表")
    entity_count: int = Field(..., description="实体数量")
    status: str = Field(..., description="处理状态")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    processed_at: Optional[datetime] = Field(None, description="处理完成时间")


class NERResultListItem(BaseModel):
    """NER 结果列表项"""
    ner_id: str = Field(..., description="NER 结果 ID")
    result_id: str = Field(..., description="关联的处理结果 ID")
    entity_count: int = Field(..., description="实体数量")
    status: str = Field(..., description="处理状态")
    re_status: Optional[str] = Field(None, description="RE 处理状态")
    created_at: Optional[datetime] = Field(None, description="创建时间")


class NERResultListResponse(BaseModel):
    """NER 结果列表响应"""
    total: int = Field(..., description="总数")
    items: List[NERResultListItem] = Field(default_factory=list, description="结果列表")


class NERBatchRequest(BaseModel):
    """批量 NER 请求"""
    result_ids: List[str] = Field(..., description="处理结果 ID 列表")
    query_file: str = Field(..., description="Prompt 模板文件路径")
    skip_introduction: bool = Field(default=True)
    sentence_group_size: int = Field(default=5)


class NERBatchResponse(BaseModel):
    """批量 NER 响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    task_id: str = Field(..., description="任务 ID")
    total_count: int = Field(..., description="总数")
    results: List[NERResponse] = Field(default_factory=list, description="结果列表")