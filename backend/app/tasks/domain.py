# -*- coding: utf-8 -*-
"""
领域分析异步任务处理器

将原 Celery 任务 domain_analysis_batch_task 改写为 Redis Stream 处理器声明。
"""
from __future__ import annotations

import uuid
from typing import Any

from loguru import logger
from sqlalchemy import select

from backend.app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure


async def domain_analysis_batch_handler(context: Any) -> dict[str, Any]:
    """批量领域分析任务处理器。

    payload 字段：
      - ner_ids: NER 结果 ID 列表
      - user_id: 用户 ID
      - domain: 领域标识（默认 "rebco"）
      - analysis_types: 分析类型列表（默认 ["tech_route", "exp_scheme", "jc"]）
    """
    payload = context.message.payload
    ner_ids: list[str] = payload["ner_ids"]
    user_id: int = payload["user_id"]
    domain: str = payload.get("domain", "rebco")
    analysis_types: list[str] = payload.get("analysis_types") or [
        "tech_route",
        "exp_scheme",
        "jc",
    ]

    total = len(ner_ids)
    logger.info(f"开始批量领域分析: domain={domain}, 数量={total}")

    from backend.app.domain.registry import DomainRegistry
    from backend.app.models.base import AsyncSessionLocal
    from backend.app.models import NERResult, REResult, TechRoute, ExpScheme

    results: list[dict] = []
    errors: list[dict] = []

    async with AsyncSessionLocal() as db:
        analyzer = DomainRegistry.get(domain)
        if not analyzer:
            raise TaskHandlerFailure(
                f"领域 '{domain}' 未注册",
                error_code="domain_not_registered",
            )

        for idx, ner_id in enumerate(ner_ids):
            try:
                # 获取 NER 结果
                db_result = await db.execute(
                    select(NERResult).where(NERResult.ner_id == ner_id)
                )
                ner_data = db_result.scalar_one_or_none()

                if not ner_data:
                    errors.append({"ner_id": ner_id, "error": "NER 结果不存在"})
                    continue

                entities = ner_data.entities or []
                relations: list = []

                # 获取 RE 结果
                re_db_result = await db.execute(
                    select(REResult).where(REResult.ner_id == ner_id)
                )
                re_data = re_db_result.scalar_one_or_none()
                if re_data:
                    relations = re_data.relations or []

                # 执行分析
                input_data = {
                    "analysis_type": "all",
                    "entities": entities,
                    "relations": relations,
                }
                analysis_result = await analyzer.analyze(input_data)

                # 保存技术路线
                if (
                    "tech_route" in analysis_types
                    and analysis_result.get("tech_route", {}).get("success")
                ):
                    tech_route_text = analysis_result["tech_route"].get("tech_route_text")
                    if tech_route_text:
                        tech_route = TechRoute(
                            profile_id=str(uuid.uuid4()),
                            paper_id=ner_data.result_id,
                            ner_id=ner_id,
                            profile_text=tech_route_text,
                            domain=domain,
                            user_id=user_id,
                        )
                        db.add(tech_route)

                # 保存实验方案
                if (
                    "exp_scheme" in analysis_types
                    and analysis_result.get("exp_scheme", {}).get("success")
                ):
                    exp_scheme_text = analysis_result["exp_scheme"].get("exp_scheme_text")
                    if exp_scheme_text:
                        exp_scheme = ExpScheme(
                            scheme_id=str(uuid.uuid4()),
                            paper_id=ner_data.result_id,
                            ner_id=ner_id,
                            scheme_text=exp_scheme_text,
                            dimensions=analysis_result["exp_scheme"].get("dimensions", {}),
                            domain=domain,
                            user_id=user_id,
                        )
                        db.add(exp_scheme)

                await db.commit()

                results.append({
                    "ner_id": ner_id,
                    "analysis_result": analysis_result,
                })

            except Exception as e:
                logger.error(f"领域分析第 {idx + 1}/{total} 篇失败: {e}")
                errors.append({"ner_id": ner_id, "error": str(e)})

    result = {
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    logger.info(f"批量领域分析完成: 成功={len(results)}, 失败={len(errors)}")
    return result


ASYNC_TASKS: tuple[AsyncTaskDefinition, ...] = (
    AsyncTaskDefinition("scipdf.domain.analysis_batch", domain_analysis_batch_handler),
)
