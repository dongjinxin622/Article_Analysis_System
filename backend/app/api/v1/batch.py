"""
批量处理 API 路由 - 直接异步处理（无 Celery）
支持完整的批量处理流程：PDF上传 -> 解析 -> NER -> RE
"""
import uuid
import json
import asyncio
import zipfile
import io
from urllib.parse import quote
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
from datetime import datetime

from backend.app.schemas.batch import BatchTaskRequest, BatchTaskResponse, BatchTaskDetail, TaskProgress, BatchTaskListResponse
from backend.app.api.deps import get_db
from backend.app.api.deps_user import get_current_user_required
from backend.app.services.batch_service import (
    create_batch_task,
    get_batch_task_status,
    get_user_batch_tasks,
    cancel_batch_task,
    get_default_prompt_files,
    export_batch_results_excel
)
from backend.app.services.pdf_service import process_pdf
from backend.app.services.ner_service import get_ner_result
from backend.app.services.re_service import get_re_result
from backend.app.models.user import User
from backend.app.core.config import settings, UPLOADS_DIR
from backend.app.api.v1.ner import resolve_prompt_file

router = APIRouter()


@router.post("/batch/upload-pdf", summary="批量上传 PDF 文件并解析")
async def batch_upload_pdf(
    files: List[UploadFile] = File(..., description="PDF 文件列表"),
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    批量上传 PDF 文件并自动解析

    - 支持多个 PDF 文件同时上传
    - 上传后自动解析每个 PDF
    - 返回所有文件的上传和解析结果

    参数：
    - files: PDF 文件列表（multipart/form-data）

    返回：
    - success: 是否至少有一个文件解析成功
    - message: 响应消息
    - files: 每个文件的上传结果（包含 result_id）
    - total: 总文件数
    - success_count: 成功数
    - failed_count: 失败数
    """
    if not files:
        raise HTTPException(status_code=400, detail="未提供任何文件")

    # 确保上传目录存在
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    success_count = 0
    failed_count = 0

    for file in files:
        # 验证文件扩展名
        file_ext = Path(file.filename).suffix.lower()
        if file_ext not in settings.ALLOWED_EXTENSIONS:
            results.append({
                "file_name": file.filename,
                "status": "failed",
                "error": f"不支持的文件类型：{file_ext}"
            })
            failed_count += 1
            continue

        try:
            # 读取文件内容
            content = await file.read()

            # 验证文件大小
            if len(content) > settings.MAX_UPLOAD_SIZE:
                results.append({
                    "file_name": file.filename,
                    "status": "failed",
                    "error": f"文件过大，最大支持 {settings.MAX_UPLOAD_SIZE // 1024 // 1024}MB"
                })
                failed_count += 1
                continue

            # 生成唯一文件名并保存
            file_id = str(uuid.uuid4())
            save_path = UPLOADS_DIR / f"{file_id}_{file.filename}"

            with open(save_path, "wb") as f:
                f.write(content)

            # 处理 PDF
            process_result = await process_pdf(
                str(save_path),
                file.filename,
                max_retries=settings.PDF_MAX_RETRIES,
                retry_delay=settings.PDF_RETRY_DELAY,
                user_id=user.id
            )

            if process_result.get("success"):
                results.append({
                    "file_name": file.filename,
                    "file_id": file_id,
                    "result_id": process_result.get("result_id"),
                    "title": process_result.get("title"),
                    "doi": process_result.get("doi"),
                    "status": "completed",
                    "size": len(content)
                })
                success_count += 1
            else:
                results.append({
                    "file_name": file.filename,
                    "file_id": file_id,
                    "status": "failed",
                    "error": process_result.get("error", "PDF 解析失败")
                })
                failed_count += 1

        except Exception as e:
            results.append({
                "file_name": file.filename,
                "status": "failed",
                "error": str(e)
            })
            failed_count += 1

    message = f"成功上传 {len(files)} 个文件"
    if success_count > 0:
        message += f"，解析成功 {success_count} 个"
    if failed_count > 0:
        message += f"，解析失败 {failed_count} 个"

    return {
        "success": success_count > 0,
        "message": message,
        "files": results,
        "total": len(files),
        "success_count": success_count,
        "failed_count": failed_count
    }


@router.get("/batch", response_model=BatchTaskListResponse, summary="获取任务列表")
async def get_task_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取用户的批量任务列表

    - **page**: 页码
    - **page_size**: 每页数量
    """
    tasks = await get_user_batch_tasks(user.id)

    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    paginated_tasks = tasks[start:end]

    # 转换为 BatchTaskDetail
    items = []
    for task in paginated_tasks:
        items.append(BatchTaskDetail(
            task_id=task.get("task_id", ""),
            task_name=task.get("task_name", "批量任务"),
            status=task.get("status", "pending"),
            total_count=task.get("total_count", 0),
            completed_count=task.get("completed_count", 0),
            failed_count=task.get("failed_count", 0),
            progress=task.get("progress", 0.0),
            error_message=task.get("message") if task.get("status") == "failed" else None,
            created_at=task.get("created_at")
        ))

    return BatchTaskListResponse(
        items=items,
        total=len(tasks),
        page=page,
        page_size=page_size
    )


@router.post("/batch", response_model=BatchTaskResponse, summary="创建批量任务")
async def create_batch_task_api(
    request: BatchTaskRequest,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    创建批量处理任务

    - **task_name**: 任务名称
    - **result_ids**: 处理结果 ID 列表
    - **config**: 任务配置
        - do_ner: 是否执行 NER (默认 true)
        - do_re: 是否执行 RE (默认 true)
        - ner_query_file: NER prompt 文件路径 (可选，使用默认)
        - re_query_file: RE prompt 文件路径 (可选，使用默认)
        - skip_introduction: 是否跳过 introduction (默认 true)
        - sentence_group_size: 句子分组大小 (默认 5)
    - **enable_hitl**: 是否启用 HITL (暂不支持)
    """
    # 验证 result_ids
    if not request.result_ids:
        raise HTTPException(status_code=400, detail="必须提供 result_ids")

    # 获取默认 prompt 文件
    default_prompts = get_default_prompt_files()

    # 合并配置
    config = request.config or {}
    if not config.get("ner_query_file"):
        config["ner_query_file"] = default_prompts.get("ner_query_file")
    if not config.get("re_query_file"):
        config["re_query_file"] = default_prompts.get("re_query_file")

    # 解析 prompt（支持名称和文件路径）
    if config.get("do_ner", True):
        ner_file = config.get("ner_query_file")
        if not ner_file:
            raise HTTPException(status_code=400, detail="缺少 NER prompt 文件配置")
        config["ner_query_file"] = await resolve_prompt_file(ner_file, user_id=user.id)

    if config.get("do_re", True):
        re_file = config.get("re_query_file")
        if not re_file:
            raise HTTPException(status_code=400, detail="缺少 RE prompt 文件配置")
        config["re_query_file"] = await resolve_prompt_file(re_file, user_id=user.id)

    # 创建任务
    result = await create_batch_task(
        task_name=request.task_name,
        result_ids=request.result_ids,
        user_id=user.id,
        config=config
    )

    return BatchTaskResponse(
        success=True,
        message=result.get("message", "任务已创建"),
        task_id=result.get("task_id"),
        status=result.get("status", "pending"),
        total_count=result.get("total_count", 0)
    )


@router.get("/batch/{task_id}", response_model=BatchTaskDetail, summary="获取任务详情")
async def get_batch_task_detail(
    task_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取批量任务详情

    - **task_id**: 任务 ID
    """
    task_status = await get_batch_task_status(task_id)

    if not task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    return BatchTaskDetail(
        task_id=task_id,
        task_name=task_status.get("task_name", "批量任务"),
        status=task_status.get("status", "pending"),
        total_count=task_status.get("total_count", 0),
        completed_count=task_status.get("completed_count", 0),
        failed_count=task_status.get("failed_count", 0),
        progress=task_status.get("progress", 0.0),
        error_message=task_status.get("message") if task_status.get("status") == "failed" else None,
        results=task_status.get("results", []),
        errors=task_status.get("errors", [])
    )


@router.post("/batch/{task_id}/cancel", summary="取消任务")
async def cancel_batch_task_api(
    task_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    取消批量任务

    - **task_id**: 任务 ID
    """
    result = await cancel_batch_task(task_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "取消失败"))

    return {"success": True, "message": f"任务 {task_id} 已取消"}


@router.get("/batch/{task_id}/progress", response_model=TaskProgress, summary="获取任务进度")
async def get_task_progress_api(
    task_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取批量任务进度

    - **task_id**: 任务 ID
    """
    task_status = await get_batch_task_status(task_id)

    if not task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskProgress(
        task_id=task_id,
        step=task_status.get("status", "pending"),
        progress=task_status.get("progress", 0.0),
        message=task_status.get("message", ""),
        current_file=None,
        total_files=task_status.get("total_count", 0)
    )


@router.get("/batch/prompts", summary="获取默认 Prompt 文件")
async def get_default_prompts(
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    获取默认的 NER 和 RE prompt 文件路径
    """
    default_prompts = get_default_prompt_files()

    return {
        "ner_query_file": default_prompts.get("ner_query_file"),
        "re_query_file": default_prompts.get("re_query_file")
    }


@router.get("/batch/{task_id}/download", summary="下载批量任务结果 Excel")
async def download_batch_results(
    task_id: str,
    db = Depends(get_db),
    user: User = Depends(get_current_user_required)
):
    """
    下载批量任务结果 Excel 文件

    Excel 文件包含三个 sheet：
    - content: 论文原文内容（doi, section_idx, group_idx, heading, text）
    - NER: 实体提取结果
    - RE: 关系提取结果

    - **task_id**: 任务 ID
    """
    task_status = await get_batch_task_status(task_id)

    if not task_status:
        raise HTTPException(status_code=404, detail="任务不存在")

    if task_status.get("status") != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成，无法下载")

    # 导出 Excel
    export_result = await export_batch_results_excel(task_id)

    if not export_result.get("success"):
        raise HTTPException(status_code=500, detail=export_result.get("error", "导出失败"))

    file_path = Path(export_result["file_path"])
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    filename = f"{task_id}_results.xlsx"

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )