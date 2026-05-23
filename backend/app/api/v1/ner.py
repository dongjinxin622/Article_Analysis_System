"""
NER 处理 API 路由 - 完整实现
支持Prompt Name（从数据库获取）和文件路径两种方式
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse
from typing import List, Optional, Dict
from pathlib import Path
import tempfile
import os

from backend.app.schemas.ner import NERRequest, NERResponse, NERResultDetail, NERBatchRequest, NERBatchResponse, EntityInfo, NERResultListItem, NERResultListResponse
from backend.app.schemas.paper import ProcessingStatus
from backend.app.api.deps import get_db, get_current_user_required
from backend.app.services.ner_service import process_ner_for_result, get_ner_result, load_ner_entities
from backend.app.services.prompt_service import get_prompt_service
from backend.app.models.user import User
from backend.app.core.config import NER_RESULTS_DIR

router = APIRouter()


async def resolve_prompt_file(query_file: str, user_id: Optional[int] = None) -> str:
    """
    解析Prompt文件路径或名称

    如果query_file不包含路径分隔符，视为prompt name，从数据库获取内容并写入临时文件
    如果包含路径分隔符，视为文件路径，直接返回

    Args:
        query_file: Prompt文件路径或名称
        user_id: 用户ID（可选），用于过滤用户私有模板

    Returns:
        实际的Prompt文件路径
    """
    # 检查是否包含路径分隔符
    if '/' in query_file or '\\' in query_file:
        # 是文件路径，验证存在性
        if not Path(query_file).exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt 文件不存在: {query_file}"
            )
        return query_file

    # 是prompt name，从数据库获取
    prompt_service = get_prompt_service()
    prompt_content = await prompt_service.get_prompt_content(query_file, user_id=user_id)

    if not prompt_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt 模板 '{query_file}' 不存在"
        )

    # 写入临时文件
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    temp_file.write(prompt_content)
    temp_file.close()

    return temp_file.name


@router.post("/ner", response_model=NERResponse, summary="执行 NER")
async def execute_ner(
    request: NERRequest,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    对指定论文执行命名实体识别

    - **result_id**: 处理结果 ID
    - **query_file**: Prompt 模板名称（如"material_ner"）或文件路径
    - **skip_introduction**: 是否跳过 introduction 部分
    - **sentence_group_size**: 每组句子数量
    """
    # 解析Prompt（支持名称和文件路径）
    actual_query_file = await resolve_prompt_file(request.query_file, user_id=user.id)

    # 是否是临时文件（需要清理）
    is_temp_file = '/' not in request.query_file and '\\' not in request.query_file

    # 执行 NER
    result = await process_ner_for_result(
        result_id=request.result_id,
        skip_introduction=request.skip_introduction,
        sentence_group_size=request.sentence_group_size,
        query_file_path=actual_query_file,
        task_name=request.task_name,
        user_id=user.id
    )

    # 清理临时文件
    if is_temp_file and Path(actual_query_file).exists():
        try:
            os.unlink(actual_query_file)
        except:
            pass

    if result["success"]:
        return NERResponse(
            success=True,
            message="NER 处理完成",
            ner_id=result["ner_id"],
            result_id=result["result_id"],
            entity_count=result["entity_count"],
            ner_json_path=result["ner_json_path"],
            ner_excel_path=result["ner_excel_path"],
            ner_pkl_path=result["ner_pkl_path"],
            group_count=result["group_count"]
        )
    else:
        return NERResponse(
            success=False,
            message=f"NER 处理失败: {result.get('error', '未知错误')}",
            ner_id=None,
            result_id=request.result_id
        )


@router.get("/ner/list", response_model=NERResultListResponse, summary="获取 NER 结果列表")
async def get_ner_result_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取用户的 NER 结果列表

    - **page**: 页码
    - **page_size**: 每页数量
    """
    from sqlalchemy import select, func
    from backend.app.models.ner import NERResult
    from backend.app.models.re import REResult

    # 查询用户的NER结果
    stmt = select(NERResult).where(NERResult.user_id == user.id)

    # 获取总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # 分页查询
    stmt = stmt.order_by(NERResult.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    items = result.scalars().all()

    # 查询每个NER结果对应的RE状态
    ner_ids = [item.ner_id for item in items]
    re_stmt = select(REResult.ner_id, REResult.status).where(
        REResult.ner_id.in_(ner_ids)
    )
    re_result = await db.execute(re_stmt)
    re_status_map = {row.ner_id: row.status for row in re_result.all()}

    return NERResultListResponse(
        total=total,
        items=[
            NERResultListItem(
                ner_id=item.ner_id,
                result_id=item.result_id,
                entity_count=item.entity_count,
                status=item.status,
                re_status=re_status_map.get(item.ner_id),
                created_at=item.created_at
            ) for item in items
        ]
    )


@router.get("/ner/{ner_id}", response_model=NERResultDetail, summary="获取 NER 结果")
async def get_ner_result_detail(
    ner_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取指定 NER 结果详情

    - **ner_id**: NER 结果 ID
    """
    result = await get_ner_result(ner_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"NER 结果不存在: {ner_id}")

    # 加载实体列表
    entities = await load_ner_entities(ner_id)

    entity_infos = [
        EntityInfo(
            entity_type=ent.get("entity_type", ""),
            entity_text=ent.get("entity_text", ""),
            start_pos=ent.get("start_pos", 0),
            end_pos=ent.get("end_pos", 0),
            confidence=ent.get("confidence"),
            section_idx=ent.get("section_idx"),
            group_idx=ent.get("group_idx")
        ) for ent in entities
    ]

    return NERResultDetail(
        ner_id=result["ner_id"],
        result_id=result["result_id"],
        entities=entity_infos,
        entity_count=result["entity_count"],
        status=result["status"],
        created_at=result.get("created_at"),
        processed_at=result.get("processed_at")
    )


@router.get("/ner/{ner_id}/excel", summary="下载 Excel")
async def download_ner_excel(
    ner_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    下载 NER 结果 Excel 文件

    - **ner_id**: NER 结果 ID
    """
    result = await get_ner_result(ner_id)

    if result is None or not result.get("ner_excel_path"):
        raise HTTPException(status_code=404, detail=f"NER Excel 文件不存在")

    excel_path = Path(result["ner_excel_path"])
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Excel 文件不存在")

    return FileResponse(
        path=excel_path,
        filename=f"{ner_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/ner/{ner_id}/pkl", summary="下载 PKL")
async def download_ner_pkl(
    ner_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    下载 NER 结果 PKL 文件

    - **ner_id**: NER 结果 ID
    """
    result = await get_ner_result(ner_id)

    if result is None or not result.get("ner_pkl_path"):
        raise HTTPException(status_code=404, detail=f"NER PKL 文件不存在")

    pkl_path = Path(result["ner_pkl_path"])
    if not pkl_path.exists():
        raise HTTPException(status_code=404, detail="PKL 文件不存在")

    return FileResponse(
        path=pkl_path,
        filename=f"{ner_id}.pkl",
        media_type="application/octet-stream"
    )


def transform_entity_to_display_format(ent: Dict) -> Dict:
    """将 NER 实体转换为前端显示格式"""
    # 处理 error 类型的实体
    if "error" in ent:
        return {
            "entity_type": "错误",
            "entity_text": ent.get("error", ""),
            "start_pos": 0,
            "end_pos": 0,
            "section_idx": ent.get("section_idx"),
            "group_idx": ent.get("group_idx")
        }

    # 构建实体文本
    entity_text = ""
    if ent.get("name"):
        entity_text = ent.get("name", "")
    elif ent.get("symbol"):
        entity_text = ent.get("symbol", "")
    if ent.get("value"):
        entity_text += f" = {ent.get('value')}"
        if ent.get("unit"):
            entity_text += f" {ent.get('unit')}"

    # 构建实体类型
    entity_type = ent.get("type", "")
    if ent.get("subtype"):
        entity_type += f" / {ent.get('subtype')}"

    return {
        "entity_type": entity_type,
        "entity_text": entity_text,
        "start_pos": 0,
        "end_pos": 0,
        "confidence": None,
        "section_idx": ent.get("section_idx"),
        "group_idx": ent.get("group_idx"),
        "original_data": ent  # 保留原始数据供参考
    }


@router.get("/ner/{ner_id}/entities", summary="获取实体列表")
async def get_entities(
    ner_id: str,
    entity_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取 NER 结果中的实体列表

    - **ner_id**: NER 结果 ID
    - **entity_type**: 实体类型过滤（可选）
    - **limit**: 返回数量限制
    """
    raw_entities = await load_ner_entities(ner_id)

    # 转换为前端显示格式
    entities = [transform_entity_to_display_format(e) for e in raw_entities]

    # 过滤（过滤转换后的 entity_type）
    if entity_type:
        entities = [e for e in entities if entity_type in e.get("entity_type", "")]

    # 限制数量
    entities = entities[:limit]

    return {
        "ner_id": ner_id,
        "total": len(entities),
        "entities": entities
    }


@router.post("/ner/batch", response_model=NERBatchResponse, summary="批量 NER")
async def batch_ner(
    request: NERBatchRequest,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    批量执行 NER

    - **result_ids**: 处理结果 ID 列表
    - **query_file**: Prompt 模板文件路径
    """
    # 验证 Prompt 文件
    if not Path(request.query_file).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Prompt 文件不存在: {request.query_file}"
        )

    results = []
    for result_id in request.result_ids:
        result = await process_ner_for_result(
            result_id=result_id,
            skip_introduction=request.skip_introduction,
            sentence_group_size=request.sentence_group_size,
            query_file_path=request.query_file,
            user_id=user.id
        )
        results.append(NERResponse(
            success=result["success"],
            message=result.get("error") if not result["success"] else "处理完成",
            ner_id=result.get("ner_id"),
            result_id=result_id
        ))

    success_count = sum(1 for r in results if r.success)

    return NERBatchResponse(
        success=success_count > 0,
        message=f"批量处理完成，成功 {success_count}/{len(request.result_ids)}",
        task_id=f"batch_ner_{len(request.result_ids)}",
        total_count=len(request.result_ids),
        results=results
    )