"""
领域分析相关 Schema
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime


class DomainConfigResponse(BaseModel):
    """领域配置响应"""
    domain_name: str = Field(..., description="领域名称")
    description: Optional[str] = Field(None, description="领域描述")
    entity_types: Dict[str, str] = Field(default_factory=dict, description="实体类型定义")
    relation_types: Dict[str, str] = Field(default_factory=dict, description="关系类型定义")
    prompt_templates: Dict[str, str] = Field(default_factory=dict, description="Prompt 模板")
    is_active: bool = Field(default=True, description="是否激活")


class DomainListResponse(BaseModel):
    """领域列表响应"""
    domains: List[str] = Field(default_factory=list, description="领域列表")
    count: int = Field(..., description="数量")


class TechRouteRequest(BaseModel):
    """技术路线分析请求"""
    ner_id: str = Field(..., description="NER 结果 ID")
    domain: str = Field(default="material", description="领域标识")
    top_k: int = Field(default=10, ge=1, le=50, description="检索相似论文数量")


class TechRouteResponse(BaseModel):
    """技术路线分析响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    profile_text: Optional[str] = Field(None, description="技术路线描述")
    profile_id: Optional[str] = Field(None, description="技术路线 ID")
    similar_papers: List[Dict[str, Any]] = Field(default_factory=list, description="相似论文列表")


class ExpSchemeRequest(BaseModel):
    """实验方案分析请求"""
    ner_id: str = Field(..., description="NER 结果 ID")
    domain: str = Field(default="material", description="领域标识")
    top_k: int = Field(default=10, ge=1, le=50, description="检索相似论文数量")


class ExpSchemeResponse(BaseModel):
    """实验方案分析响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    scheme_text: Optional[str] = Field(None, description="实验方案描述")
    scheme_id: Optional[str] = Field(None, description="实验方案 ID")
    dimensions: Dict[str, Any] = Field(default_factory=dict, description="8维度分析")
    similar_papers: List[Dict[str, Any]] = Field(default_factory=list, description="相似论文列表")


class JcSearchRequest(BaseModel):
    """Jc 指标搜索请求"""
    ner_id: str = Field(..., description="NER 结果 ID")
    domain: str = Field(default="material", description="领域标识")
    temperature: Optional[float] = Field(None, description="温度条件")
    magnetic_field: Optional[float] = Field(None, description="磁场条件")
    angle: Optional[float] = Field(None, description="角度条件")
    top_k: int = Field(default=10, ge=1, le=50, description="检索数量")


class JcIndicator(BaseModel):
    """Jc 指标"""
    jc_value: float = Field(..., description="Jc 值")
    unit: str = Field(default="A/cm²", description="单位")
    temperature: Optional[float] = Field(None, description="温度")
    magnetic_field: Optional[float] = Field(None, description="磁场")
    angle: Optional[float] = Field(None, description="角度")
    source_paper: Optional[str] = Field(None, description="来源论文")
    source_sentence: Optional[str] = Field(None, description="来源句子")


class JcSearchResponse(BaseModel):
    """Jc 指标搜索响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    indicators: List[Dict[str, Any]] = Field(default_factory=list, description="Jc 指标列表")
    count: int = Field(..., description="数量")


class JcCompareRequest(BaseModel):
    """Jc 对比分析请求"""
    ner_ids: List[str] = Field(..., description="NER 结果 ID 列表")
    domain: str = Field(default="material", description="领域标识")


class JcCompareResponse(BaseModel):
    """Jc 对比分析响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    comparison_table: List[Dict[str, Any]] = Field(default_factory=list, description="对比表格")
    analysis_report: Optional[str] = Field(None, description="分析报告")