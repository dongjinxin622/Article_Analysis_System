"""
领域分析 API 路由
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from loguru import logger

from backend.app.schemas.domain import (
    DomainListResponse, DomainConfigResponse,
    TechRouteRequest, TechRouteResponse,
    ExpSchemeRequest, ExpSchemeResponse,
    JcSearchRequest, JcSearchResponse,
    JcCompareRequest, JcCompareResponse
)
from backend.app.api.deps import get_db, get_current_user_required
from backend.app.models import NERResult, REResult, TechRoute, ExpScheme
from backend.app.domain.registry import DomainRegistry
from backend.app.domain.material.analyzer import REBCOAnalyzer

router = APIRouter()


@router.get("/domains", response_model=DomainListResponse, summary="获取领域列表")
async def get_domain_list():
    """
    获取已注册的领域分析器列表
    """
    domains = DomainRegistry.list_domains()
    return DomainListResponse(domains=domains, count=len(domains))


@router.get("/domains/{domain_name}/config", response_model=DomainConfigResponse, summary="获取领域配置")
async def get_domain_config(domain_name: str):
    """
    获取指定领域的配置信息

    - **domain_name**: 领域名称
    """
    config = DomainRegistry.get_config(domain_name)

    if not config:
        raise HTTPException(status_code=404, detail=f"领域 '{domain_name}' 未注册")

    return DomainConfigResponse(
        domain_name=config.get('domain_name', domain_name),
        description=f"{domain_name} 领域分析器",
        entity_types=config.get('entity_types', {}),
        relation_types=config.get('relation_types', {}),
        prompt_templates=config.get('prompt_templates', {}),
        is_active=config.get('is_active', True)
    )


@router.post("/domains/{domain_name}/techroute", response_model=TechRouteResponse, summary="技术路线分析")
async def analyze_tech_route(
    domain_name: str,
    request: TechRouteRequest,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    执行技术路线分析

    - **domain_name**: 领域名称
    - **ner_id**: NER 结果 ID
    - **top_k**: 返回相似论文数量
    """
    # 获取领域分析器
    analyzer = DomainRegistry.get(domain_name)

    if not analyzer:
        raise HTTPException(status_code=404, detail=f"领域 '{domain_name}' 未注册")

    # 获取 NER 结果
    ner_result = await db.execute(select(NERResult).where(NERResult.ner_id == request.ner_id))
    ner_data = ner_result.scalar_one_or_none()

    if not ner_data:
        raise HTTPException(status_code=404, detail=f"NER 结果 '{request.ner_id}' 不存在")

    # 获取 RE 结果（如有）
    entities = ner_data.entities or []
    relations = []

    # 查找关联的 RE 结果
    re_result = await db.execute(select(REResult).where(REResult.ner_id == request.ner_id))
    re_data = re_result.scalar_one_or_none()
    if re_data:
        relations = re_data.relations or []

    # 执行分析
    result = await analyzer.analyze_tech_route(
        entities=entities,
        relations=relations,
        top_k=request.top_k or 10
    )

    # 存储技术路线结果
    if result.get('success') and result.get('tech_route_text'):
        profile_id = str(uuid.uuid4())
        tech_route_record = TechRoute(
            profile_id=profile_id,
            paper_id=ner_data.result_id,
            ner_id=request.ner_id,
            profile_text=result['tech_route_text'],
            domain=domain_name,
            user_id=user.id
        )
        db.add(tech_route_record)
        await db.commit()

        result['profile_id'] = profile_id

    return TechRouteResponse(
        success=result.get('success', False),
        message=result.get('message', ''),
        profile_id=result.get('profile_id'),
        profile_text=result.get('tech_route_text'),
        similar_papers=result.get('similar_papers', [])
    )


@router.post("/domains/{domain_name}/expscheme", response_model=ExpSchemeResponse, summary="实验方案分析")
async def analyze_exp_scheme(
    domain_name: str,
    request: ExpSchemeRequest,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    执行实验方案分析

    - **domain_name**: 领域名称
    - **ner_id**: NER 结果 ID
    - **top_k**: 返回相似论文数量
    """
    # 获取领域分析器
    analyzer = DomainRegistry.get(domain_name)

    if not analyzer:
        raise HTTPException(status_code=404, detail=f"领域 '{domain_name}' 未注册")

    # 获取 NER 结果
    ner_result = await db.execute(select(NERResult).where(NERResult.ner_id == request.ner_id))
    ner_data = ner_result.scalar_one_or_none()

    if not ner_data:
        raise HTTPException(status_code=404, detail=f"NER 结果 '{request.ner_id}' 不存在")

    entities = ner_data.entities or []

    # 执行分析
    result = await analyzer.analyze_exp_scheme(
        entities=entities,
        top_k=request.top_k or 10
    )

    # 存储实验方案结果
    if result.get('success') and result.get('exp_scheme_text'):
        scheme_id = str(uuid.uuid4())
        exp_scheme_record = ExpScheme(
            scheme_id=scheme_id,
            paper_id=ner_data.result_id,
            ner_id=request.ner_id,
            scheme_text=result['exp_scheme_text'],
            dimensions=result.get('dimensions', {}),
            domain=domain_name,
            user_id=user.id
        )
        db.add(exp_scheme_record)
        await db.commit()

        result['scheme_id'] = scheme_id

    return ExpSchemeResponse(
        success=result.get('success', False),
        message=result.get('message', ''),
        scheme_id=result.get('scheme_id'),
        scheme_text=result.get('exp_scheme_text'),
        dimensions=result.get('dimensions', {}),
        similar_papers=result.get('similar_papers', [])
    )


@router.post("/domains/{domain_name}/jc/search", response_model=JcSearchResponse, summary="Jc 指标搜索")
async def search_jc_indicators(
    domain_name: str,
    request: JcSearchRequest,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    搜索 Jc 指标

    - **domain_name**: 领域名称
    - **ner_id**: NER 结果 ID
    - **temperature**: 目标温度（K）
    - **magnetic_field**: 目标磁场（T）
    - **angle**: 目标角度（deg）
    """
    # 获取领域分析器
    analyzer = DomainRegistry.get(domain_name)

    if not analyzer:
        raise HTTPException(status_code=404, detail=f"领域 '{domain_name}' 未注册")

    # 获取 NER 结果
    ner_result = await db.execute(select(NERResult).where(NERResult.ner_id == request.ner_id))
    ner_data = ner_result.scalar_one_or_none()

    if not ner_data:
        raise HTTPException(status_code=404, detail=f"NER 结果 '{request.ner_id}' 不存在")

    entities = ner_data.entities or []

    # 分析 Jc 指标
    jc_result = await analyzer.jc_index_analyzer.analyze(entities)

    if not jc_result.get('success'):
        return JcSearchResponse(
            success=False,
            message=jc_result.get('message', 'Jc 分析失败'),
            indicators=[],
            count=0
        )

    # 按条件筛选
    filtered = analyzer.jc_index_analyzer.search_by_conditions(
        jc_result.get('jc_indicators', []),
        temperature=request.temperature,
        magnetic_field=request.magnetic_field,
        angle=request.angle
    )

    return JcSearchResponse(
        success=True,
        message="Jc 指标搜索完成",
        indicators=filtered,
        count=len(filtered)
    )


@router.post("/domains/{domain_name}/jc/compare", response_model=JcCompareResponse, summary="Jc 对比分析")
async def compare_jc_indicators(
    domain_name: str,
    request: JcCompareRequest,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    对比多篇论文的 Jc 指标

    - **domain_name**: 领域名称
    - **ner_ids**: NER 结果 ID 列表
    """
    # 获取领域分析器
    analyzer = DomainRegistry.get(domain_name)

    if not analyzer:
        raise HTTPException(status_code=404, detail=f"领域 '{domain_name}' 未注册")

    # 获取所有 NER 结果
    jc_data_list = []

    for ner_id in request.ner_ids:
        ner_result = await db.execute(select(NERResult).where(NERResult.ner_id == ner_id))
        ner_data = ner_result.scalar_one_or_none()

        if ner_data:
            entities = ner_data.entities or []
            jc_result = await analyzer.jc_index_analyzer.analyze(entities)
            jc_data_list.append(jc_result.get('jc_indicators', []))
        else:
            jc_data_list.append([])

    # 执行对比
    comparison_result = await analyzer.compare_jc(request.ner_ids, jc_data_list)

    return JcCompareResponse(
        success=comparison_result.get('success', True),
        message=comparison_result.get('message', 'Jc 对比分析完成'),
        comparison_table=comparison_result.get('comparison_table', []),
        analysis_report=comparison_result.get('analysis_report')
    )


@router.post("/domains/{domain_name}/analyze", summary="综合领域分析")
async def full_domain_analysis(
    domain_name: str,
    request: dict,
    db: AsyncSession = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    执行综合领域分析（包含技术路线、实验方案、Jc 指标）

    - **domain_name**: 领域名称
    - **ner_id**: NER 结果 ID
    - **include_content**: 是否包含原文内容分析
    """
    # 获取领域分析器
    analyzer = DomainRegistry.get(domain_name)

    if not analyzer:
        raise HTTPException(status_code=404, detail=f"领域 '{domain_name}' 未注册")

    ner_id = request.get('ner_id')
    if not ner_id:
        raise HTTPException(status_code=400, detail="缺少 ner_id 参数")

    # 获取 NER 结果
    ner_result = await db.execute(select(NERResult).where(NERResult.ner_id == ner_id))
    ner_data = ner_result.scalar_one_or_none()

    if not ner_data:
        raise HTTPException(status_code=404, detail=f"NER 结果 '{ner_id}' 不存在")

    entities = ner_data.entities or []
    relations = []
    content = None

    # 查找关联的 RE 结果
    re_result = await db.execute(select(REResult).where(REResult.ner_id == ner_id))
    re_data = re_result.scalar_one_or_none()
    if re_data:
        relations = re_data.relations or []

    # 构建输入数据
    input_data = {
        'analysis_type': 'all',
        'entities': entities,
        'relations': relations,
        'content': content
    }

    # 执行综合分析
    result = await analyzer.analyze(input_data)

    return {
        "success": True,
        "message": "综合领域分析完成",
        "domain": domain_name,
        "ner_id": ner_id,
        **result
    }