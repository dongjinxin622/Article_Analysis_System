# -*- coding: utf-8 -*-
"""
批量处理 Celery 任务

批量 PDF 解析、NER、RE 和领域分析任务。
"""

import asyncio
import uuid
import json
from typing import Dict, Any, List
from loguru import logger

from backend.app.tasks import celery_app
from backend.app.core.config import settings
from backend.app.services.task_manager import TaskManager
from backend.app.api.websocket import manager as ws_manager


task_manager = TaskManager()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def full_pipeline_task(
    self,
    file_paths: List[str],
    user_id: int,
    options: Dict = None
) -> Dict[str, Any]:
    """
    完整处理流水线任务

    执行 PDF 解析 -> NER 提取 -> RE 提取 -> 领域分析

    Args:
        self: Celery 任务实例
        file_paths: PDF 文件路径列表
        user_id: 用户 ID
        options: 处理选项

    Returns:
        处理结果
    """
    task_id = self.request.id
    total = len(file_paths)
    options = options or {}

    logger.info(f"开始完整流水线任务: {task_id}, 文件数: {total}")

    # 更新任务状态
    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        stage="init",
        message=f"开始处理，共 {total} 个文件"
    )

    results = []
    errors = []

    try:
        from backend.app.tasks.pdf_tasks import parse_pdf_task
        from backend.app.tasks.ner_tasks import ner_extraction_task
        from backend.app.tasks.re_tasks import re_extraction_task

        for idx, file_path in enumerate(file_paths):
            base_progress = int((idx / total) * 100)

            try:
                # 步骤 1: PDF 解析 (0-30%)
                task_manager.update_task_status(
                    task_id,
                    progress=base_progress,
                    stage="pdf",
                    message=f"解析 PDF {idx + 1}/{total}"
                )

                pdf_result = parse_pdf_task.apply_async(
                    args=[file_path, user_id, options.get('pdf_options')],
                    queue="pdf"
                ).get(timeout=600)

                if pdf_result.get('status') != 'completed':
                    errors.append({
                        "file": file_path,
                        "stage": "pdf",
                        "error": pdf_result.get('error')
                    })
                    continue

                result_id = pdf_result.get('result', {}).get('result_id')

                # 步骤 2: NER 提取 (30-60%)
                task_manager.update_task_status(
                    task_id,
                    progress=base_progress + 30,
                    stage="ner",
                    message=f"NER 提取 {idx + 1}/{total}"
                )

                ner_result = ner_extraction_task.apply_async(
                    args=[result_id, user_id, options.get('config_id'), options.get('domain')],
                    queue="ner"
                ).get(timeout=600)

                if ner_result.get('status') != 'completed':
                    errors.append({
                        "file": file_path,
                        "stage": "ner",
                        "error": ner_result.get('error')
                    })
                    continue

                ner_id = ner_result.get('result', {}).get('ner_id')

                # 步骤 3: RE 提取 (60-80%)
                if options.get('do_re', True):
                    task_manager.update_task_status(
                        task_id,
                        progress=base_progress + 60,
                        stage="re",
                        message=f"RE 提取 {idx + 1}/{total}"
                    )

                    re_result = re_extraction_task.apply_async(
                        args=[ner_id, user_id, options.get('config_id'), options.get('domain')],
                        queue="re"
                    ).get(timeout=600)

                    re_id = re_result.get('result', {}).get('re_id') if re_result.get('status') == 'completed' else None
                else:
                    re_id = None

                # 收集结果
                results.append({
                    "file": file_path,
                    "result_id": result_id,
                    "ner_id": ner_id,
                    "re_id": re_id
                })

            except Exception as e:
                errors.append({
                    "file": file_path,
                    "error": str(e)
                })
                logger.error(f"处理文件失败: {file_path}, {e}")

        # 步骤 4: 领域分析 (80-100%) - 可选
        if options.get('do_domain_analysis') and results:
            task_manager.update_task_status(
                task_id,
                progress=80,
                stage="domain",
                message="执行领域分析"
            )

            # 可以在此添加领域分析逻辑

        # 更新最终状态
        task_manager.update_task_status(
            task_id,
            status="completed",
            progress=100,
            stage="completed",
            message=f"处理完成，成功 {len(results)} 篇，失败 {len(errors)} 篇",
            result={
                "success_count": len(results),
                "error_count": len(errors),
                "results": results
            }
        )

        # WebSocket 推送
        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "pipeline_completed",
            "data": {
                "task_id": task_id,
                "status": "completed",
                "success_count": len(results),
                "error_count": len(errors)
            }
        }))

        logger.info(f"完整流水线任务完成: {task_id}")
        return {
            "status": "completed",
            "success_count": len(results),
            "error_count": len(errors),
            "results": results,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"完整流水线任务失败: {task_id}, {e}")

        task_manager.update_task_status(
            task_id,
            status="failed",
            message=f"任务失败: {str(e)}",
            error=str(e)
        )

        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "pipeline_failed",
            "data": {
                "task_id": task_id,
                "status": "failed",
                "error": str(e)
            }
        }))

        return {"status": "failed", "error": str(e)}


@celery_app.task(bind=True, max_retries=2)
def domain_analysis_batch_task(
    self,
    ner_ids: List[str],
    user_id: int,
    domain: str = "rebco",
    analysis_types: List[str] = None
) -> Dict[str, Any]:
    """
    批量领域分析任务

    Args:
        self: Celery 任务实例
        ner_ids: NER 结果 ID 列表
        user_id: 用户 ID
        domain: 领域标识
        analysis_types: 分析类型列表（tech_route, exp_scheme, jc）

    Returns:
        领域分析结果
    """
    task_id = self.request.id
    total = len(ner_ids)
    analysis_types = analysis_types or ['tech_route', 'exp_scheme', 'jc']

    logger.info(f"开始批量领域分析任务: {task_id}, 领域: {domain}, 数量: {total}")

    task_manager.update_task_status(
        task_id,
        status="processing",
        progress=0,
        message=f"开始领域分析，共 {total} 篇"
    )

    results = []
    errors = []

    try:
        from backend.app.domain.registry import DomainRegistry
        from backend.app.models.base import AsyncSessionLocal
        from backend.app.models import NERResult, REResult, TechRoute, ExpScheme
        from sqlalchemy import select

        async def _analyze():
            async with AsyncSessionLocal() as db:
                analyzer = DomainRegistry.get(domain)

                if not analyzer:
                    raise ValueError(f"领域 '{domain}' 未注册")

                for idx, ner_id in enumerate(ner_ids):
                    progress = int((idx / total) * 100)

                    task_manager.update_task_status(
                        task_id,
                        progress=progress,
                        message=f"分析第 {idx + 1}/{total} 篇"
                    )

                    # 获取 NER 结果
                    db_result = await db.execute(
                        select(NERResult).where(NERResult.ner_id == ner_id)
                    )
                    ner_data = db_result.scalar_one_or_none()

                    if not ner_data:
                        errors.append({"ner_id": ner_id, "error": "NER 结果不存在"})
                        continue

                    entities = ner_data.entities or []
                    relations = []

                    # 获取 RE 结果
                    re_db_result = await db.execute(
                        select(REResult).where(REResult.ner_id == ner_id)
                    )
                    re_data = re_db_result.scalar_one_or_none()
                    if re_data:
                        relations = re_data.relations or []

                    # 执行分析
                    input_data = {
                        'analysis_type': 'all',
                        'entities': entities,
                        'relations': relations
                    }

                    analysis_result = await analyzer.analyze(input_data)

                    # 保存结果
                    if 'tech_route' in analysis_types and analysis_result.get('tech_route', {}).get('success'):
                        tech_route_text = analysis_result['tech_route'].get('tech_route_text')
                        if tech_route_text:
                            tech_route = TechRoute(
                                profile_id=str(uuid.uuid4()),
                                paper_id=ner_data.result_id,
                                ner_id=ner_id,
                                profile_text=tech_route_text,
                                domain=domain,
                                user_id=user_id
                            )
                            db.add(tech_route)

                    if 'exp_scheme' in analysis_types and analysis_result.get('exp_scheme', {}).get('success'):
                        exp_scheme_text = analysis_result['exp_scheme'].get('exp_scheme_text')
                        if exp_scheme_text:
                            exp_scheme = ExpScheme(
                                scheme_id=str(uuid.uuid4()),
                                paper_id=ner_data.result_id,
                                ner_id=ner_id,
                                scheme_text=exp_scheme_text,
                                dimensions=analysis_result['exp_scheme'].get('dimensions', {}),
                                domain=domain,
                                user_id=user_id
                            )
                            db.add(exp_scheme)

                    await db.commit()

                    results.append({
                        "ner_id": ner_id,
                        "analysis_result": analysis_result
                    })

                return results

        final_results = asyncio.run(_analyze())

        task_manager.update_task_status(
            task_id,
            status="completed",
            progress=100,
            message=f"领域分析完成，成功 {len(results)} 篇，失败 {len(errors)} 篇",
            result={"success_count": len(results), "error_count": len(errors)}
        )

        asyncio.run(ws_manager.send_progress(task_id, {
            "event": "domain_analysis_completed",
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
            "results": final_results,
            "errors": errors
        }

    except Exception as e:
        logger.error(f"批量领域分析任务失败: {task_id}, {e}")

        task_manager.update_task_status(
            task_id,
            status="failed",
            message=f"任务失败: {str(e)}",
            error=str(e)
        )

        return {"status": "failed", "error": str(e)}