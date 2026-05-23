# -*- coding: utf-8 -*-
"""
任务状态 API 路由

提供任务状态查询、取消和列表功能。
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any, Optional
from loguru import logger

from backend.app.api.deps_user import get_current_user_required
from backend.app.services.task_manager import TaskManager
from backend.app.schemas.task import (
    TaskStatusResponse, TaskListResponse, TaskCancelResponse,
    TaskCreateRequest, TaskCreateResponse
)

router = APIRouter()
task_manager = TaskManager()


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse, summary="获取任务状态")
async def get_task_status(
    task_id: str,
    user = Depends(get_current_user_required)
):
    """
    获取指定任务的状态信息

    - **task_id**: 任务 ID
    """
    task_status = task_manager.get_task_status(task_id)

    if task_status.get("status") == "not_found":
        # 尝试从 Celery 获取
        from celery.result import AsyncResult
        from backend.app.tasks import celery_app

        result = AsyncResult(task_id, app=celery_app)

        if result.state == "PENDING":
            task_status = {
                "task_id": task_id,
                "status": "pending",
                "progress": 0,
                "message": "任务等待执行"
            }
        elif result.state == "STARTED":
            task_status = {
                "task_id": task_id,
                "status": "processing",
                "progress": 0,
                "message": "任务正在执行"
            }
        elif result.state == "SUCCESS":
            task_status = {
                "task_id": task_id,
                "status": "completed",
                "progress": 100,
                "message": "任务已完成",
                "result": result.result
            }
        elif result.state == "FAILURE":
            task_status = {
                "task_id": task_id,
                "status": "failed",
                "progress": 0,
                "message": "任务执行失败",
                "error": str(result.result)
            }
        else:
            task_status = {
                "task_id": task_id,
                "status": result.state.lower(),
                "message": f"任务状态: {result.state}"
            }

    return TaskStatusResponse(
        task_id=task_id,
        status=task_status.get("status", "unknown"),
        progress=task_status.get("progress", 0),
        message=task_status.get("message", ""),
        stage=task_status.get("stage"),
        result=task_status.get("result"),
        error=task_status.get("error"),
        created_at=task_status.get("created_at"),
        updated_at=task_status.get("updated_at")
    )


@router.get("/tasks", response_model=TaskListResponse, summary="获取任务列表")
async def get_task_list(
    status: Optional[str] = None,
    limit: int = 50,
    user = Depends(get_current_user_required)
):
    """
    获取用户的任务列表

    - **status**: 状态筛选（pending/processing/completed/failed）
    - **limit**: 返回数量限制
    """
    # 获取用户任务
    tasks = task_manager.get_user_tasks(user.id)

    # 状态筛选
    if status:
        tasks = [t for t in tasks if t.get("status") == status]

    # 限制数量
    tasks = tasks[:limit]

    return TaskListResponse(
        tasks=tasks,
        count=len(tasks),
        total=len(task_manager.get_user_tasks(user.id))
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskCancelResponse, summary="取消任务")
async def cancel_task(
    task_id: str,
    user = Depends(get_current_user_required)
):
    """
    取消正在执行的任务

    - **task_id**: 任务 ID
    """
    # 获取任务状态
    task_status = task_manager.get_task_status(task_id)

    if task_status.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在")

    # 检查任务所属用户
    if task_status.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="无权取消此任务")

    # 只能取消 pending 或 processing 状态的任务
    if task_status.get("status") not in ["pending", "processing"]:
        raise HTTPException(status_code=400, detail="任务已完成，无法取消")

    # 取消 Celery 任务
    from celery.result import AsyncResult
    from backend.app.tasks import celery_app

    result = AsyncResult(task_id, app=celery_app)
    result.revoke(terminate=True)

    # 更新任务状态
    task_manager.update_task_status(
        task_id,
        status="cancelled",
        message="任务已取消"
    )

    logger.info(f"任务已取消: {task_id}, 用户: {user.id}")

    return TaskCancelResponse(
        task_id=task_id,
        status="cancelled",
        message="任务已成功取消"
    )


@router.post("/tasks/pdf", response_model=TaskCreateResponse, summary="提交 PDF 解析任务")
async def submit_pdf_task(
    request: TaskCreateRequest,
    user = Depends(get_current_user_required)
):
    """
    提交 PDF 解析任务

    - **file_path**: PDF 文件路径
    - **options**: 解析选项
    """
    from backend.app.tasks.pdf_tasks import parse_pdf_task

    # 提交任务
    task = parse_pdf_task.apply_async(
        args=[request.file_path, user.id, request.options or {}],
        queue="pdf"
    )

    # 创建任务记录
    task_manager.create_task(
        task.id,
        task_type="pdf_parse",
        user_id=user.id,
        params={"file_path": request.file_path, "options": request.options}
    )

    logger.info(f"PDF 解析任务已提交: {task.id}, 文件: {request.file_path}")

    return TaskCreateResponse(
        task_id=task.id,
        status="pending",
        message="任务已提交，等待执行"
    )


@router.post("/tasks/ner", response_model=TaskCreateResponse, summary="提交 NER 任务")
async def submit_ner_task(
    request: TaskCreateRequest,
    user = Depends(get_current_user_required)
):
    """
    提交 NER 提取任务

    - **result_id**: PDF 处理结果 ID
    - **config_id**: Prompt 配置 ID
    """
    from backend.app.tasks.ner_tasks import ner_extraction_task

    # 提交任务
    task = ner_extraction_task.apply_async(
        args=[request.result_id, user.id, request.config_id, request.domain],
        queue="ner"
    )

    # 创建任务记录
    task_manager.create_task(
        task.id,
        task_type="ner_extraction",
        user_id=user.id,
        params={"result_id": request.result_id, "config_id": request.config_id}
    )

    logger.info(f"NER 任务已提交: {task.id}, 结果ID: {request.result_id}")

    return TaskCreateResponse(
        task_id=task.id,
        status="pending",
        message="任务已提交，等待执行"
    )


@router.post("/tasks/re", response_model=TaskCreateResponse, summary="提交 RE 任务")
async def submit_re_task(
    request: TaskCreateRequest,
    user = Depends(get_current_user_required)
):
    """
    提交关系抽取任务

    - **ner_id**: NER 结果 ID
    - **config_id**: Prompt 配置 ID
    """
    from backend.app.tasks.re_tasks import re_extraction_task

    # 提交任务
    task = re_extraction_task.apply_async(
        args=[request.ner_id, user.id, request.config_id, request.domain],
        queue="re"
    )

    # 创建任务记录
    task_manager.create_task(
        task.id,
        task_type="re_extraction",
        user_id=user.id,
        params={"ner_id": request.ner_id, "config_id": request.config_id}
    )

    logger.info(f"RE 任务已提交: {task.id}, NER ID: {request.ner_id}")

    return TaskCreateResponse(
        task_id=task.id,
        status="pending",
        message="任务已提交，等待执行"
    )


@router.post("/tasks/pipeline", response_model=TaskCreateResponse, summary="提交完整流水线任务")
async def submit_pipeline_task(
    request: TaskCreateRequest,
    user = Depends(get_current_user_required)
):
    """
    提交完整处理流水线任务（PDF -> NER -> RE -> 领域分析）

    - **file_paths**: PDF 文件路径列表
    - **options**: 处理选项
    """
    from backend.app.tasks.batch_tasks import full_pipeline_task

    file_paths = request.file_paths or []

    if not file_paths:
        raise HTTPException(status_code=400, detail="文件路径列表不能为空")

    # 提交任务
    task = full_pipeline_task.apply_async(
        args=[file_paths, user.id, request.options or {}],
        queue="batch"
    )

    # 创建任务记录
    task_manager.create_task(
        task.id,
        task_type="full_pipeline",
        user_id=user.id,
        params={"file_paths": file_paths, "options": request.options}
    )

    logger.info(f"完整流水线任务已提交: {task.id}, 文件数: {len(file_paths)}")

    return TaskCreateResponse(
        task_id=task.id,
        status="pending",
        message=f"任务已提交，共 {len(file_paths)} 个文件"
    )


@router.get("/tasks/statistics", summary="获取任务统计")
async def get_task_statistics(
    user = Depends(get_current_user_required)
):
    """
    获取用户的任务统计信息
    """
    tasks = task_manager.get_user_tasks(user.id)

    stats = {
        "total": len(tasks),
        "pending": len([t for t in tasks if t.get("status") == "pending"]),
        "processing": len([t for t in tasks if t.get("status") == "processing"]),
        "completed": len([t for t in tasks if t.get("status") == "completed"]),
        "failed": len([t for t in tasks if t.get("status") == "failed"]),
        "cancelled": len([t for t in tasks if t.get("status") == "cancelled"])
    }

    return {
        "success": True,
        "statistics": stats
    }