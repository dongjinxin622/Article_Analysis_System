"""
关系抽取 API 路由 - 完整实现
支持Prompt Name（从数据库获取）和文件路径两种方式
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pathlib import Path
from typing import Optional
import tempfile
import os

from backend.app.schemas.re import RERequest, REResponse, REResultDetail, RelationInfo
from backend.app.api.deps import get_db, get_current_user_required
from backend.app.services.re_service import process_re_for_ner, get_re_result, load_re_relations, get_re_by_ner_id
from backend.app.services.prompt_service import get_prompt_service
from backend.app.models.user import User

router = APIRouter()


async def resolve_prompt_file(query_file: str, user_id: Optional[int] = None) -> str:
    """
    解析Prompt文件路径或名称

    如果query_file不包含路径分隔符，视为prompt name，从数据库获取内容并写入临时文件
    如果包含路径分隔符，视为文件路径，直接返回

    Args:
        query_file: Prompt文件路径或名称
        user_id: 用户ID（可选），用于过滤用户私有模板
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


@router.post("/re", response_model=REResponse, summary="执行关系抽取")
async def execute_re(
    request: RERequest,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    对指定 NER 结果执行关系抽取

    - **ner_id**: NER 结果 ID
    - **query_file**: Prompt 模板名称（如"material_re"）或文件路径
    """
    # 解析Prompt（支持名称和文件路径）
    actual_query_file = await resolve_prompt_file(request.query_file, user_id=user.id)

    # 是否是临时文件（需要清理）
    is_temp_file = '/' not in request.query_file and '\\' not in request.query_file

    # 执行 RE
    result = await process_re_for_ner(
        ner_id=request.ner_id,
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
        return REResponse(
            success=True,
            message="关系抽取完成",
            re_id=result["re_id"],
            ner_id=result["ner_id"],
            relation_count=result["relation_count"],
            re_json_path=result["re_json_path"],
            re_excel_path=result["re_excel_path"]
        )
    else:
        return REResponse(
            success=False,
            message=f"关系抽取失败: {result.get('error', '未知错误')}",
            re_id=None,
            ner_id=request.ner_id
        )


@router.get("/re/{re_id}", response_model=REResultDetail, summary="获取 RE 结果")
async def get_re_result_detail(
    re_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取指定 RE 结果详情

    - **re_id**: RE 结果 ID
    """
    result = await get_re_result(re_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"RE 结果不存在: {re_id}")

    # 加载关系列表
    relations = await load_re_relations(re_id)

    relation_infos = [
        RelationInfo(
            relation_type=rel.get("relation_type", ""),
            source_type=rel.get("source_type", ""),
            source_entity=rel.get("source_entity", ""),
            target_type=rel.get("target_type", ""),
            target_entity=rel.get("target_entity", ""),
            effect=rel.get("effect"),
            supporting_sentence=rel.get("supporting_sentence")
        ) for rel in relations
    ]

    return REResultDetail(
        re_id=result["re_id"],
        ner_id=result["ner_id"],
        result_id=result["result_id"],
        relations=relation_infos,
        relation_count=result["relation_count"],
        status=result["status"],
        created_at=result.get("created_at"),
        processed_at=result.get("processed_at")
    )


@router.get("/re/{re_id}/excel", summary="下载 Excel")
async def download_re_excel(
    re_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    下载 RE 结果 Excel 文件

    - **re_id**: RE 结果 ID
    """
    result = await get_re_result(re_id)

    if result is None or not result.get("re_excel_path"):
        raise HTTPException(status_code=404, detail=f"RE Excel 文件不存在")

    excel_path = Path(result["re_excel_path"])
    if not excel_path.exists():
        raise HTTPException(status_code=404, detail="Excel 文件不存在")

    return FileResponse(
        path=excel_path,
        filename=f"{re_id}.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@router.get("/re/{re_id}/relations", summary="获取关系列表")
async def get_relations(
    re_id: str,
    relation_type: str = None,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取 RE 结果中的关系列表

    - **re_id**: RE 结果 ID
    - **relation_type**: 关系类型过滤（可选）
    """
    relations = await load_re_relations(re_id)

    # 过滤
    if relation_type:
        relations = [r for r in relations if r.get("relation_type") == relation_type]

    return {
        "re_id": re_id,
        "total": len(relations),
        "relations": relations
    }


@router.get("/re/by-ner/{ner_id}", summary="根据 NER ID 获取 RE")
async def get_re_by_ner(
    ner_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    根据 NER 结果 ID 获取对应的 RE 结果

    - **ner_id**: NER 结果 ID
    """
    result = await get_re_by_ner_id(ner_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"未找到对应 NER {ner_id} 的 RE 结果")

    # 加载关系列表
    relations = await load_re_relations(result["re_id"])

    relation_infos = [
        RelationInfo(
            relation_type=rel.get("relation_type", ""),
            source_type=rel.get("source_type", ""),
            source_entity=rel.get("source_entity", ""),
            target_type=rel.get("target_type", ""),
            target_entity=rel.get("target_entity", ""),
            effect=rel.get("effect"),
            supporting_sentence=rel.get("supporting_sentence")
        ) for rel in relations
    ]

    return REResultDetail(
        re_id=result["re_id"],
        ner_id=result["ner_id"],
        result_id=result["result_id"],
        relations=relation_infos,
        relation_count=result["relation_count"],
        status=result["status"],
        created_at=result.get("created_at"),
        processed_at=result.get("processed_at")
    )