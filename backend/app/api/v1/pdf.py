"""
PDF 处理 API 路由 - 完整实现
"""
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status, Query
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)

from backend.app.schemas.paper import PaperUploadResponse, ResultListResponse, ResultDetail, ResultListItem
from backend.app.api.deps import get_db
from backend.app.api.deps_user import get_current_user_required
from backend.app.services.pdf_service import process_pdf, get_processing_result, delete_processing_result
from backend.app.services.storage_service import get_storage_service
from backend.app.models.user import User

router = APIRouter()


@router.post("/papers", response_model=PaperUploadResponse, summary="上传论文")
async def upload_paper(
    file: UploadFile = File(...),
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    上传 PDF 论文文件并解析

    - **file**: PDF 文件
    """
    import logging
    import traceback
    import sys
    logger = logging.getLogger(__name__)

    # 使用print确保在日志系统之前输出
    print(f"[PDF UPLOAD] 收到上传请求: filename={file.filename}", flush=True)
    sys.stdout.flush()

    try:
        logger.info(f"收到上传请求: filename={file.filename}, content_type={file.content_type}")

        # 验证文件类型
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            logger.warning(f"文件类型不支持: {file.filename}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只支持 PDF 文件"
            )

        # 读取文件内容
        file_content = await file.read()
        file_size = len(file_content)
        logger.info(f"文件大小: {file_size} bytes")

        if file_size == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件内容为空"
            )

        if file_size > 100 * 1024 * 1024:  # 100MB
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件大小超过100MB限制"
            )

        # 保存文件
        storage = get_storage_service()

        # 使用BytesIO包装文件内容
        from io import BytesIO
        file_stream = BytesIO(file_content)

        logger.info(f"开始保存文件...")
        save_result = await storage.save_upload_file(
            file_content=file_stream,
            file_name=file.filename,
            user_id=user.id
        )
        logger.info(f"文件保存结果: {save_result}")

        if not save_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="文件保存失败"
            )

        # 处理 PDF
        logger.info(f"开始处理PDF...")
        result = await process_pdf(
            file_path=save_result["file_path"],
            file_name=save_result["original_name"],
            user_id=user.id
        )
        logger.info(f"PDF处理结果: {result}")

        if result["success"]:
            return PaperUploadResponse(
                success=True,
                message="PDF 上传并解析成功",
                result_id=result["result_id"],
                file_name=result["file_name"],
                title=result.get("title", ""),
                doi=result.get("doi")
            )
        else:
            return PaperUploadResponse(
                success=False,
                message=f"PDF 解析失败: {result.get('error', '未知错误')}",
                result_id=None,
                file_name=file.filename
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传处理异常: {type(e).__name__}: {str(e)}")
        logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理失败: {str(e)}"
        )


@router.get("/papers", response_model=ResultListResponse, summary="获取论文列表")
async def get_paper_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status_filter: Optional[str] = Query(None, alias="status"),
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取已上传论文列表

    - **page**: 页码
    - **page_size**: 每页数量
    - **status**: 状态过滤（可选）
    """
    from sqlalchemy import select, func
    from backend.app.models.paper import ProcessingResult
    from backend.app.models.ner import NERResult
    from backend.app.models.re import REResult

    # 构建查询
    stmt = select(ProcessingResult).where(ProcessingResult.user_id == user.id)

    if status_filter:
        stmt = stmt.where(ProcessingResult.status == status_filter)

    # 获取总数
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar()

    # 分页查询
    stmt = stmt.order_by(ProcessingResult.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(stmt)
    items = result.scalars().all()

    # 查询每个论文的NER/RE状态
    result_ids = [item.result_id for item in items]

    # NER状态查询
    ner_stmt = select(NERResult.result_id, NERResult.status, NERResult.entity_count).where(
        NERResult.result_id.in_(result_ids)
    )
    ner_result = await db.execute(ner_stmt)
    ner_status_map = {row.result_id: (row.status, row.entity_count) for row in ner_result.all()}

    # RE状态查询
    re_stmt = select(REResult.result_id, REResult.status, REResult.relation_count).where(
        REResult.result_id.in_(result_ids)
    )
    re_result = await db.execute(re_stmt)
    re_status_map = {row.result_id: (row.status, row.relation_count) for row in re_result.all()}

    return ResultListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[
            ResultListItem(
                result_id=item.result_id,
                file_name=item.file_name,
                title=item.title,
                doi=item.doi,
                abstract=item.abstract,
                status=item.status,
                created_at=item.created_at,
                processed_at=item.processed_at,
                ner_status=ner_status_map.get(item.result_id, (None, None))[0],
                re_status=re_status_map.get(item.result_id, (None, None))[0]
            ) for item in items
        ]
    )


@router.get("/papers/{result_id}", response_model=ResultDetail, summary="获取论文详情")
async def get_paper_detail(
    result_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取指定论文的解析结果详情

    - **result_id**: 处理结果 ID
    """
    from backend.app.services.pdf_service import load_result_json

    # 从数据库获取基本信息
    result = await get_processing_result(result_id)

    if result is None:
        raise HTTPException(status_code=404, detail=f"论文不存在: {result_id}")

    # 加载详细内容
    parse_result = await load_result_json(result_id)

    if parse_result is None:
        parse_result = {}

    return ResultDetail(
        result_id=result["result_id"],
        file_name=result["file_name"],
        title=result["title"],
        doi=result["doi"],
        abstract=result["abstract"],
        status=result["status"],
        created_at=result.get("created_at"),
        processed_at=result.get("processed_at"),
        sections=parse_result.get("sections", []),
        references=parse_result.get("references", []),
        figures=parse_result.get("figures", []),
        result_pkl_path=result.get("result_pkl_path"),
        result_json_path=result.get("result_json_path")
    )


@router.delete("/papers/{result_id}", summary="删除论文")
async def delete_paper(
    result_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    删除指定论文及其相关数据

    - **result_id**: 处理结果 ID
    """
    success = await delete_processing_result(result_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"论文不存在: {result_id}")

    return {"success": True, "message": f"论文 {result_id} 已删除"}