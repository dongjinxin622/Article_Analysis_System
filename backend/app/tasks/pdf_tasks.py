# -*- coding: utf-8 -*-
"""
PDF 处理 Celery 任务

异步 PDF 解析、提取和处理任务。
"""

import asyncio
import os
from typing import Dict, Any
from loguru import logger

from backend.app.tasks import celery_app
from backend.app.core.config import settings, UPLOADS_DIR, RESULTS_DIR
from backend.app.services.task_manager import TaskManager
from backend.app.api.websocket import manager as ws_manager


task_manager = TaskManager()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def parse_pdf_task(
    self,
    file_path: str,
    user_id: int,
    options: Dict = None
) -> Dict[str, Any]:
    """
    PDF 解析任务

    Args:
        self: Celery 任务实例
        file_path: PDF 文件路径
        user_id: 用户 ID
        options: 解析选项

    Returns:
        解析结果
    """
    task_id = self.request.id
    logger.info(f"开始 PDF 解析任务: {task_id}, 文件: {file_path}")

    # 更新任务状态
    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        message="开始解析 PDF"
    )

    try:
        # 复用 pdf_service 中已有的完整处理流程（含数据库 upsert 逻辑）
        from backend.app.services.pdf_service import process_pdf

        file_name = os.path.basename(file_path)

        async def _parse():
            return await process_pdf(
                file_path=file_path,
                file_name=file_name,
                user_id=user_id
            )

        result = asyncio.run(_parse())

        # 更新进度
        task_manager.update_task_status(
            task_id,
            status="completed",
            progress=100,
            message="PDF 解析完成",
            result=result
        )

        # WebSocket 推送
        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "pdf_completed",
            "data": {
                "task_id": task_id,
                "status": "completed",
                "progress": 100,
                "result_id": result.get('result_id'),
                "title": result.get('title')
            }
        }))

        logger.info(f"PDF 解析任务完成: {task_id}")
        return {"status": "completed", "result": result}

    except Exception as e:
        logger.error(f"PDF 解析任务失败: {task_id}, 错误: {e}")

        # 更新任务状态
        task_manager.update_task_status(
            task_id,
            status="failed",
            progress=0,
            message=f"解析失败: {str(e)}",
            error=str(e)
        )

        # WebSocket 推送错误
        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "pdf_failed",
            "data": {
                "task_id": task_id,
                "status": "failed",
                "error": str(e)
            }
        }))

        # 重试
        if self.request.retries < self.max_retries:
            logger.info(f"任务重试: {task_id}, 第 {self.request.retries + 1} 次")
            raise self.retry(exc=e)
        else:
            return {"status": "failed", "error": str(e)}


@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def extract_figures_task(
    self,
    result_id: str,
    user_id: int
) -> Dict[str, Any]:
    """
    图片提取任务

    Args:
        self: Celery 任务实例
        result_id: 处理结果 ID
        user_id: 用户 ID

    Returns:
        提取结果
    """
    task_id = self.request.id
    logger.info(f"开始图片提取任务: {task_id}, 结果ID: {result_id}")

    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        message="开始提取图片"
    )

    try:
        from backend.app.models.base import AsyncSessionLocal
        from backend.app.models import ProcessingResult
        from sqlalchemy import select

        async def _extract():
            async with AsyncSessionLocal() as db:
                # 获取处理结果
                db_result = await db.execute(
                    select(ProcessingResult).where(ProcessingResult.result_id == result_id)
                )
                paper = db_result.scalar_one_or_none()

                if not paper:
                    raise ValueError(f"处理结果不存在: {result_id}")

                # 从解析结果文件中提取图片信息
                figures = []
                if paper.result_json_path:
                    import json
                    try:
                        with open(paper.result_json_path, 'r', encoding='utf-8') as f:
                            parsed_data = json.load(f)
                        figures = parsed_data.get('figures', [])
                    except Exception as e:
                        logger.warning(f"读取解析结果文件失败: {e}")

                return {"result_id": result_id, "figures": figures}

        result = asyncio.run(_extract())

        task_manager.update_task_status(
            task_id,
            status="completed",
            progress=100,
            message="图片提取完成",
            result=result
        )

        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "figures_extracted",
            "data": {
                "task_id": task_id,
                "status": "completed",
                "result_id": result_id
            }
        }))

        return {"status": "completed", "result": result}

    except Exception as e:
        logger.error(f"图片提取任务失败: {task_id}, 错误: {e}")

        task_manager.update_task_status(
            task_id,
            status="failed",
            message=f"提取失败: {str(e)}",
            error=str(e)
        )

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        else:
            return {"status": "failed", "error": str(e)}
