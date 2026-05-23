"""
NER+RE 流水线处理服务
每个片段: NER → 立即RE，所有片段并行执行
无需等待全部NER完成即可开始RE
"""
import json
import pickle
import asyncio
import uuid
import re
import json5
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from loguru import logger

from backend.app.core.config import settings, NER_RESULTS_DIR, RE_RESULTS_DIR
from backend.app.models.base import get_db_context
from backend.app.models.ner import NERResult
from backend.app.models.re import REResult
from backend.app.services.ner_service import (
    prepare_sentences_from_pdf,
    group_sentences,
    save_ner_results,
    save_ner_to_database
)
from backend.app.services.re_service import (
    save_re_results as _save_re_results,
)
from backend.app.utils.task_processor import AsyncTaskProcessor


async def process_ner_re_pipeline(
    result_id: str,
    ner_query_file: str,
    re_query_file: str,
    skip_introduction: bool = True,
    sentence_group_size: int = 5,
    task_name: str = "NER_RE_pipeline",
    user_id: Optional[int] = None,
    progress_callback: Optional[callable] = None,
    ner_timeout: int = 300,  # NER 单阶段超时时间（秒）
    re_timeout: int = 300,   # RE 单阶段超时时间（秒）
    max_concurrent: int = 15  # 并发数
) -> Dict[str, Any]:
    """
    NER+RE 流水线处理：每个片段 NER→RE 串行，所有片段并行

    Args:
        result_id: PDF解析结果ID
        ner_query_file: NER Prompt文件路径
        re_query_file: RE Prompt文件路径
        progress_callback: async def callback(stage, completed, total, message)
                          stage="ner"|"re", completed和total是该阶段的计数

    Returns:
        {
            success, ner_id, re_id, entity_count, relation_count,
            ner_json_path, re_json_path, ...
        }
    """
    logger.info("=" * 60)
    logger.info("开始 NER+RE 流水线处理")
    logger.info(f"result_id={result_id}")
    logger.info("=" * 60)

    try:
        # Step 1: 准备句子数据
        logger.info("[流水线] 准备句子数据...")
        parse_result, sentences_data = await prepare_sentences_from_pdf(
            result_id=result_id,
            skip_introduction=skip_introduction
        )

        if parse_result is None:
            return {'success': False, 'error': f'未找到处理结果：{result_id}'}

        if not sentences_data:
            return {'success': False, 'error': '没有找到有效的章节内容'}

        logger.info(f"[流水线] 句子准备完成，{len(sentences_data)} 个章节")

        # Step 2: 句子分组
        grouped_data = group_sentences(
            sentences_data=sentences_data,
            group_size=sentence_group_size,
            keep_abstract_intact=True
        )
        logger.info(f"[流水线] 分组完成，共 {len(grouped_data)} 组")

        if not grouped_data:
            return {'success': False, 'error': '句子分组失败'}

        # Step 3: 构建 grouped_data 索引（用于后续RE）
        content_dict = {}
        for item in grouped_data:
            if len(item) >= 5:
                doi, section_idx, group_idx, heading, text = item
                key = (doi, section_idx, group_idx)
                content_dict[key] = text

        # Step 4: 准备NER输入数据
        ner_input_dict = {}
        for item in grouped_data:
            doi, section_idx, group_idx, heading, text = item
            key = (doi, section_idx, group_idx)
            ner_input_dict[key] = {"content": text}

        total_chunks = len(ner_input_dict)
        logger.info(f"[流水线] 共 {total_chunks} 个数据块，开始并行 NER→RE 流水线")

        # Step 5: 创建处理器并使用总并发控制
        unique_task_name = f"{task_name}_{uuid.uuid4().hex[:8]}"

        # 使用总并发 semaphore 控制 NER+RE 总并发数
        total_semaphore = asyncio.Semaphore(max_concurrent)

        ner_processor = AsyncTaskProcessor(
            task_name=f"{unique_task_name}_ner",
            max_concurrent=max_concurrent,
            rate_limit_delay=0.3,
            request_timeout=120,
            max_retries=2,
            retry_delay=10,
            model=settings.MODEL_NAME
        )
        re_processor = AsyncTaskProcessor(
            task_name=f"{unique_task_name}_re",
            max_concurrent=max_concurrent,
            rate_limit_delay=0.3,
            request_timeout=120,
            max_retries=2,
            retry_delay=10,
            model=settings.MODEL_NAME
        )

        try:
            ner_query_template = ner_processor.load_query(ner_query_file)
            re_query_template = re_processor.load_query(re_query_file)

            if not ner_query_template:
                return {'success': False, 'error': 'NER Prompt 文件加载失败'}
            if not re_query_template:
                return {'success': False, 'error': 'RE Prompt 文件加载失败'}

            # 收集结果
            all_entities = []
            all_relations = []
            ner_count = 0  # NER 完成计数
            re_count = 0   # RE 完成计数
            lock = asyncio.Lock()

            async def process_single_chunk(key, content_text):
                """处理单个数据块: NER → 立即 RE"""
                nonlocal ner_count, re_count
                # 使用总并发 semaphore 控制
                async with total_semaphore:
                    try:
                        await _process_chunk_internal(key, content_text)
                    except Exception as e:
                        logger.error(f"[流水线] 块 {key} 处理异常: {e}")
                        async with lock:
                            ner_count += 1
                            re_count += 1
                            if progress_callback:
                                await progress_callback("ner", ner_count, total_chunks, f"NER异常: {ner_count}/{total_chunks}")
                                await progress_callback("re", re_count, total_chunks, f"RE异常: {re_count}/{total_chunks}")

            async def _process_chunk_internal(key, content_text):
                """内部处理逻辑，NER和RE各自独立超时"""
                nonlocal ner_count, re_count, all_entities, all_relations
                # 1. NER（独立超时）
                ner_input = f"content: {content_text}"
                ner_parsed = []
                try:
                    # NER 独立超时控制，关闭思考模式
                    _, ner_raw = await asyncio.wait_for(
                        ner_processor.call_api(ner_input, ner_query_template, extra_body={"enable_thinking": False}),
                        timeout=ner_timeout
                    )
                    logger.debug(f"[流水线] NER 原始响应 {key}: {ner_raw[:200] if ner_raw else 'empty'}...")

                    # 尝试解析
                    ner_parsed = json5.loads(ner_raw)
                    logger.info(f"[流水线] NER 解析成功 {key}: {len(ner_parsed) if isinstance(ner_parsed, list) else 1} 个实体")
                except asyncio.TimeoutError:
                    logger.error(f"[流水线] NER 超时 {key} ({ner_timeout}s)")
                    ner_parsed = []
                except json.JSONDecodeError as e:
                    logger.warning(f"[流水线] NER JSON解析失败 {key}: {e}, raw={ner_raw[:100] if ner_raw else 'empty'}")
                    ner_parsed = []
                except Exception as e:
                    logger.warning(f"[流水线] NER 失败 {key}: {e}")
                    ner_parsed = []

                # 提取实体
                chunk_entities = []
                if isinstance(ner_parsed, list):
                    for ent in ner_parsed:
                        if isinstance(ent, dict):
                            ent['doi'] = key[0]
                            ent['section_idx'] = key[1]
                            ent['group_idx'] = key[2]
                            chunk_entities.append(ent)
                elif isinstance(ner_parsed, dict):
                    ner_parsed['doi'] = key[0]
                    ner_parsed['section_idx'] = key[1]
                    ner_parsed['group_idx'] = key[2]
                    chunk_entities.append(ner_parsed)

                # 报告 NER 进度（独立计数）
                async with lock:
                    ner_count += 1
                    if progress_callback:
                        await progress_callback("ner", ner_count, total_chunks,
                                               f"NER: {ner_count}/{total_chunks}")

                # 2. 如果有实体，立即执行 RE（独立超时）
                chunk_relations = []
                if chunk_entities:
                    # 准备 RE 输入
                    entities_for_re = []
                    for ent in chunk_entities:
                        ent_copy = {k: v for k, v in ent.items()
                                   if k not in ['doi', 'section_idx', 'group_idx']}
                        entities_for_re.append(ent_copy)

                    entities_json = json.dumps(entities_for_re, ensure_ascii=False, indent=2)
                    sentences_json = json.dumps([content_text], ensure_ascii=False, indent=2)
                    re_input = f"实体列表:\n{entities_json}\n\n文本句子:\n{sentences_json}"

                    try:
                        # RE 独立超时控制，关闭思考模式
                        _, re_raw = await asyncio.wait_for(
                            re_processor.call_api(re_input, re_query_template, extra_body={"enable_thinking": False}),
                            timeout=re_timeout
                        )
                        re_parsed = json5.loads(re_raw)

                        # 解析 RE 结果
                        if isinstance(re_parsed, list):
                            for rel in re_parsed:
                                if isinstance(rel, dict):
                                    rel['doi'] = key[0]
                                    rel['section'] = key[1]
                                    rel['part'] = key[2]
                                    chunk_relations.append(rel)
                        elif isinstance(re_parsed, dict):
                            if 'relations' in re_parsed:
                                for rel in re_parsed['relations']:
                                    if isinstance(rel, dict):
                                        rel['doi'] = key[0]
                                        rel['section'] = key[1]
                                        rel['part'] = key[2]
                                        chunk_relations.append(rel)
                            else:
                                re_parsed['doi'] = key[0]
                                re_parsed['section'] = key[1]
                                re_parsed['part'] = key[2]
                                chunk_relations.append(re_parsed)
                    except asyncio.TimeoutError:
                        logger.error(f"[流水线] RE 超时 {key} ({re_timeout}s)")
                    except Exception as e:
                        logger.warning(f"[流水线] RE 失败 {key}: {e}")

                    # 报告 RE 进度（独立计数）
                    async with lock:
                        re_count += 1
                        if progress_callback:
                            await progress_callback("re", re_count, total_chunks,
                                                   f"RE: {re_count}/{total_chunks}")

                # 汇总结果
                async with lock:
                    all_entities.extend(chunk_entities)
                    all_relations.extend(chunk_relations)
                    logger.info(f"[流水线] 块 {key[1]}-{key[2]} 完成: {len(chunk_entities)}实体, {len(chunk_relations)}关系")

                await asyncio.sleep(0.1)

            # 并行执行所有块
            tasks = [
                process_single_chunk(key, item["content"])
                for key, item in ner_input_dict.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 检查是否有异常被返回
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    keys_list = list(ner_input_dict.keys())
                    logger.error(f"[流水线] 任务 {keys_list[i]} 失败: {result}")
                    import traceback
                    logger.error(traceback.format_exception(type(result), result, result.__traceback__))

        finally:
            await ner_processor.close()
            await re_processor.close()

        logger.info(f"[流水线] 处理完成: {len(all_entities)} 实体, {len(all_relations)} 关系")

        # Step 6: 保存 NER 结果
        ner_id = f"ner_{result_id}"
        ner_json_path, ner_excel_path, ner_pkl_path = await save_ner_results(
            ner_id=ner_id,
            result_id=result_id,
            entities=all_entities,
            grouped_data=grouped_data
        )

        await save_ner_to_database(
            ner_id=ner_id,
            result_id=result_id,
            ner_json_path=ner_json_path,
            ner_excel_path=ner_excel_path,
            ner_pkl_path=ner_pkl_path,
            entity_count=len(all_entities),
            user_id=user_id
        )

        logger.info(f"[流水线] NER 结果已保存: {ner_json_path}")

        # Step 7: 保存 RE 结果
        re_id = f"re_{ner_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        re_json_path, re_excel_path, re_pkl_path = await _save_re_results(
            re_id=re_id,
            result_id=result_id,
            ner_id=ner_id,
            relations=all_relations
        )

        # 保存 RE 到数据库
        async with get_db_context() as db:
            from sqlalchemy import select
            stmt = select(REResult).where(REResult.ner_id == ner_id)
            result = await db.execute(stmt)
            existing_re = result.scalar_one_or_none()

            if existing_re:
                existing_re.re_json_path = str(re_json_path)
                existing_re.re_excel_path = str(re_excel_path) if re_excel_path else None
                existing_re.re_pkl_path = str(re_pkl_path) if re_pkl_path else None
                existing_re.relation_count = len(all_relations)
                existing_re.status = 'completed'
                existing_re.processed_at = datetime.now()
            else:
                new_re = REResult(
                    re_id=re_id,
                    result_id=result_id,
                    ner_id=ner_id,
                    re_json_path=str(re_json_path),
                    re_excel_path=str(re_excel_path) if re_excel_path else None,
                    re_pkl_path=str(re_pkl_path) if re_pkl_path else None,
                    relation_count=len(all_relations),
                    status='completed',
                    processed_at=datetime.now(),
                    user_id=user_id
                )
                db.add(new_re)
            await db.flush()

        logger.info(f"[流水线] RE 结果已保存: {re_json_path}")
        logger.info("=" * 60)
        logger.info("NER+RE 流水线处理完成")
        logger.info("=" * 60)

        return {
            'success': True,
            'ner_id': ner_id,
            're_id': re_id,
            'result_id': result_id,
            'entity_count': len(all_entities),
            'relation_count': len(all_relations),
            'ner_json_path': ner_json_path,
            'ner_excel_path': ner_excel_path,
            'ner_pkl_path': ner_pkl_path,
            're_json_path': re_json_path,
            're_excel_path': re_excel_path,
            're_pkl_path': re_pkl_path
        }

    except Exception as e:
        import traceback
        logger.error(f"[流水线] 处理失败: {e}")
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e)}
