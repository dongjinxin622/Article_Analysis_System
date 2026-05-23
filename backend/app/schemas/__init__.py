"""
Schemas - Pydantic 数据模型
"""
from backend.app.schemas.paper import (
    ProcessingStatus, SectionInfo, PaperUploadResponse,
    ProcessingResult, ResultListItem, ResultDetail, ResultListResponse
)
from backend.app.schemas.ner import (
    NERRequest, EntityInfo, NERResponse, NERResultDetail, NERBatchRequest, NERBatchResponse
)
from backend.app.schemas.re import (
    RERequest, RelationInfo, REResponse, REResultDetail, RelationGraph
)
from backend.app.schemas.batch import (
    BatchTaskStatus, BatchTaskRequest, BatchTaskResponse,
    BatchTaskDetail, TaskProgress, HITLCheckpoint, BatchExtractionRequest
)
from backend.app.schemas.user import (
    UserCreate, UserLogin, Token, UserResponse, LoginResponse, UserUpdate
)
from backend.app.schemas.domain import (
    DomainConfigResponse, DomainListResponse, TechRouteRequest,
    TechRouteResponse, ExpSchemeRequest, ExpSchemeResponse,
    JcSearchRequest, JcSearchResponse, JcIndicator, JcCompareRequest, JcCompareResponse
)

__all__ = [
    # Paper
    "ProcessingStatus", "SectionInfo", "PaperUploadResponse",
    "ProcessingResult", "ResultListItem", "ResultDetail", "ResultListResponse",
    # NER
    "NERRequest", "EntityInfo", "NERResponse", "NERResultDetail", "NERBatchRequest", "NERBatchResponse",
    # RE
    "RERequest", "RelationInfo", "REResponse", "REResultDetail", "RelationGraph",
    # Batch
    "BatchTaskStatus", "BatchTaskRequest", "BatchTaskResponse",
    "BatchTaskDetail", "TaskProgress", "HITLCheckpoint", "BatchExtractionRequest",
    # User
    "UserCreate", "UserLogin", "Token", "UserResponse", "LoginResponse", "UserUpdate",
    # Domain
    "DomainConfigResponse", "DomainListResponse", "TechRouteRequest",
    "TechRouteResponse", "ExpSchemeRequest", "ExpSchemeResponse",
    "JcSearchRequest", "JcSearchResponse", "JcIndicator", "JcCompareRequest", "JcCompareResponse"
]