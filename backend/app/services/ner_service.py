"""
NER 处理服务 - 异步版本
负责从 PDF 解析结果中提取命名实体
"""
import json
import pickle
import logging
import uuid
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import aiofiles
import pandas as pd
import stanza

from backend.app.core.config import settings, NER_RESULTS_DIR, FAILED_LOGS_DIR, STANZA_RESOURCES_DIR
from backend.app.models.base import get_db_context
from backend.app.models.paper import ProcessingResult
from backend.app.models.ner import NERResult
from backend.app.models.domain import FailedLog
from backend.app.services.pdf_service import load_result_json

logger = logging.getLogger(__name__)

# Stanza 管道（全局懒加载）
_nlp_stanza = None


def get_stanza_pipeline():
    """获取 Stanza 管道（懒加载）"""
    global _nlp_stanza
    if _nlp_stanza is None:
        try:
            _nlp_stanza = stanza.Pipeline(
                lang='en',
                dir=str(STANZA_RESOURCES_DIR) if STANZA_RESOURCES_DIR.exists() else None,
                processors='tokenize',
                download_method=stanza.DownloadMethod.REUSE_RESOURCES,
                use_gpu=False,
                verbose=False
            )
            logger.info(f"Stanza 管道初始化成功")
        except Exception as e:
            logger.error(f"Stanza 管道初始化失败：{e}")
    return _nlp_stanza


async def prepare_sentences_from_pdf(
    result_id: str,
    skip_introduction: bool = True
) -> Tuple[Optional[Dict], List[List]]:
    """
    从 PDF 解析结果准备句子数据（异步版本）

    Returns:
        (parse_result, sentences_data)
        sentences_data 格式：[[doi, section_idx, heading, [sentences]], ...]
    """
    # 获取 Stanza 管道
    nlp_stanza = get_stanza_pipeline()
    if nlp_stanza is None:
        logger.error("Stanza 管道未初始化")
        return None, []

    # 加载 JSON 解析结果
    parse_result = await load_result_json(result_id)
    if parse_result is None:
        logger.error(f"未找到处理结果：{result_id}")
        return None, []

    # 从数据库获取 DOI
    async with get_db_context() as db:
        from sqlalchemy import select
        stmt = select(ProcessingResult).where(ProcessingResult.result_id == result_id)
        result = await db.execute(stmt)
        db_record = result.scalar_one_or_none()

        result_doi = db_record.doi if db_record else None
        result_file_name = db_record.file_name if db_record else None

    # 构建 sections 数据
    sections = []

    # 添加 abstract
    abstract = parse_result.get('abstract', '')
    if abstract and isinstance(abstract, str):
        sections.append(('abstract', abstract.strip()))

    # 添加其他章节
    for sec in parse_result.get('sections', []):
        if isinstance(sec, dict):
            heading = sec.get('heading', '').lower().strip()
            text = sec.get('text', '')

            # 跳过 introduction
            if skip_introduction and heading == 'introduction':
                continue

            if heading and text and isinstance(text, str):
                sections.append((heading, text.strip()))

    if not sections:
        return parse_result, []

    # 构建 rows 数据
    original_doi = result_doi if result_doi else str(result_id)
    rows = [{
        'doi': original_doi,
        'sections': sections
    }]

    # 使用 Stanza 分割句子（同步操作，用 asyncio.to_thread 包装）
    def _split_sentences():
        sentences_data = []
        for row_data in rows:
            doi = row_data['doi']

            for section_idx, (heading, content) in enumerate(row_data['sections'], 1):
                if not isinstance(content, str) or not content.strip():
                    continue

                try:
                    doc = nlp_stanza(content)
                    sentences = [sentence.text for sentence in doc.sentences]
                    sentences_data.append([doi, section_idx, heading, sentences])
                except Exception as e:
                    logger.error(f"DOI {doi} section {heading} 句子分割失败：{e}")

        return sentences_data

    sentences_data = await asyncio.to_thread(_split_sentences)
    logger.info(f"句子分割完成，共 {len(sentences_data)} 个章节")

    return parse_result, sentences_data


def group_sentences(
    sentences_data: List[List],
    group_size: int = 5,
    keep_abstract_intact: bool = True
) -> List[List]:
    """
    将句子按指定数量分组拼接（同步数据处理）

    Returns:
        grouped_data: [[doi, section_idx, group_idx, heading, text], ...]
    """
    grouped_data = []

    for item in sentences_data:
        doi, section_idx, heading, sentences = item

        if not sentences:
            continue

        # abstract 保持完整
        if keep_abstract_intact and heading == 'abstract':
            full_text = ' '.join(sentences)
            grouped_data.append([doi, section_idx, 1, heading, full_text])
            continue

        # 其他章节按 group_size 分组
        for i in range(0, len(sentences), group_size):
            group_sentences = sentences[i:i + group_size]
            paragraph = ' '.join(group_sentences)
            group_idx = i + 1
            grouped_data.append([doi, section_idx, group_idx, heading, paragraph])

    logger.info(f"句子分组完成，共 {len(grouped_data)} 组，每组最多{group_size}句")
    return grouped_data


async def process_ner_with_llm(
    grouped_data: List[List],
    query_file_path: str,
    task_name: str = "NER_task",
    progress_callback: Optional[callable] = None
) -> Dict:
    """
    使用 LLM API 进行 NER 处理（异步版本）

    Args:
        grouped_data: [[doi, section_idx, group_idx, heading, text], ...]
        query_file_path: prompt 模板文件路径
        task_name: 任务名称
        progress_callback: 可选进度回调 async def callback(completed, total, message)

    Returns:
        results: 处理结果
    """
    from backend.app.utils.task_processor import AsyncTaskProcessor
    import uuid as _uuid

    # 构建输入数据
    input_dict = {}
    for item in grouped_data:
        doi, section_idx, group_idx, heading, text = item
        key = (doi, section_idx, group_idx)
        input_dict[key] = {"content": text}

    total = len(input_dict)
    logger.info(f"数据加载完成，共 {total} 条记录")

    # 创建处理器
    unique_task_name = f"{task_name}_{_uuid.uuid4().hex[:8]}"
    processor = AsyncTaskProcessor(
        task_name=unique_task_name,
        max_concurrent=30,
        rate_limit_delay=0.1
    )

    try:
        query_template = processor.load_query(query_file_path)
        if not query_template:
            return {}

        data_list = list(input_dict.items())
        semaphore = asyncio.Semaphore(processor.max_concurrent)
        completed_count = 0
        result_dict = {}
        completed_lock = asyncio.Lock()

        async def _process_one(item):
            nonlocal completed_count
            key, content = item
            input_text = f"content: {content}"

            async with semaphore:
                try:
                    messages, raw_response = await processor.call_api(input_text, query_template, extra_body={"enable_thinking": False})
                    import json5
                    parsed_data = json5.loads(raw_response)
                    result_dict[key] = parsed_data
                except Exception as e:
                    logger.warning(f"NER 处理失败 {key}: {e}")
                    result_dict[key] = []
                finally:
                    async with completed_lock:
                        completed_count += 1
                        if progress_callback:
                            await progress_callback(
                                completed_count, total,
                                f"NER 处理中: {completed_count}/{total}"
                            )
                    await asyncio.sleep(processor.rate_limit_delay)

        # 并行执行
        tasks = [_process_one(item) for item in data_list]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"LLM 处理完成，返回 {len(result_dict)} 条记录")
        return result_dict
    finally:
        await processor.close()


async def save_ner_results(
    ner_id: str,
    result_id: str,
    entities: List[Dict],
    grouped_data: Optional[List[List]] = None
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    保存 NER 结果到文件（异步版本）

    Returns:
        (json_path, excel_path, pkl_path)
    """
    NER_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # JSON 格式
    json_path = NER_RESULTS_DIR / f"{ner_id}.json"
    json_data = {
        'ner_id': ner_id,
        'result_id': result_id,
        'entities': entities,
        'created_at': datetime.now().isoformat()
    }

    async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(json_data, ensure_ascii=False, indent=2))

    excel_path = None
    pkl_path = None

    # Excel 格式
    if entities:
        try:
            df_entities = pd.DataFrame(entities)

            # 清洗数据
            def clean_value(val):
                if isinstance(val, str):
                    val = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', val)
                    val = re.sub(r'[\uf000-\uf8ff]', '', val)
                    val = val.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                    if len(val) > 32000:
                        val = val[:32000]
                return val

            df_entities = df_entities.map(clean_value)

            # 重命名列
            new_columns = {}
            for col in df_entities.columns:
                new_col = re.sub(r'[][:*?/]', '_', str(col))
                new_columns[col] = new_col
            df_entities = df_entities.rename(columns=new_columns)

            excel_path = NER_RESULTS_DIR / f"{ner_id}.xlsx"

            def _save_excel():
                df_entities.to_excel(excel_path, index=False, engine='openpyxl')

            await asyncio.to_thread(_save_excel)
            logger.info(f"NER 结果已保存为 Excel: {excel_path}")
        except Exception as e:
            logger.warning(f"Excel 保存失败：{e}")

    # PKL 格式
    pkl_path = NER_RESULTS_DIR / f"{ner_id}.pkl"
    pkl_data = {
        'ner_id': ner_id,
        'result_id': result_id,
        'entities': entities,
        'grouped_data': grouped_data,
        'created_at': datetime.now().isoformat()
    }

    def _save_pkl():
        with open(pkl_path, 'wb') as f:
            pickle.dump(pkl_data, f)

    await asyncio.to_thread(_save_pkl)
    logger.info(f"NER 结果已保存为 PKL: {pkl_path}")

    return str(json_path), str(excel_path) if excel_path else None, str(pkl_path)


async def save_ner_to_database(
    ner_id: str,
    result_id: str,
    ner_json_path: str,
    ner_excel_path: Optional[str],
    ner_pkl_path: Optional[str],
    entity_count: int,
    user_id: Optional[int] = None,
    status: str = "completed",
    error_message: Optional[str] = None
):
    """将 NER 结果保存到数据库（异步版本）"""
    async with get_db_context() as db:
        from sqlalchemy import select
        stmt = select(NERResult).where(NERResult.ner_id == ner_id)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.result_id = result_id
            existing.ner_json_path = ner_json_path
            existing.ner_excel_path = ner_excel_path
            existing.ner_pkl_path = ner_pkl_path
            existing.entity_count = entity_count
            existing.status = status
            existing.error_message = error_message
            existing.processed_at = datetime.now()
        else:
            ner_record = NERResult(
                ner_id=ner_id,
                result_id=result_id,
                ner_json_path=ner_json_path,
                ner_excel_path=ner_excel_path,
                ner_pkl_path=ner_pkl_path,
                entity_count=entity_count,
                status=status,
                error_message=error_message,
                processed_at=datetime.now(),
                user_id=user_id
            )
            db.add(ner_record)

        await db.flush()
        logger.info(f"NER 数据库记录已保存：{ner_id}")


async def save_ner_failed_log(
    result_id: str,
    error_type: str,
    error_message: str,
    error_stack: Optional[str] = None
):
    """保存 NER 失败日志（异步版本）"""
    import traceback

    log_id = str(uuid.uuid4())
    FAILED_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    log_data = {
        'log_id': log_id,
        'result_id': result_id,
        'error_type': error_type,
        'error_message': error_message,
        'error_stack': error_stack or traceback.format_exc(),
        'created_at': datetime.now().isoformat()
    }

    log_file = FAILED_LOGS_DIR / f"{log_id}.json"
    async with aiofiles.open(log_file, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(log_data, ensure_ascii=False, indent=2))

    logger.error(f"NER 失败日志已保存：{log_file}")


async def process_ner_for_result(
    result_id: str,
    skip_introduction: bool = True,
    sentence_group_size: int = 5,
    query_file_path: Optional[str] = None,
    task_name: str = "NER_task",
    user_id: Optional[int] = None,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    为指定的处理结果执行 NER 处理（异步版本，完整流程）

    Args:
        progress_callback: 可选的进度回调 async def callback(completed, total, message)
    """
    logger.info(f"========== 开始 NER 处理 ========== ")
    logger.info(f"结果 ID: {result_id}")

    try:
        # 步骤 1: 准备句子数据
        logger.info(f"[步骤 1] 正在准备句子数据...")
        parse_result, sentences_data = await prepare_sentences_from_pdf(
            result_id=result_id,
            skip_introduction=skip_introduction
        )

        if parse_result is None:
            logger.error(f"[步骤 1] 未找到处理结果：{result_id}")
            return {'success': False, 'error': f'未找到处理结果：{result_id}'}

        logger.info(f"[步骤 1] 句子准备完成，获取 {len(sentences_data)} 个章节")

        if not sentences_data:
            logger.error(f"[步骤 1] 没有找到有效的章节内容")
            return {'success': False, 'error': '没有找到有效的章节内容'}

        # 步骤 2: 句子分组
        logger.info(f"[步骤 2] 正在进行句子分组...")
        grouped_data = group_sentences(
            sentences_data=sentences_data,
            group_size=sentence_group_size,
            keep_abstract_intact=True
        )
        logger.info(f"[步骤 2] 分组完成，共 {len(grouped_data)} 组")

        if not grouped_data:
            return {'success': False, 'error': '句子分组失败'}

        # 步骤 3: NER 处理
        if query_file_path is None:
            return {'success': False, 'error': '必须提供 query_file_path 参数'}

        logger.info(f"[步骤 3] 开始调用 LLM API 进行 NER 处理...")
        llm_result = await process_ner_with_llm(
            grouped_data=grouped_data,
            query_file_path=query_file_path,
            task_name=task_name,
            progress_callback=progress_callback
        )

        # 解析 LLM 结果
        all_entities = []
        for key, content in llm_result.items():
            doi, section_idx, group_idx = key

            if isinstance(content, list):
                for ent in content:
                    if isinstance(ent, dict):
                        ent['doi'] = doi
                        ent['section_idx'] = section_idx
                        ent['group_idx'] = group_idx
                        all_entities.append(ent)
            elif isinstance(content, dict):
                content['doi'] = doi
                content['section_idx'] = section_idx
                content['group_idx'] = group_idx
                all_entities.append(content)

        logger.info(f"[步骤 3] 实体解析完成，共 {len(all_entities)} 个实体")

        # 步骤 4: 保存结果
        logger.info(f"[步骤 4] 正在保存 NER 结果...")
        ner_id = f"ner_{result_id}"

        ner_json_path, ner_excel_path, ner_pkl_path = await save_ner_results(
            ner_id=ner_id,
            result_id=result_id,
            entities=all_entities,
            grouped_data=grouped_data
        )

        # 步骤 5: 保存到数据库
        logger.info(f"[步骤 5] 正在保存到数据库...")
        await save_ner_to_database(
            ner_id=ner_id,
            result_id=result_id,
            ner_json_path=ner_json_path,
            ner_excel_path=ner_excel_path,
            ner_pkl_path=ner_pkl_path,
            entity_count=len(all_entities),
            user_id=user_id
        )

        logger.info(f"========== NER 处理完成 ========== ")

        return {
            'success': True,
            'ner_id': ner_id,
            'result_id': result_id,
            'entity_count': len(all_entities),
            'group_count': len(grouped_data),
            'ner_json_path': ner_json_path,
            'ner_excel_path': ner_excel_path,
            'ner_pkl_path': ner_pkl_path
        }

    except Exception as e:
        import traceback
        error_stack = traceback.format_exc()
        logger.error(f"========== NER 处理失败 ========== ")
        logger.error(f"错误: {e}")

        await save_ner_failed_log(
            result_id=result_id,
            error_type="ner_error",
            error_message=str(e),
            error_stack=error_stack
        )

        return {'success': False, 'error': str(e)}


async def get_ner_result(ner_id: str) -> Optional[Dict[str, Any]]:
    """获取 NER 结果（异步版本）"""
    async with get_db_context() as db:
        from sqlalchemy import select
        stmt = select(NERResult).where(NERResult.ner_id == ner_id)
        result = await db.execute(stmt)
        db_record = result.scalar_one_or_none()

        if not db_record:
            return None

        return {
            'ner_id': db_record.ner_id,
            'result_id': db_record.result_id,
            'entity_count': db_record.entity_count,
            'status': db_record.status,
            'ner_json_path': db_record.ner_json_path,
            'ner_excel_path': db_record.ner_excel_path,
            'ner_pkl_path': db_record.ner_pkl_path,
            'created_at': db_record.created_at.isoformat() if db_record.created_at else None,
            'processed_at': db_record.processed_at.isoformat() if db_record.processed_at else None
        }


async def load_ner_entities(ner_id: str) -> List[Dict]:
    """加载 NER 实体数据（异步版本）"""
    pkl_path = NER_RESULTS_DIR / f"{ner_id}.pkl"

    if not pkl_path.exists():
        json_path = NER_RESULTS_DIR / f"{ner_id}.json"
        if json_path.exists():
            async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                return data.get('entities', [])
        return []

    def _load_pkl():
        with open(pkl_path, 'rb') as f:
            return pickle.load(f).get('entities', [])

    return await asyncio.to_thread(_load_pkl)


async def load_grouped_data(pkl_path: str) -> List[List]:
    """从 pkl 文件加载分组数据（异步版本）"""
    if not Path(pkl_path).exists():
        return []

    def _load():
        with open(pkl_path, 'rb') as f:
            data = pickle.load(f)
            return data.get('grouped_data', [])

    return await asyncio.to_thread(_load)