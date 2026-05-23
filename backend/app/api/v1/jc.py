"""
Jc 数据库搜索 API
无需 NER ID，直接搜索云端 MySQL 历史数据
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from pydantic import BaseModel, Field

from backend.app.services.jc_database_service import get_jc_db_service
from backend.app.api.deps import get_current_user_required

router = APIRouter(prefix="/jc")


# ========== Schemas ==========

class JcDatabaseSearchRequest(BaseModel):
    """Jc 数据库搜索请求"""
    temperature: Optional[float] = Field(None, description="温度条件 (K)")
    magnetic_field: Optional[float] = Field(None, description="磁场条件 (T)")
    angle: Optional[float] = Field(None, description="角度条件 (deg)")
    top_k: int = Field(default=50, ge=1, le=200, description="返回数量")
    min_jc: Optional[float] = Field(None, description="最小 Jc 值筛选")
    temp_tolerance: float = Field(default=5.0, description="温度容差 (K)")
    field_tolerance: float = Field(default=1.0, description="磁场容差 (T)")
    angle_tolerance: float = Field(default=10.0, description="角度容差 (deg)")


class JcDatabaseRankRequest(BaseModel):
    """Jc 数据库排名请求"""
    target_doi: str = Field(..., description="目标论文 DOI")
    temperature: Optional[float] = Field(None, description="温度条件 (K)")
    magnetic_field: Optional[float] = Field(None, description="磁场条件 (T)")
    angle: Optional[float] = Field(None, description="角度条件 (deg)")
    temp_tolerance: float = Field(default=5.0, description="温度容差 (K)")
    field_tolerance: float = Field(default=1.0, description="磁场容差 (T)")
    angle_tolerance: float = Field(default=10.0, description="角度容差 (deg)")


class JcDatabaseSearchResult(BaseModel):
    """Jc 数据库搜索结果"""
    doi: str = Field(..., description="DOI")
    title: Optional[str] = Field(None, description="标题")
    temperature_K: Optional[float] = Field(None, description="温度 (K)")
    magnetic_field_T: Optional[float] = Field(None, description="磁场 (T)")
    angle_deg: Optional[float] = Field(None, description="角度 (deg)")
    jc_value: Optional[float] = Field(None, description="Jc 值")
    jc_unit: str = Field(default="A/cm²", description="Jc 单位")
    class1_temp_field: Optional[str] = Field(None, description="温度磁场分类")
    method: Optional[str] = Field(None, description="测量方法")
    thickness: Optional[str] = Field(None, description="薄膜厚度")
    substrate: Optional[str] = Field(None, description="基底")


class JcDatabaseSearchResponse(BaseModel):
    """Jc 数据库搜索响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    search_conditions: dict = Field(default_factory=dict, description="搜索条件")
    results: List[JcDatabaseSearchResult] = Field(default_factory=list, description="结果列表")
    count: int = Field(..., description="结果数量")


class JcDatabaseRankResponse(BaseModel):
    """Jc 数据库排名响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    target_doi: str = Field(..., description="目标 DOI")
    target_jc_max: Optional[float] = Field(None, description="目标最大 Jc")
    target_rank: Optional[int] = Field(None, description="目标排名")
    total_papers: int = Field(default=0, description="总论文数")
    best_jc_max: Optional[float] = Field(None, description="最高 Jc")
    rank_percentile: Optional[float] = Field(None, description="百分位排名")
    top_10: List[dict] = Field(default_factory=list, description="前10名")
    search_conditions: dict = Field(default_factory=dict, description="搜索条件")


class JcDatabaseStatsResponse(BaseModel):
    """Jc 数据库统计响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    statistics: dict = Field(default_factory=dict, description="统计信息")


# ========== API Endpoints ==========

@router.get("/stats", response_model=JcDatabaseStatsResponse, summary="获取数据库统计")
async def get_jc_database_stats(
    user = Depends(get_current_user_required)
):
    """
    获取 Jc 数据库统计信息
    - 总记录数
    -唯一 DOI 数
    - 温度/磁场/Jc 范围
    """
    service = get_jc_db_service()
    result = await service.get_jc_statistics()

    return JcDatabaseStatsResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        statistics=result.get("statistics", {})
    )


@router.post("/search", response_model=JcDatabaseSearchResponse, summary="搜索Jc数据库")
async def search_jc_database(
    request: JcDatabaseSearchRequest,
    user = Depends(get_current_user_required)
):
    """
    搜索云端 MySQL Jc 历史数据

    - **temperature**: 目标温度 (K)，范围: 0-200K
    - **magnetic_field**: 目标磁场 (T)，范围: 0-80T
    - **angle**: 目标角度 (deg)
    - **top_k**: 返回数量
    - **min_jc**: 最小 Jc 筛选
    - **tolerances**: 各条件容差

    无需 NER ID，直接搜索历史数据
    """
    # 输入范围验证
    if request.temperature is not None:
        if request.temperature < 0:
            raise HTTPException(status_code=400, detail="温度不能为负数")
        if request.temperature > 200:
            raise HTTPException(status_code=400, detail="温度超出范围，最大允许 200K")

    if request.magnetic_field is not None:
        if request.magnetic_field < 0:
            raise HTTPException(status_code=400, detail="磁场不能为负数")
        if request.magnetic_field > 80:
            raise HTTPException(status_code=400, detail="磁场超出范围，最大允许 80T")

    if request.angle is not None and request.angle < 0:
        raise HTTPException(status_code=400, detail="角度不能为负数")

    if request.min_jc is not None and request.min_jc < 0:
        raise HTTPException(status_code=400, detail="最小Jc值不能为负数")

    service = get_jc_db_service()
    result = await service.search_by_conditions(
        temperature=request.temperature,
        magnetic_field=request.magnetic_field,
        angle=request.angle,
        top_k=request.top_k,
        min_jc=request.min_jc,
        temp_tolerance=request.temp_tolerance,
        field_tolerance=request.field_tolerance,
        angle_tolerance=request.angle_tolerance
    )

    return JcDatabaseSearchResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        search_conditions=result.get("search_conditions", {}),
        results=result.get("results", []),
        count=result.get("count", 0)
    )


@router.post("/rank", response_model=JcDatabaseRankResponse, summary="DOI Jc排名")
async def rank_jc_by_doi(
    request: JcDatabaseRankRequest,
    user = Depends(get_current_user_required)
):
    """
    计算指定DOI的 Jc 排名

    - **target_doi**: 目标论文 DOI
    - **temperature**: 筛选温度条件，范围: 0-200K
    - **magnetic_field**: 筛选磁场条件，范围: 0-80T
    - **angle**: 筛选角度条件

    返回排名、百分位、Top 10 等
    """
    # 输入范围验证
    if request.temperature is not None:
        if request.temperature < 0:
            raise HTTPException(status_code=400, detail="温度不能为负数")
        if request.temperature > 200:
            raise HTTPException(status_code=400, detail="温度超出范围，最大允许 200K")

    if request.magnetic_field is not None:
        if request.magnetic_field < 0:
            raise HTTPException(status_code=400, detail="磁场不能为负数")
        if request.magnetic_field > 80:
            raise HTTPException(status_code=400, detail="磁场超出范围，最大允许 80T")

    if request.angle is not None and request.angle < 0:
        raise HTTPException(status_code=400, detail="角度不能为负数")

    service = get_jc_db_service()
    result = await service.rank_by_doi(
        target_doi=request.target_doi,
        temperature=request.temperature,
        magnetic_field=request.magnetic_field,
        angle=request.angle,
        temp_tolerance=request.temp_tolerance,
        field_tolerance=request.field_tolerance,
        angle_tolerance=request.angle_tolerance
    )

    return JcDatabaseRankResponse(
        success=result.get("success", False),
        message=result.get("message", ""),
        target_doi=result.get("target_doi", request.target_doi),
        target_jc_max=result.get("target_jc_max"),
        target_rank=result.get("target_rank"),
        total_papers=result.get("total_papers", 0),
        best_jc_max=result.get("best_jc_max"),
        rank_percentile=result.get("rank_percentile"),
        top_10=result.get("top_10", []),
        search_conditions=result.get("search_conditions", {})
    )


@router.get("/top-dois", summary="获取Jc排名靠前的DOI")
async def get_top_jc_dois(
    top_k: int = 20,
    temperature: Optional[float] = None,
    magnetic_field: Optional[float] = None,
    user = Depends(get_current_user_required)
):
    """
    获取 Jc 排名靠前的 DOI 列表

    - **top_k**: 返回数量
    - **temperature**: 筛选温度范围，范围: 0-200K
    - **magnetic_field**: 筛选磁场范围，范围: 0-80T
    """
    # 输入范围验证
    if temperature is not None:
        if temperature < 0:
            raise HTTPException(status_code=400, detail="温度不能为负数")
        if temperature > 200:
            raise HTTPException(status_code=400, detail="温度超出范围，最大允许 200K")

    if magnetic_field is not None:
        if magnetic_field < 0:
            raise HTTPException(status_code=400, detail="磁场不能为负数")
        if magnetic_field > 80:
            raise HTTPException(status_code=400, detail="磁场超出范围，最大允许 80T")

    service = get_jc_db_service()
    results = await service.get_dois_by_jc_rank(
        top_k=top_k,
        temperature=temperature,
        magnetic_field=magnetic_field
    )

    return {
        "success": True,
        "message": f"获取前 {len(results)} 名DOI",
        "results": results
    }