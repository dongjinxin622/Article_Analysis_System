# -*- coding: utf-8 -*-
"""
NER 异步任务处理器

将原 Celery 任务 ner_extraction_task 和 ner_batch_task 改写为 Redis Stream 处理器声明。
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Any

from loguru import logger
from sqlalchemy import select

from backend.app.core.config import NER_RESULTS_DIR
from backend.app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure


def _load_parsed_content(paper) -> tuple[str, list]:
    """从 ProcessingResult 的 JSON 文件中加载解析内容。"""
    content = ""
    sections: list = []
    if paper.result_json_path and os.path.exists(paper.result_json_path):
        try:
            with open(paper.result_json_path, "r", encoding="utf-8") as f:
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
    if not content:
        content = paper.abstract or ""
    return content, sections


async def ner_extraction_handler(context: Any) -> dict[str, Any]:
    """NER 提取任务处理器。

    payload 字段：
      - result_id: PDF 处理结果 ID
      - user_id: 用户 ID
      - config_id: Prompt 配置 ID（可选）
      - domain: 领域标识（可选）
    """
    payload = context.message.payload
    result_id: str = payload["result_id"]
    user_id: int = payload["user_id"]
    config_id: int | None = payload.get("config_id")
    domain: str | None = payload.get("domain")

    logger.info(f"开始 NER 提取: result_id={result_id}")

    from backend.app.services.ner_service import NERService
    from backend.app.models.base import AsyncSessionLocal
    from backend.app.models import ProcessingResult, NERResult

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

        content, sections = _load_parsed_content(paper)

        ner_service = NERService()
        ner_result = await ner_service.extract_entities(
            content=content,
            sections=sections,
            config_id=config_id,
            domain=domain,
        )

        ner_id = str(uuid.uuid4())

        db_ner = NERResult(
            ner_id=ner_id,
            result_id=result_id,
            entity_count=len(ner_result.get("entities", [])),
            entity_types=ner_result.get("entity_types"),
            status="completed",
            user_id=user_id,
        )
        db.add(db_ner)
        await db.commit()

    # 保存结果文件
    ner_file = NER_RESULTS_DIR / f"{ner_id}.json"
    ner_file.parent.mkdir(parents=True, exist_ok=True)
    with open(ner_file, "w", encoding="utf-8") as f:
        json.dump(ner_result, f, ensure_ascii=False, indent=2)

    result = {
        "ner_id": ner_id,
        "result_id": result_id,
        "entity_count": len(ner_result.get("entities", [])),
        "entities": ner_result.get("entities", []),
    }
    logger.info(f"NER 提取完成: ner_id={ner_id}, entities={result['entity_count']}")
    return result


async def ner_batch_handler(context: Any) -> dict[str, Any]:
    """批量 NER 提取任务处理器。

    payload 字段：
      - result_ids: PDF 处理结果 ID 列表
      - user_id: 用户 ID
      - config_id: Prompt 配置 ID（可选）
    """
    payload = context.message.payload
    result_ids: list[str] = payload["result_ids"]
    user_id: int = payload["user_id"]
    config_id: int | None = payload.get("config_id")

    total = len(result_ids)
    logger.info(f"开始批量 NER: 数量={total}")

    results: list[dict] = []
    errors: list[dict] = []

    for idx, result_id in enumerate(result_ids):
        try:
            single_result = await ner_extraction_handler(
                _make_inline_context(payload={
                    "result_id": result_id,
                    "user_id": user_id,
                    "config_id": config_id,
                })
            )
            results.append(single_result)
        except Exception as e:
            logger.error(f"批量 NER 第 {idx + 1}/{total} 篇失败: {e}")
            errors.append({"result_id": result_id, "error": str(e)})

    result = {
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    logger.info(f"批量 NER 完成: 成功={len(results)}, 失败={len(errors)}")
    return result


def _make_inline_context(payload: dict) -> Any:
    """构造内联上下文，供批量处理器复用单个处理器逻辑。"""
    from backend.app.schemas.tasks import TaskStreamMessage
    from datetime import datetime, timezone

    class _InlineMessage:
        def __init__(self, p: dict) -> None:
            self.payload = p

    class _InlineContext:
        def __init__(self, p: dict) -> None:
            self.message = _InlineMessage(p)

    return _InlineContext(payload)


ASYNC_TASKS: tuple[AsyncTaskDefinition, ...] = (
    AsyncTaskDefinition("scipdf.ner.extract", ner_extraction_handler),
    AsyncTaskDefinition("scipdf.ner.batch", ner_batch_handler),
)
