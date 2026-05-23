"""
综合分析 API
整合 PDF → NER → RE → 技术路线 → 实验方案 → Jc → 报告 的完整流程
支持一键上传PDF并自动完成全流程
使用 Redis TaskManager 持久化任务状态，关闭页面后仍可查看进度
支持Prompt Name（从数据库获取）和文件路径两种方式
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import uuid
import asyncio
import logging
import json
import tempfile
import os

from backend.app.services.comprehensive_service import get_comprehensive_service
from backend.app.services.pdf_service import process_pdf
from backend.app.services.storage_service import get_storage_service
from backend.app.services.ner_service import load_ner_entities
from backend.app.services.re_service import load_re_relations
from backend.app.services.ner_re_pipeline import process_ner_re_pipeline
from backend.app.services.task_manager import TaskManager
from backend.app.services.prompt_service import get_prompt_service
from backend.app.api.deps_user import get_current_user_required
from backend.app.core.config import BASE_DIR
from backend.app.models.base import get_db_context
from backend.app.models.comprehensive import ComprehensiveTask
from datetime import datetime
from sqlalchemy import select, delete
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/comprehensive")

# 初始化 TaskManager（使用 Redis 持久化）
_task_manager = TaskManager()


# ========== 默认 Prompt 文件路径 ==========

def _get_default_ner_prompt():
    """获取默认 NER prompt 文件"""
    ner_dir = BASE_DIR / "scipdf" / "ner_queries"
    if ner_dir.exists():
        for pattern in ["material_ner.txt", "ner*.txt"]:
            matches = list(ner_dir.glob(pattern))
            if matches:
                return str(matches[0])
    return None

def _get_default_re_prompt():
    """获取默认 RE prompt 文件"""
    re_dir = BASE_DIR / "scipdf" / "re_queries"
    if re_dir.exists():
        for pattern in ["material_re.txt", "re*.txt"]:
            matches = list(re_dir.glob(pattern))
            if matches:
                return str(matches[0])
    return None


async def resolve_prompt_to_file(query_file: str, category: str = "ner", user_id: Optional[int] = None) -> str:
    """
    解析Prompt文件路径或名称

    如果query_file不包含路径分隔符，视为prompt name，从数据库获取内容并写入临时文件
    如果包含路径分隔符，视为文件路径，验证后返回

    Args:
        query_file: Prompt文件路径或名称
        category: 分类（ner/re），用于从数据库查找
        user_id: 用户ID（可选），用于过滤用户私有模板

    Returns:
        实际的Prompt文件路径
    """
    # 检查是否包含路径分隔符
    if '/' in query_file or '\\' in query_file:
        # 是文件路径，验证存在性
        if not Path(query_file).exists():
            raise HTTPException(
                status_code=400,
                detail=f"Prompt 文件不存在: {query_file}"
            )
        return query_file

    # 是prompt name，从数据库获取
    prompt_service = get_prompt_service()
    prompt_content = await prompt_service.get_prompt_content(query_file, user_id=user_id)

    if not prompt_content:
        # 数据库中没有，尝试查找默认文件
        default_file = _get_default_ner_prompt() if category == "ner" else _get_default_re_prompt()
        if default_file:
            logger.info(f"Prompt '{query_file}' 不存在于数据库，使用默认文件: {default_file}")
            return default_file
        raise HTTPException(
            status_code=400,
            detail=f"Prompt 模板 '{query_file}' 不存在"
        )

    # 写入临时文件
    temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
    temp_file.write(prompt_content)
    temp_file.close()

    logger.info(f"Prompt '{query_file}' 已从数据库解析为临时文件: {temp_file.name}")
    return temp_file.name


DEFAULT_NER_QUERY_FILE = _get_default_ner_prompt()
DEFAULT_RE_QUERY_FILE = _get_default_re_prompt()


# ========== Schemas ==========

class OneClickResponse(BaseModel):
    """一键处理响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="响应消息")
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(default="pending", description="任务状态")


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str
    task_type: str = "one_click_analysis"
    status: str
    progress: int = 0
    current_step: str = ""
    message: str = ""
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class TaskListItem(BaseModel):
    """任务列表项"""
    task_id: str
    task_type: str
    status: str
    progress: int
    current_step: str = ""
    message: str = ""
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    tasks: List[TaskListItem]


# ========== MySQL 持久化辅助函数 ==========

async def _save_task_to_mysql(task_info: dict):
    """将任务信息同步写入 MySQL（成功或失败时调用）"""
    try:
        async with get_db_context() as db:
            # 检查是否已存在
            existing = await db.execute(
                select(ComprehensiveTask).where(ComprehensiveTask.task_id == task_info["task_id"])
            )
            existing_task = existing.scalar_one_or_none()

            now = datetime.now()
            if existing_task:
                # 更新
                existing_task.status = task_info.get("status", existing_task.status)
                existing_task.progress = task_info.get("progress", existing_task.progress)
                existing_task.current_step = task_info.get("stage", task_info.get("current_step", ""))
                existing_task.message = task_info.get("message", "")
                existing_task.result = task_info.get("result")
                existing_task.error = task_info.get("error")
                existing_task.updated_at = now
                if task_info.get("status") in ("completed", "failed"):
                    existing_task.completed_at = now
            else:
                # 新建
                new_task = ComprehensiveTask(
                    task_id=task_info["task_id"],
                    user_id=task_info["user_id"],
                    status=task_info.get("status", "pending"),
                    progress=task_info.get("progress", 0),
                    current_step=task_info.get("stage", task_info.get("current_step", "")),
                    message=task_info.get("message", ""),
                    result=task_info.get("result"),
                    error=task_info.get("error"),
                    params=task_info.get("params"),
                    created_at=datetime.fromtimestamp(task_info.get("created_at", now.timestamp())),
                    updated_at=now,
                    completed_at=now if task_info.get("status") in ("completed", "failed") else None
                )
                db.add(new_task)
        logger.info(f"[MySQL] 任务 {task_info['task_id']} 已同步到数据库")
    except Exception as e:
        logger.error(f"[MySQL] 同步任务失败: {e}")


def _task_info_to_response(task_info: dict) -> TaskStatusResponse:
    """将任务字典转换为 TaskStatusResponse"""
    return TaskStatusResponse(
        task_id=task_info.get("task_id", ""),
        task_type=task_info.get("task_type", "one_click_analysis"),
        status=task_info.get("status", "unknown"),
        progress=task_info.get("progress", 0),
        current_step=task_info.get("stage", task_info.get("current_step", "")),
        message=task_info.get("message", ""),
        result=task_info.get("result"),
        error=task_info.get("error"),
        created_at=task_info.get("created_at"),
        updated_at=task_info.get("updated_at")
    )


# ========== API Endpoints ==========

@router.get("/tasks", response_model=TaskListResponse, summary="获取用户任务列表")
async def get_user_tasks(
    user = Depends(get_current_user_required)
):
    """
    获取用户的所有任务列表

    返回用户创建的所有一键处理任务，包括正在运行和历史任务
    合并 Redis（活跃/近期任务）和 MySQL（历史持久化任务）
    """
    # 从 Redis 获取活跃/近期任务
    redis_tasks = _task_manager.get_user_tasks(user.id)
    redis_task_ids = {t.get("task_id") for t in redis_tasks}

    task_list = [
        TaskListItem(
            task_id=t.get("task_id", ""),
            task_type=t.get("task_type", "one_click_analysis"),
            status=t.get("status", "unknown"),
            progress=t.get("progress", 0),
            current_step=t.get("stage", t.get("current_step", "")),
            message=t.get("message", ""),
            created_at=t.get("created_at"),
            updated_at=t.get("updated_at")
        )
        for t in redis_tasks
    ]

    # 从 MySQL 补充已过期但持久化的历史任务
    try:
        async with get_db_context() as db:
            result = await db.execute(
                select(ComprehensiveTask)
                .where(ComprehensiveTask.user_id == user.id)
                .order_by(ComprehensiveTask.created_at.desc())
                .limit(200)
            )
            db_tasks = result.scalars().all()

            for db_task in db_tasks:
                # 跳过已在 Redis 中的任务
                if db_task.task_id in redis_task_ids:
                    continue
                task_list.append(TaskListItem(
                    task_id=db_task.task_id,
                    task_type="one_click_analysis",
                    status=db_task.status,
                    progress=db_task.progress,
                    current_step=db_task.current_step or "",
                    message=db_task.message or "",
                    created_at=db_task.created_at.timestamp() if db_task.created_at else None,
                    updated_at=db_task.updated_at.timestamp() if db_task.updated_at else None
                ))
    except Exception as e:
        logger.error(f"[MySQL] 查询历史任务失败: {e}")

    # 按创建时间降序排序
    task_list.sort(key=lambda x: x.created_at or 0, reverse=True)

    return TaskListResponse(total=len(task_list), tasks=task_list)


@router.get("/status/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
async def get_task_status(
    task_id: str,
    user = Depends(get_current_user_required)
):
    """
    查询任务状态

    - **task_id**: 任务 ID

    返回进度、当前步骤、结果（完成时）
    优先从 Redis 查询，Redis 未命中时回退查询 MySQL
    """
    task_info = _task_manager.get_task_status(task_id)

    # Redis 未命中，尝试从 MySQL 回退查询
    if task_info.get("status") == "not_found":
        try:
            async with get_db_context() as db:
                result = await db.execute(
                    select(ComprehensiveTask).where(ComprehensiveTask.task_id == task_id)
                )
                db_task = result.scalar_one_or_none()
                if db_task:
                    # 将 MySQL 记录转换为响应格式
                    task_info = {
                        "task_id": db_task.task_id,
                        "task_type": "one_click_analysis",
                        "user_id": db_task.user_id,
                        "status": db_task.status,
                        "progress": db_task.progress,
                        "stage": db_task.current_step,
                        "message": db_task.message or "",
                        "result": db_task.result,
                        "error": db_task.error,
                        "created_at": db_task.created_at.timestamp() if db_task.created_at else None,
                        "updated_at": db_task.updated_at.timestamp() if db_task.updated_at else None
                    }
                    logger.info(f"[MySQL回退] 任务 {task_id} 从数据库加载")
        except Exception as e:
            logger.error(f"[MySQL回退] 查询任务失败: {e}")

    if task_info.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在或已过期")

    # 验证任务所有权
    if task_info.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="无权访问此任务")

    return _task_info_to_response(task_info)


@router.delete("/task/{task_id}", summary="删除任务")
async def delete_task(
    task_id: str,
    user = Depends(get_current_user_required)
):
    """
    删除任务记录

    - **task_id**: 任务 ID
    """
    task_info = _task_manager.get_task_status(task_id)

    if task_info.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="任务不存在")

    # 验证任务所有权
    if task_info.get("user_id") != user.id:
        raise HTTPException(status_code=403, detail="无权删除此任务")

    _task_manager.delete_task(task_id)

    # 同步删除 MySQL 记录
    try:
        async with get_db_context() as db:
            await db.execute(
                delete(ComprehensiveTask).where(ComprehensiveTask.task_id == task_id)
            )
            logger.info(f"[MySQL] 任务 {task_id} 已从数据库删除")
    except Exception as e:
        logger.error(f"[MySQL] 删除任务失败: {e}")

    return {"success": True, "message": "任务已删除"}


@router.get("/active", response_model=TaskListResponse, summary="获取活跃任务")
async def get_active_tasks(
    user = Depends(get_current_user_required)
):
    """
    获取用户的活跃任务（正在运行的任务）

    用于页面加载时检查是否有正在进行的任务
    """
    all_tasks = _task_manager.get_user_tasks(user.id)

    # 过滤出活跃任务
    active_tasks = [
        t for t in all_tasks
        if t.get("status") in ["pending", "processing", "running"]
    ]

    task_list = [
        TaskListItem(
            task_id=t.get("task_id", ""),
            task_type=t.get("task_type", "one_click_analysis"),
            status=t.get("status", "unknown"),
            progress=t.get("progress", 0),
            current_step=t.get("stage", t.get("current_step", "")),
            message=t.get("message", ""),
            created_at=t.get("created_at"),
            updated_at=t.get("updated_at")
        )
        for t in active_tasks
    ]

    return TaskListResponse(total=len(task_list), tasks=task_list)


# ========== 一键处理接口 ==========

@router.post("/one-click", response_model=OneClickResponse, summary="一键处理PDF")
async def one_click_analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF 文件"),
    top_k: int = 10,
    target_doi: Optional[str] = None,
    ner_query_file: Optional[str] = None,
    re_query_file: Optional[str] = None,
    user = Depends(get_current_user_required)
):
    """
    一键处理 PDF 文件

    自动执行完整流程：PDF解析 → NER → RE → 技术路线 → 实验方案 → Jc → LLM报告

    - **file**: PDF 文件
    - **top_k**: 相似论文数量
    - **target_doi**: 目标 DOI（用于 Jc 排名，可选）
    - **ner_query_file**: NER Prompt 模板名称（如"material_ner"）或文件路径（可选）
    - **re_query_file**: RE Prompt 模板名称（如"material_re"）或文件路径（可选）

    返回任务 ID，可通过 /status/{task_id} 查询进度
    任务状态持久化到 Redis，关闭页面后仍可查看进度
    """
    task_id = str(uuid.uuid4())

    # 验证文件类型
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="只支持 PDF 文件")

    # Prompt 文件：可以是名称或路径，后台任务中解析
    ner_prompt_name_or_path = ner_query_file or "material_ner"
    re_prompt_name_or_path = re_query_file or "material_re"

    # 验证 RE Prompt 文件
    # 创建任务记录（持久化到 Redis）
    _task_manager.create_task(
        task_id=task_id,
        task_type="one_click_analysis",
        user_id=user.id,
        params={
            "file_name": file.filename,
            "top_k": top_k,
            "target_doi": target_doi,
            "ner_query_file": ner_prompt_name_or_path,
            "re_query_file": re_prompt_name_or_path
        }
    )

    # 定义后台任务
    async def run_one_click_analysis():
        # 用于清理的临时文件列表
        temp_prompt_files = []
        try:
            _task_manager.update_task_status(
                task_id=task_id,
                status="running",
                progress=0,
                stage="初始化",
                message="任务开始执行"
            )
            logger.info(f"[一键处理] 任务 {task_id} 开始")

            # 解析Prompt文件（支持名称和路径）
            ner_prompt_file = await resolve_prompt_to_file(ner_prompt_name_or_path, "ner", user_id=user.id)
            re_prompt_file = await resolve_prompt_to_file(re_prompt_name_or_path, "re", user_id=user.id)

            # 记录是否是临时文件（需要清理）
            if '/' not in ner_prompt_name_or_path and '\\' not in ner_prompt_name_or_path:
                temp_prompt_files.append(ner_prompt_file)
            if '/' not in re_prompt_name_or_path and '\\' not in re_prompt_name_or_path:
                temp_prompt_files.append(re_prompt_file)

            logger.info(f"[一键处理] NER Prompt: {ner_prompt_file}, RE Prompt: {re_prompt_file}")

            # Step 1: 上传并解析 PDF
            _task_manager.update_task_status(
                task_id=task_id,
                stage="pdf_parse",
                message="正在解析 PDF...",
                progress=5
            )

            # 保存文件
            storage = get_storage_service()
            file_content = await file.read()
            from io import BytesIO
            file_stream = BytesIO(file_content)

            save_result = await storage.save_upload_file(
                file_content=file_stream,
                file_name=file.filename,
                user_id=user.id
            )

            if not save_result["success"]:
                raise Exception("文件保存失败")

            pdf_path = save_result["file_path"]
            logger.info(f"[一键处理] PDF 保存成功: {pdf_path}")

            # 解析 PDF
            pdf_result = await process_pdf(
                file_path=pdf_path,
                file_name=save_result["original_name"],
                user_id=user.id
            )

            if not pdf_result["success"]:
                raise Exception(f"PDF 解析失败: {pdf_result.get('error', '未知错误')}")

            result_id = pdf_result["result_id"]
            doi = pdf_result.get("doi")
            logger.info(f"[一键处理] PDF 解析成功, result_id={result_id}, doi={doi}")

            _task_manager.update_task_status(
                task_id=task_id,
                progress=15,
                message="PDF 解析完成，开始 NER+RE 流水线处理..."
            )

            # Step 2+3: NER+RE 流水线处理（每个片段 NER→RE 流水线，所有片段并行）
            _task_manager.update_task_status(
                task_id=task_id,
                stage="ner_re_pipeline",
                message="正在执行 NER+RE 流水线处理...",
                progress=15
            )

            # 进度回调
            async def ner_re_progress_callback(stage, completed, total, message):
                # NER 占 15-35%，RE 占 35-50%
                if stage == "ner":
                    percent = int(15 + (completed / total) * 20)  # 15% → 35%
                else:  # re
                    percent = int(35 + (completed / total) * 15)  # 35% → 50%
                _task_manager.update_task_status(
                    task_id=task_id,
                    stage=f"ner_re_{stage}",
                    message=message,
                    progress=percent
                )

            pipeline_result = await process_ner_re_pipeline(
                result_id=result_id,
                ner_query_file=ner_prompt_file,
                re_query_file=re_prompt_file,
                user_id=user.id,
                progress_callback=ner_re_progress_callback
            )

            if not pipeline_result["success"]:
                raise Exception(f"NER+RE 流水线处理失败: {pipeline_result.get('error', '未知错误')}")

            ner_id = pipeline_result["ner_id"]
            re_id = pipeline_result["re_id"]
            ner_entities = await load_ner_entities(ner_id)
            re_relations = await load_re_relations(re_id)
            entity_count = pipeline_result.get("entity_count", len(ner_entities))
            relation_count = pipeline_result.get("relation_count", len(re_relations))
            logger.info(f"[一键处理] NER+RE 完成: {entity_count}实体, {relation_count}关系")

            _task_manager.update_task_status(
                task_id=task_id,
                progress=50,
                message=f"NER+RE 完成 ({entity_count}实体, {relation_count}关系)，开始深度分析..."
            )

            # Step 4: 执行深度分析
            _task_manager.update_task_status(
                task_id=task_id,
                stage="tech_route",
                message="正在分析技术路线..."
            )

            pdf_content = {
                "title": pdf_result.get("title", ""),
                "doi": doi,
                "abstract": pdf_result.get("abstract", "")
            }

            # 提取原文内容用于Jc条件补充
            content_text = ""
            # 从PDF解析结果中提取原文
            if pdf_result.get("sections"):
                sections = pdf_result.get("sections", [])
                content_text = "\n".join([
                    s.get("text", "") for s in sections if s.get("text")
                ])
            elif pdf_result.get("abstract"):
                content_text = pdf_result.get("abstract", "")

            actual_doi = target_doi or doi

            # 进度回调（必须是 async 函数才能被 await）
            async def progress_callback(step: str, message: str, progress: int):
                _task_manager.update_task_status(
                    task_id=task_id,
                    stage=step,
                    message=message,
                    progress=50 + int(progress * 0.45)
                )

            service = get_comprehensive_service()
            analysis_result = await service.run_full_analysis(
                pdf_path=pdf_path,
                ner_entities=ner_entities,
                re_relations=re_relations,
                pdf_content=pdf_content,
                content_text=content_text,  # 传递原文用于Jc条件补充
                target_doi=actual_doi,
                top_k=top_k,
                progress_callback=progress_callback,
                task_id=task_id  # 传递任务ID，使报告文件名与task_id匹配
            )

            # 添加中间结果信息
            analysis_result["pdf_info"] = {
                "result_id": result_id,
                "ner_id": ner_id,
                "re_id": re_id,
                "doi": doi,
                "title": pdf_result.get("title"),
                "file_name": save_result["original_name"],
                "ner_query_file": ner_prompt_file,
                "re_query_file": re_prompt_file,
                "ner_entity_count": len(ner_entities),
                "re_relation_count": len(re_relations),
                "ner_json_path": pipeline_result.get("ner_json_path"),
                "ner_excel_path": pipeline_result.get("ner_excel_path"),
                "re_json_path": pipeline_result.get("re_json_path"),
                "re_excel_path": pipeline_result.get("re_excel_path")
            }

            _task_manager.update_task_status(
                task_id=task_id,
                status="completed",
                progress=100,
                message=analysis_result.get("message", "一键处理完成"),
                result=analysis_result
            )

            # 同步写入 MySQL 持久化
            task_info = _task_manager.get_task_status(task_id)
            await _save_task_to_mysql(task_info)

            logger.info(f"[一键处理] 任务 {task_id} 完成")

        except Exception as e:
            logger.error(f"[一键处理] 任务 {task_id} 失败: {e}")
            _task_manager.update_task_status(
                task_id=task_id,
                status="failed",
                message=str(e),
                error=str(e),
                progress=0
            )

            # 同步写入 MySQL 持久化
            task_info = _task_manager.get_task_status(task_id)
            await _save_task_to_mysql(task_info)

        finally:
            # 清理临时Prompt文件
            for temp_file in temp_prompt_files:
                try:
                    if Path(temp_file).exists():
                        os.unlink(temp_file)
                        logger.info(f"[一键处理] 清理临时文件: {temp_file}")
                except Exception as cleanup_error:
                    logger.warning(f"[一键处理] 清理临时文件失败: {cleanup_error}")

    # 启动后台任务
    background_tasks.add_task(run_one_click_analysis)

    return OneClickResponse(
        success=True,
        message="一键处理任务已启动",
        task_id=task_id,
        status="pending"
    )


# ========== 报告导出接口 ==========

from fastapi.responses import FileResponse
from pydantic import BaseModel


class ReportExportRequest(BaseModel):
    """报告导出请求"""
    task_id: str = Field(..., description="任务 ID")
    format: str = Field("md", description="报告格式：md/excel/pdf")


class ReportExportResponse(BaseModel):
    """报告导出响应"""
    success: bool
    message: str
    file_path: Optional[str] = None
    download_url: Optional[str] = None


@router.get("/report/{task_id}", summary="下载分析报告")
async def download_report(
    task_id: str,
    format: str = "md",
    user = Depends(get_current_user_required)
):
    """
    下载分析报告

    支持三种格式：
    - **md**: Markdown 格式
    - **excel**: Excel 格式（最多 9 个 Sheet）
    - **pdf**: PDF 格式

    Args:
        task_id: 任务 ID
        format: 报告格式（md/excel/pdf）
    """
    try:
        # 验证任务所有权
        task_info = _task_manager.get_task_status(task_id)
        if task_info.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="报告对应的任务不存在")
        if task_info.get("user_id") != user.id:
            raise HTTPException(status_code=403, detail="无权下载此报告")

        from backend.app.core.config import RESULTS_DIR
        from pathlib import Path

        report_dir = Path(RESULTS_DIR) / "reports"

        # 根据格式确定文件扩展名
        if format == 'md' or format == 'markdown':
            file_ext = 'md'
            media_type = 'text/markdown'
        elif format == 'excel' or format == 'xlsx':
            file_ext = 'xlsx'
            media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        elif format == 'pdf':
            file_ext = 'pdf'
            media_type = 'application/pdf'
        else:
            raise HTTPException(status_code=400, detail=f"不支持的格式：{format}")

        # 查找报告文件
        pattern = f"{task_id}_report.{file_ext}"
        matching_files = list(report_dir.glob(pattern))

        if not matching_files:
            # 尝试匹配任务ID前缀
            matching_files = list(report_dir.glob(f"*{task_id}*.{file_ext}"))

        if not matching_files:
            # 尝试匹配UUID短格式（去掉连字符，只取前8位）
            # UUID格式如 c044b5e2-xxxx-xxxx-xxxx-xxxxxxxxxxxx -> 取 c044b5e2
            short_uuid = task_id.split('-')[0] if '-' in task_id else task_id[:8]
            matching_files = list(report_dir.glob(f"*{short_uuid}*.{file_ext}"))

        if not matching_files:
            raise HTTPException(
                status_code=404,
                detail=f"报告文件不存在：{pattern}"
            )

        file_path = matching_files[0]

        return FileResponse(
            str(file_path),
            media_type=media_type,
            filename=f"{task_id}_report.{file_ext}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下载报告失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/report/export", response_model=ReportExportResponse, summary="导出报告")
async def export_report(
    request: ReportExportRequest,
    user = Depends(get_current_user_required)
):
    """
    导出指定格式的报告

    Args:
        request: 导出请求（task_id, format）

    Returns:
        导出结果（success, file_path, download_url）
    """
    try:
        # 验证任务所有权
        task_info = _task_manager.get_task_status(request.task_id)
        if task_info.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="任务不存在")
        if task_info.get("user_id") != user.id:
            raise HTTPException(status_code=403, detail="无权导出此报告")

        from backend.app.core.config import RESULTS_DIR
        from pathlib import Path

        report_dir = Path(RESULTS_DIR) / "reports"

        # 验证格式
        if request.format not in ['md', 'markdown', 'excel', 'xlsx', 'pdf']:
            raise HTTPException(status_code=400, detail=f"不支持的格式：{request.format}")

        # 确定文件扩展名
        file_ext = 'md' if request.format in ['md', 'markdown'] else ('xlsx' if request.format in ['excel', 'xlsx'] else 'pdf')

        # 查找报告文件
        pattern = f"{request.task_id}_report.{file_ext}"
        matching_files = list(report_dir.glob(pattern))

        if not matching_files:
            matching_files = list(report_dir.glob(f"*{request.task_id}*.{file_ext}"))

        if not matching_files:
            raise HTTPException(
                status_code=404,
                detail=f"报告文件不存在，请先完成任务分析"
            )

        file_path = matching_files[0]

        return ReportExportResponse(
            success=True,
            message="报告导出成功",
            file_path=str(file_path),
            download_url=f"/api/v1/comprehensive/report/{request.task_id}?format={file_ext}"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导出报告失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/report/list/{task_id}", summary="获取任务报告列表")
async def get_report_list(
    task_id: str,
    user = Depends(get_current_user_required)
):
    """
    获取任务的所有报告文件列表

    返回该任务生成的所有格式报告及其下载链接
    """
    try:
        # 验证任务所有权
        task_info = _task_manager.get_task_status(task_id)
        if task_info.get("status") == "not_found":
            raise HTTPException(status_code=404, detail="任务不存在")
        if task_info.get("user_id") != user.id:
            raise HTTPException(status_code=403, detail="无权访问此任务报告")

        from backend.app.core.config import RESULTS_DIR
        from pathlib import Path

        report_dir = Path(RESULTS_DIR) / "reports"

        reports = []
        formats = ['md', 'xlsx', 'pdf']

        for fmt in formats:
            pattern = f"{task_id}_report.{fmt}"
            matching_files = list(report_dir.glob(pattern))

            if not matching_files:
                matching_files = list(report_dir.glob(f"*{task_id}*.{fmt}"))

            if matching_files:
                file_path = matching_files[0]
                reports.append({
                    "format": fmt,
                    "file_path": str(file_path),
                    "download_url": f"/api/v1/comprehensive/report/{task_id}?format={fmt}",
                    "file_size": file_path.stat().st_size if file_path.exists() else 0
                })

        return {
            "task_id": task_id,
            "reports": reports,
            "total": len(reports)
        }

    except Exception as e:
        logger.error(f"获取报告列表失败：{e}")
        raise HTTPException(status_code=500, detail=str(e))