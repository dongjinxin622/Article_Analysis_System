"""
论文处理相关 Schema
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class ProcessingStatus(str, Enum):
    """处理状态枚举"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SectionInfo(BaseModel):
    """章节信息"""
    heading: str = Field(..., description="章节标题")
    text: str = Field(..., description="章节内容")


class PaperUploadResponse(BaseModel):
    """论文上传响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    result_id: Optional[str] = Field(None, description="处理结果ID")
    file_name: str = Field(..., description="文件名")
    title: Optional[str] = Field(None, description="论文标题")
    doi: Optional[str] = Field(None, description="DOI")


class ProcessingResult(BaseModel):
    """处理结果基础信息"""
    result_id: str = Field(..., description="唯一标识符（DOI 或文件名）")
    file_name: str = Field(..., description="原始 PDF 文件名")
    title: Optional[str] = Field(None, description="论文标题")
    doi: Optional[str] = Field(None, description="DOI 标识")
    abstract: Optional[str] = Field(None, description="摘要内容")
    status: ProcessingStatus = Field(default=ProcessingStatus.PENDING, description="处理状态")
    error_message: Optional[str] = Field(None, description="错误信息")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    processed_at: Optional[datetime] = Field(None, description="处理完成时间")


class ResultListItem(ProcessingResult):
    """结果列表项"""
    ner_status: Optional[ProcessingStatus] = Field(None, description="NER 处理状态")
    re_status: Optional[ProcessingStatus] = Field(None, description="RE 处理状态")


class ResultDetail(ProcessingResult):
    """结果详情"""
    sections: List[SectionInfo] = Field(default_factory=list, description="章节列表")
    references: List[Dict[str, Any]] = Field(default_factory=list, description="参考文献")
    figures: List[Dict[str, Any]] = Field(default_factory=list, description="图表信息")
    result_pkl_path: Optional[str] = Field(None, description="pkl 文件路径")
    result_json_path: Optional[str] = Field(None, description="json 文件路径")


class ResultListResponse(BaseModel):
    """结果列表响应"""
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页")
    page_size: int = Field(..., description="每页数量")
    items: List[ResultListItem] = Field(default_factory=list, description="结果列表")


class PaperParseRequest(BaseModel):
    """论文解析请求"""
    file_path: str = Field(..., description="文件路径")
    use_grobid: bool = Field(default=True, description="是否使用 GROBID")
    fallback_to_pymupdf: bool = Field(default=True, description="GROBID 失败时是否回退到 PyMuPDF")