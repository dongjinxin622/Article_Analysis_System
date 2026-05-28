# -*- coding: utf-8 -*-
"""
RE（关系抽取）处理 Celery 任务

异步关系抽取处理任务。
"""

import asyncio
import uuid
import json
import os
from typing import Dict, Any, List
from loguru import logger

from backend.app.tasks import celery_app
from backend.app.core.config import settings, RE_RESULTS_DIR
from backend.app.services.task_manager import TaskManager
from backend.app.api.websocket import manager as ws_manager


task_manager = TaskManager()


def _load_ner_content(ner_data) -> str:
    """从 NER 结果关联的 ProcessingResult JSON 文件中加载文本内容"""
    content = ""
    if ner_data.processing_result and ner_data.processing_result.result_json_path:
        json_path = ner_data.processing_result.result_json_path
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    parsed_data = json.load(f)
                sections = parsed_data.get('sections', [])
                content_parts = []
                for sec in sections:
                    if isinstance(sec, dict):
                        text = sec.get('text', '')
                        if text:
                            content_parts.append(text)
                content = '\n\n'.join(content_parts)
            except Exception as e:
                logger.warning(f"加载解析结果 JSON 失败: {e}")
    if not content and ner_data.processing_result:
        content = ner_data.processing_result.abstract or ""
    return content


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def re_extraction_task(
    self,
    ner_id: str,
    user_id: int,
    config_id: int = None,
    domain: str = None
) -> Dict[str, Any]:
    """
    关系抽取任务

    Args:
        self: Celery 任务实例
        ner_id: NER 结果 ID
        user_id: 用户 ID
        config_id: Prompt 配置 ID
        domain: 领域标识

    Returns:
        RE 结果
    """
    task_id = self.request.id
    logger.info(f"开始 RE 提取任务: {task_id}, NER ID: {ner_id}")

    # 更新任务状态
    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        message="开始关系抽取"
    )

    try:
        from backend.app.services.re_service import REService
        from backend.app.models.base import AsyncSessionLocal
        from backend.app.models import NERResult, REResult
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        async def _extract():
            async with AsyncSessionLocal() as db:
                # 获取 NER 结果（预加载关联的 ProcessingResult）
                db_result = await db.execute(
                    select(NERResult)
                    .where(NERResult.ner_id == ner_id)
                    .options(selectinload(NERResult.processing_result))
                )
                ner_data = db_result.scalar_one_or_none()

                if not ner_data:
                    raise ValueError(f"NER 结果不存在: {ner_id}")

                entities = ner_data.entities if hasattr(ner_data, 'entities') else []

                # 从关联的 ProcessingResult JSON 文件加载文本内容
                content = _load_ner_content(ner_data)

                # 更新进度
                task_manager.update_task_status(
                    task_id,
                    progress=20,
                    message="加载 RE 服务"
                )

                # 创建 RE 服务
                re_service = REService()

                # 执行关系抽取
                task_manager.update_task_status(
                    task_id,
                    progress=40,
                    message="执行关系抽取"
                )

                re_result = await re_service.extract_relations(
                    entities=entities,
                    content=content,
                    config_id=config_id,
                    domain=domain
                )

                # 生成 RE ID
                re_id = str(uuid.uuid4())

                # 保存结果到数据库
                task_manager.update_task_status(
                    task_id,
                    progress=80,
                    message="保存 RE 结果"
                )

                db_re = REResult(
                    re_id=re_id,
                    ner_id=ner_id,
                    result_id=ner_data.result_id,
                    relation_count=len(re_result.get('relations', [])),
                    relation_types=re_result.get('relation_types'),
                    status='completed',
                    user_id=user_id
                )
                db.add(db_re)
                await db.commit()

                # 保存结果文件
                re_file = RE_RESULTS_DIR / f"{re_id}.json"
                re_file.parent.mkdir(parents=True, exist_ok=True)
                with open(re_file, 'w', encoding='utf-8') as f:
                    json.dump(re_result, f, ensure_ascii=False, indent=2)

                return {
                    "re_id": re_id,
                    "ner_id": ner_id,
                    "relation_count": len(re_result.get('relations', [])),
                    "relations": re_result.get('relations', [])
                }

        result = asyncio.run(_extract())

        # 更新进度
        task_manager.update_task_status(
            task_id,
            status="completed",
            progress=100,
            message="关系抽取完成",
            result=result
        )

        # WebSocket 推送
        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "re_completed",
            "data": {
                "task_id": task_id,
                "status": "completed",
                "progress": 100,
                "re_id": result.get('re_id'),
                "relation_count": result.get('relation_count')
            }
        }))

        logger.info(f"RE 提取任务完成: {task_id}, 关系数: {result.get('relation_count')}")
        return {"status": "completed", "result": result}

    except Exception as e:
        logger.error(f"RE 提取任务失败: {task_id}, 错误: {e}")

        # 更新任务状态
        task_manager.update_task_status(
            task_id,
            status="failed",
            message=f"关系抽取失败: {str(e)}",
            error=str(e)
        )

        # WebSocket 推送错误
        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "re_failed",
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
def re_batch_task(
    self,
    ner_ids: List[str],
    user_id: int,
    config_id: int = None
) -> Dict[str, Any]:
    """
    批量关系抽取任务

    Args:
        self: Celery 任务实例
        ner_ids: NER 结果 ID 列表
        user_id: 用户 ID
        config_id: Prompt 配置 ID

    Returns:
        批量处理结果
    """
    task_id = self.request.id
    total = len(ner_ids)
    logger.info(f"开始批量 RE 任务: {task_id}, 数量: {total}")

    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        message=f"开始批量关系抽取，共 {total} 篇"
    )

    results = []
    errors = []

    for idx, ner_id in enumerate(ner_ids):
        progress = int((idx / total) * 100)

        task_manager.update_task_status(
            task_id,
            progress=progress,
            message=f"处理第 {idx + 1}/{total} 篇"
        )

        try:
            # 调用单个 RE 任务（同步等待）
            single_result = re_extraction_task.apply_async(
                args=[ner_id, user_id, config_id],
                queue="re"
            ).get()

            if single_result.get('status') == 'completed':
                results.append(single_result.get('result'))
            else:
                errors.append({
                    "ner_id": ner_id,
                    "error": single_result.get('error')
                })

        except Exception as e:
            errors.append({
                "ner_id": ner_id,
                "error": str(e)
            })

    # 更新最终状态
    task_manager.update_task_status(
        task_id,
        status="completed",
        progress=100,
        message=f"批量 RE 完成，成功 {len(results)} 篇，失败 {len(errors)} 篇",
        result={"success_count": len(results), "error_count": len(errors)}
    )

    # WebSocket 推送
    asyncio.run(ws_manager.send_progress(task_id, {
        "event": "re_batch_completed",
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
