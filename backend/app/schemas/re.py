"""
关系抽取相关 Schema
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class RERequest(BaseModel):
    """关系抽取请求"""
    ner_id: str = Field(..., description="NER 结果 ID")
    query_file: str = Field(..., description="Prompt 模板文件路径")
    task_name: str = Field(default="RE_task", description="任务名称")


class RelationInfo(BaseModel):
    """关系信息"""
    relation_type: str = Field(..., description="关系类型")
    source_type: str = Field(..., description="源实体类别")
    source_entity: str = Field(..., description="源实体")
    target_type: str = Field(..., description="目标实体类别")
    target_entity: str = Field(..., description="目标实体")
    effect: Optional[str] = Field(None, description="影响性质：neutral/positive/negative")
    supporting_sentence: Optional[str] = Field(None, description="支持句子")
    confidence: Optional[float] = Field(None, description="置信度")


class REResponse(BaseModel):
    """关系抽取响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    re_id: Optional[str] = Field(None, description="关系抽取结果 ID")
    ner_id: str = Field(..., description="关联的 NER 结果 ID")
    relation_count: Optional[int] = Field(None, description="识别关系数量")
    re_json_path: Optional[str] = Field(None, description="JSON 结果路径")
    re_excel_path: Optional[str] = Field(None, description="Excel 结果路径")


class REResultDetail(BaseModel):
    """RE 结果详情"""
    re_id: str = Field(..., description="RE 结果 ID")
    ner_id: str = Field(..., description="关联的 NER 结果 ID")
    result_id: str = Field(..., description="关联的处理结果 ID")
    relations: List[RelationInfo] = Field(default_factory=list, description="关系列表")
    relation_count: int = Field(..., description="关系数量")
    status: str = Field(..., description="处理状态")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    processed_at: Optional[datetime] = Field(None, description="处理完成时间")


class RelationGraph(BaseModel):
    """关系图谱"""
    nodes: List[Dict[str, Any]] = Field(default_factory=list, description="节点列表")
    edges: List[Dict[str, Any]] = Field(default_factory=list, description="边列表")