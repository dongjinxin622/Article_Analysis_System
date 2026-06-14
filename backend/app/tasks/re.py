# -*- coding: utf-8 -*-
"""
RE（关系抽取）异步任务处理器

将原 Celery 任务 re_extraction_task 和 re_batch_task 改写为 Redis Stream 处理器声明。
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.core.config import RE_RESULTS_DIR
from backend.app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure


def _load_ner_content(ner_data) -> str:
    """从 NER 结果关联的 ProcessingResult JSON 文件中加载文本内容。"""
    content = ""
    if ner_data.processing_result and ner_data.processing_result.result_json_path:
        json_path = ner_data.processing_result.result_json_path
        if os.path.exists(json_path):
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    parsed_data = json.load(f)
                sections = parsed_data.get("sections", [])
                content_parts = []
                for sec in sections:
                    if isinstance(sec, dict):
                        text = sec.get("text", "")
                        if text:
                            content_parts.append(text)
                content = "\n\n".join(content_parts)
            except Exception as e:
                logger.warning(f"加载解析结果 JSON 失败: {e}")
    if not content and ner_data.processing_result:
        content = ner_data.processing_result.abstract or ""
    return content


async def re_extraction_handler(context: Any) -> dict[str, Any]:
    """关系抽取任务处理器。

    payload 字段：
      - ner_id: NER 结果 ID
      - user_id: 用户 ID
      - config_id: Prompt 配置 ID（可选）
      - domain: 领域标识（可选）
    """
    payload = context.message.payload
    ner_id: str = payload["ner_id"]
    user_id: int = payload["user_id"]
    config_id: int | None = payload.get("config_id")
    domain: str | None = payload.get("domain")

    logger.info(f"开始 RE 提取: ner_id={ner_id}")

    from backend.app.services.re_service import REService
    from backend.app.models.base import AsyncSessionLocal
    from backend.app.models import NERResult, REResult

    async with AsyncSessionLocal() as db:
        db_result = await db.execute(
            select(NERResult)
            .where(NERResult.ner_id == ner_id)
            .options(selectinload(NERResult.processing_result))
        )
        ner_data = db_result.scalar_one_or_none()

        if not ner_data:
            raise TaskHandlerFailure(
                f"NER 结果不存在: {ner_id}",
                error_code="ner_result_not_found",
            )

        entities = ner_data.entities if hasattr(ner_data, "entities") else []
        content = _load_ner_content(ner_data)

        re_service = REService()
        re_result = await re_service.extract_relations(
            entities=entities,
            content=content,
            config_id=config_id,
            domain=domain,
        )

        re_id = str(uuid.uuid4())

        db_re = REResult(
            re_id=re_id,
            ner_id=ner_id,
            result_id=ner_data.result_id,
            relation_count=len(re_result.get("relations", [])),
            relation_types=re_result.get("relation_types"),
            status="completed",
            user_id=user_id,
        )
        db.add(db_re)
        await db.commit()

    # 保存结果文件
    re_file = RE_RESULTS_DIR / f"{re_id}.json"
    re_file.parent.mkdir(parents=True, exist_ok=True)
    with open(re_file, "w", encoding="utf-8") as f:
        json.dump(re_result, f, ensure_ascii=False, indent=2)

    result = {
        "re_id": re_id,
        "ner_id": ner_id,
        "relation_count": len(re_result.get("relations", [])),
        "relations": re_result.get("relations", []),
    }
    logger.info(f"RE 提取完成: re_id={re_id}, relations={result['relation_count']}")
    return result


async def re_batch_handler(context: Any) -> dict[str, Any]:
    """批量关系抽取任务处理器。

    payload 字段：
      - ner_ids: NER 结果 ID 列表
      - user_id: 用户 ID
      - config_id: Prompt 配置 ID（可选）
    """
    payload = context.message.payload
    ner_ids: list[str] = payload["ner_ids"]
    user_id: int = payload["user_id"]
    config_id: int | None = payload.get("config_id")

    total = len(ner_ids)
    logger.info(f"开始批量 RE: 数量={total}")

    results: list[dict] = []
    errors: list[dict] = []

    for idx, ner_id in enumerate(ner_ids):
        try:
            single_result = await re_extraction_handler(
                _make_inline_context(payload={
                    "ner_id": ner_id,
                    "user_id": user_id,
                    "config_id": config_id,
                })
            )
            results.append(single_result)
        except Exception as e:
            logger.error(f"批量 RE 第 {idx + 1}/{total} 篇失败: {e}")
            errors.append({"ner_id": ner_id, "error": str(e)})

    result = {
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    logger.info(f"批量 RE 完成: 成功={len(results)}, 失败={len(errors)}")
    return result


def _make_inline_context(payload: dict) -> Any:
    """构造内联上下文，供批量处理器复用单个处理器逻辑。"""

    class _InlineMessage:
        def __init__(self, p: dict) -> None:
            self.payload = p

    class _InlineContext:
        def __init__(self, p: dict) -> None:
            self.message = _InlineMessage(p)

    return _InlineContext(payload)


ASYNC_TASKS: tuple[AsyncTaskDefinition, ...] = (
    AsyncTaskDefinition("scipdf.re.extract", re_extraction_handler),
    AsyncTaskDefinition("scipdf.re.batch", re_batch_handler),
)
