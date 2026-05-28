# -*- coding: utf-8 -*-
"""
NER 处理 Celery 任务

异步 NER（命名实体识别）处理任务。
"""

import asyncio
import uuid
import json
import os
from typing import Dict, Any, List
from loguru import logger

from backend.app.tasks import celery_app
from backend.app.core.config import settings, NER_RESULTS_DIR
from backend.app.services.task_manager import TaskManager
from backend.app.api.websocket import manager as ws_manager


task_manager = TaskManager()


def _load_parsed_content(paper) -> tuple:
    """从 ProcessingResult 的 JSON 文件中加载解析内容"""
    content = ""
    sections = []
    if paper.result_json_path and os.path.exists(paper.result_json_path):
        try:
            with open(paper.result_json_path, 'r', encoding='utf-8') as f:
                parsed_data = json.load(f)
            sections = parsed_data.get('sections', [])
            # 从 sections 拼接正文内容
            content_parts = []
            for sec in sections:
                if isinstance(sec, dict):
                    text = sec.get('text', '')
                    if text:
                        content_parts.append(text)
            content = '\n\n'.join(content_parts)
        except Exception as e:
            logger.warning(f"加载解析结果 JSON 失败: {e}")
    if not content:
        content = paper.abstract or ""
    return content, sections


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def ner_extraction_task(
    self,
    result_id: str,
    user_id: int,
    config_id: int = None,
    domain: str = None
) -> Dict[str, Any]:
    """
    NER 提取任务

    Args:
        self: Celery 任务实例
        result_id: PDF 处理结果 ID
        user_id: 用户 ID
        config_id: Prompt 配置 ID
        domain: 领域标识（用于领域特定 NER）

    Returns:
        NER 结果
    """
    task_id = self.request.id
    logger.info(f"开始 NER 提取任务: {task_id}, 结果ID: {result_id}")

    # 更新任务状态
    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        message="开始 NER 提取"
    )

    try:
        from backend.app.services.ner_service import NERService
        from backend.app.models.base import AsyncSessionLocal
        from backend.app.models import ProcessingResult, NERResult
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

                # 从 JSON 文件加载解析内容（ProcessingResult 模型无 content/sections 列）
                content, sections = _load_parsed_content(paper)

                # 更新进度
                task_manager.update_task_status(
                    task_id,
                    progress=20,
                    message="加载 NER 服务"
                )

                # 创建 NER 服务
                ner_service = NERService()

                # 执行 NER
                task_manager.update_task_status(
                    task_id,
                    progress=40,
                    message="执行 NER 提取"
                )

                ner_result = await ner_service.extract_entities(
                    content=content,
                    sections=sections,
                    config_id=config_id,
                    domain=domain
                )

                # 生成 NER ID
                ner_id = str(uuid.uuid4())

                # 保存结果到数据库
                task_manager.update_task_status(
                    task_id,
                    progress=80,
                    message="保存 NER 结果"
                )

                db_ner = NERResult(
                    ner_id=ner_id,
                    result_id=result_id,
                    entity_count=len(ner_result.get('entities', [])),
                    entity_types=ner_result.get('entity_types'),
                    status='completed',
                    user_id=user_id
                )
                db.add(db_ner)
                await db.commit()

                # 保存结果文件
                ner_file = NER_RESULTS_DIR / f"{ner_id}.json"
                ner_file.parent.mkdir(parents=True, exist_ok=True)
                with open(ner_file, 'w', encoding='utf-8') as f:
                    json.dump(ner_result, f, ensure_ascii=False, indent=2)

                return {
                    "ner_id": ner_id,
                    "result_id": result_id,
                    "entity_count": len(ner_result.get('entities', [])),
                    "entities": ner_result.get('entities', [])
                }

        result = asyncio.run(_extract())

        # 更新进度
        task_manager.update_task_status(
            task_id,
            status="completed",
            progress=100,
            message="NER 提取完成",
            result=result
        )

        # WebSocket 推送
        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "ner_completed",
            "data": {
                "task_id": task_id,
                "status": "completed",
                "progress": 100,
                "ner_id": result.get('ner_id'),
                "entity_count": result.get('entity_count')
            }
        }))

        logger.info(f"NER 提取任务完成: {task_id}, 实体数: {result.get('entity_count')}")
        return {"status": "completed", "result": result}

    except Exception as e:
        logger.error(f"NER 提取任务失败: {task_id}, 错误: {e}")

        # 更新任务状态
        task_manager.update_task_status(
            task_id,
            status="failed",
            message=f"NER 提取失败: {str(e)}",
            error=str(e)
        )

        # WebSocket 推送错误
        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "ner_failed",
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
def ner_batch_task(
    self,
    result_ids: List[str],
    user_id: int,
    config_id: int = None
) -> Dict[str, Any]:
    """
    批量 NER 提取任务

    Args:
        self: Celery 任务实例
        result_ids: PDF 处理结果 ID 列表
        user_id: 用户 ID
        config_id: Prompt 配置 ID

    Returns:
        批量处理结果
    """
    task_id = self.request.id
    total = len(result_ids)
    logger.info(f"开始批量 NER 任务: {task_id}, 数量: {total}")

    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        message=f"开始批量 NER 提取，共 {total} 篇"
    )

    results = []
    errors = []

    for idx, result_id in enumerate(result_ids):
        progress = int((idx / total) * 100)

        task_manager.update_task_status(
            task_id,
            progress=progress,
            message=f"处理第 {idx + 1}/{total} 篇"
        )

        try:
            # 调用单个 NER 任务（同步等待）
            single_result = ner_extraction_task.apply_async(
                args=[result_id, user_id, config_id],
                queue="ner"
            ).get()

            if single_result.get('status') == 'completed':
                results.append(single_result.get('result'))
            else:
                errors.append({
                    "result_id": result_id,
                    "error": single_result.get('error')
                })

        except Exception as e:
            errors.append({
                "result_id": result_id,
                "error": str(e)
            })

    # 更新最终状态
    task_manager.update_task_status(
        task_id,
        status="completed",
        progress=100,
        message=f"批量 NER 完成，成功 {len(results)} 篇，失败 {len(errors)} 篇",
        result={"success_count": len(results), "error_count": len(errors)}
    )

    # WebSocket 推送
    asyncio.run(ws_manager.send_progress(task_id, {
        "event": "ner_batch_completed",
        "data": {
            "task_id": task_id,
            "status": "completed",
            "success_count": len(results),
            "error_count": len(errors)
        }
    }))

    return {
        "status": "completed",
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors
    }
