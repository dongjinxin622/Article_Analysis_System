"""
自定义异常定义
"""
from fastapi import HTTPException, status


class PDFProcessingError(HTTPException):
    """PDF 处理错误"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"PDF 处理失败: {detail}"
        )


class NERProcessingError(HTTPException):
    """NER 处理错误"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"NER 处理失败: {detail}"
        )


class REProcessingError(HTTPException):
    """关系抽取处理错误"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"关系抽取失败: {detail}"
        )


class FileNotFoundError(HTTPException):
    """文件未找到错误"""
    def __init__(self, file_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"文件不存在: {file_id}"
        )


class ResultNotFoundError(HTTPException):
    """结果未找到错误"""
    def __init__(self, result_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"处理结果不存在: {result_id}"
        )


class NERResultNotFoundError(HTTPException):
    """NER 结果未找到错误"""
    def __init__(self, ner_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"NER 结果不存在: {ner_id}"
        )


class ValidationError(HTTPException):
    """验证错误"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )


class LLMServiceError(HTTPException):
    """LLM 服务错误"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"LLM 服务不可用: {detail}"
        )


class MilvusConnectionError(HTTPException):
    """Milvus 连接错误"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"向量数据库连接失败: {detail}"
        )


class DatabaseError(HTTPException):
    """数据库错误"""
    def __init__(self, detail: str):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据库错误: {detail}"
        )


class DomainNotFoundError(HTTPException):
    """领域未找到错误"""
    def __init__(self, domain: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"领域分析器不存在: {domain}"
        )