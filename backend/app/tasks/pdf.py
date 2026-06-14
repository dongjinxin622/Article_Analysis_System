# -*- coding: utf-8 -*-
"""
PDF 异步任务处理器

将原 Celery 任务 parse_pdf_task 和 extract_figures_task 改写为 Redis Stream 处理器声明。
"""
from __future__ import annotations

import json
import os
from typing import Any

from loguru import logger
from sqlalchemy import select

from backend.app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure


async def parse_pdf_handler(context: Any) -> dict[str, Any]:
    """PDF 解析任务处理器。

    payload 字段：
      - file_path: PDF 文件路径
      - file_name: 文件名（可选，缺省时从 file_path 提取）
      - user_id: 用户 ID
    """
    payload = context.message.payload
    file_path: str = payload["file_path"]
    user_id: int = payload["user_id"]
    file_name: str = payload.get("file_name") or os.path.basename(file_path)

    logger.info(f"开始 PDF 解析: file={file_path}, user_id={user_id}")

    if not os.path.exists(file_path):
        raise TaskHandlerFailure(
            f"PDF 文件不存在: {file_path}",
            error_code="pdf_file_not_found",
        )

    from backend.app.services.pdf_service import process_pdf

    result = await process_pdf(
        file_path=file_path,
        file_name=file_name,
        user_id=user_id,
    )
    logger.info(f"PDF 解析完成: result_id={result.get('result_id')}")
    return result


async def extract_figures_handler(context: Any) -> dict[str, Any]:
    """图片提取任务处理器。

    payload 字段：
      - result_id: 处理结果 ID
      - user_id: 用户 ID
    """
    payload = context.message.payload
    result_id: str = payload["result_id"]
    user_id: int = payload["user_id"]

    logger.info(f"开始图片提取: result_id={result_id}")

    from backend.app.models.base import AsyncSessionLocal
    from backend.app.models import ProcessingResult

    async with AsyncSessionLocal() as db:
        db_result = await db.execute(
            select(ProcessingResult).where(ProcessingResult.result_id == result_id)
        )
        paper = db_result.scalar_one_or_none()

        if not paper:
            raise TaskHandlerFailure(
                f"处理结果不存在: {result_id}",
                error_code="processing_result_not_found",
            )

        figures: list = []
        if paper.result_json_path:
            try:
                with open(paper.result_json_path, "r", encoding="utf-8") as f:
                    parsed_data = json.load(f)
                figures = parsed_data.get("figures", [])
            except Exception as e:
                logger.warning(f"读取解析结果文件失败: {e}")

    result = {"result_id": result_id, "figures": figures}
    logger.info(f"图片提取完成: result_id={result_id}, figures={len(figures)}")
    return result


ASYNC_TASKS: tuple[AsyncTaskDefinition, ...] = (
    AsyncTaskDefinition("scipdf.pdf.parse", parse_pdf_handler),
    AsyncTaskDefinition("scipdf.pdf.extract_figures", extract_figures_handler),
)
