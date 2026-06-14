# -*- coding: utf-8 -*-
"""
完整流水线异步任务处理器

将原 Celery 任务 full_pipeline_task 改写为 Redis Stream 处理器声明。
执行流程：PDF 解析 → NER 提取 → RE 提取（可选）→ 领域分析（可选）。
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from backend.app.core.tasks.engine import AsyncTaskDefinition, TaskHandlerFailure


async def full_pipeline_handler(context: Any) -> dict[str, Any]:
    """完整处理流水线任务处理器。

    payload 字段：
      - file_paths: PDF 文件路径列表
      - user_id: 用户 ID
      - options: 处理选项（可选），支持：
          - pdf_options: PDF 解析选项
          - config_id: Prompt 配置 ID
          - domain: 领域标识
          - do_re: 是否执行 RE（默认 True）
          - do_domain_analysis: 是否执行领域分析（默认 False）
    """
    payload = context.message.payload
    file_paths: list[str] = payload["file_paths"]
    user_id: int = payload["user_id"]
    options: dict = payload.get("options") or {}

    total = len(file_paths)
    logger.info(f"开始完整流水线: 文件数={total}")

    from backend.app.tasks.pdf import parse_pdf_handler
    from backend.app.tasks.ner import ner_extraction_handler
    from backend.app.tasks.re import re_extraction_handler
    from backend.app.tasks.ner import _make_inline_context

    results: list[dict] = []
    errors: list[dict] = []

    for idx, file_path in enumerate(file_paths):
        try:
            # 步骤 1: PDF 解析
            logger.info(f"流水线 PDF 解析 {idx + 1}/{total}: {file_path}")
            pdf_result = await parse_pdf_handler(
                _make_inline_context(payload={
                    "file_path": file_path,
                    "user_id": user_id,
                })
            )
            result_id = pdf_result.get("result_id")

            # 步骤 2: NER 提取
            logger.info(f"流水线 NER 提取 {idx + 1}/{total}: result_id={result_id}")
            ner_result = await ner_extraction_handler(
                _make_inline_context(payload={
                    "result_id": result_id,
                    "user_id": user_id,
                    "config_id": options.get("config_id"),
                    "domain": options.get("domain"),
                })
            )
            ner_id = ner_result.get("ner_id")

            # 步骤 3: RE 提取（可选）
            re_id = None
            if options.get("do_re", True):
                logger.info(f"流水线 RE 提取 {idx + 1}/{total}: ner_id={ner_id}")
                try:
                    re_result = await re_extraction_handler(
                        _make_inline_context(payload={
                            "ner_id": ner_id,
                            "user_id": user_id,
                            "config_id": options.get("config_id"),
                            "domain": options.get("domain"),
                        })
                    )
                    re_id = re_result.get("re_id")
                except Exception as e:
                    logger.warning(f"流水线 RE 提取失败（非致命）: {e}")

            results.append({
                "file": file_path,
                "result_id": result_id,
                "ner_id": ner_id,
                "re_id": re_id,
            })

        except Exception as e:
            logger.error(f"流水线处理文件失败: {file_path}, {e}")
            errors.append({"file": file_path, "error": str(e)})

    result = {
        "success_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }
    logger.info(f"完整流水线完成: 成功={len(results)}, 失败={len(errors)}")
    return result


ASYNC_TASKS: tuple[AsyncTaskDefinition, ...] = (
    AsyncTaskDefinition("scipdf.pipeline.full", full_pipeline_handler),
)
