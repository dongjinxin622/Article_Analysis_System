"""
关系抽取 (RE) 服务 - 异步版本
负责从 NER 结果中提取实体之间的关系
"""
import json
import pickle
import logging
import asyncio
import re
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple

import aiofiles
import pandas as pd

from backend.app.core.config import settings, RE_RESULTS_DIR, NER_RESULTS_DIR
from backend.app.models.base import get_db_context
from backend.app.models.re import REResult
from backend.app.models.ner import NERResult
from backend.app.services.ner_service import load_grouped_data

logger = logging.getLogger(__name__)


async def save_re_results(
    re_id: str,
    result_id: str,
    ner_id: str,
    relations: List[Dict]
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    保存 RE 结果到文件（异步版本）

    Returns:
        (json_path, excel_path, pkl_path)
    """
    RE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # JSON 格式
    json_path = RE_RESULTS_DIR / f"{re_id}.json"
    json_data = {
        're_id': re_id,
        'result_id': result_id,
        'ner_id': ner_id,
        'relations': relations,
        'relation_count': len(relations),
        'created_at': datetime.now().isoformat()
    }

    async with aiofiles.open(json_path, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(json_data, ensure_ascii=False, indent=2))

    excel_path = None
    pkl_path = None

    # Excel 格式
    if relations:
        try:
            df_relations = pd.DataFrame(relations)

            # 清洗数据
            def clean_value(val):
                if isinstance(val, str):
                    val = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', val)
                    val = re.sub(r'[\uf000-\uf8ff]', '', val)
                    val = val.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ')
                    if len(val) > 32000:
                        val = val[:32000]
                return val

            df_relations = df_relations.map(clean_value)

            # 重命名列
            new_columns = {}
            for col in df_relations.columns:
                new_col = re.sub(r'[][:*?/]', '_', str(col))
                new_columns[col] = new_col
            df_relations = df_relations.rename(columns=new_columns)

            excel_path = RE_RESULTS_DIR / f"{re_id}.xlsx"

            def _save_excel():
                df_relations.to_excel(excel_path, index=False, engine='openpyxl')

            await asyncio.to_thread(_save_excel)
            logger.info(f"RE 结果已保存为 Excel: {excel_path}")
        except Exception as e:
            logger.warning(f"Excel 保存失败：{e}")

    # PKL 格式
    pkl_path = RE_RESULTS_DIR / f"{re_id}.pkl"
    pkl_data = {
        're_id': re_id,
        'result_id': result_id,
        'ner_id': ner_id,
        'relations': relations,
        'relation_count': len(relations),
        'created_at': datetime.now().isoformat()
    }

    def _save_pkl():
        with open(pkl_path, 'wb') as f:
            pickle.dump(pkl_data, f)

    await asyncio.to_thread(_save_pkl)
    logger.info(f"RE 结果已保存为 PKL: {pkl_path}")

    return str(json_path), str(excel_path) if excel_path else None, str(pkl_path)


def prepare_re_input_from_ner_results(
    entities: List[Dict],
    grouped_data: List[List]
) -> Dict:
    """
    从 NER 结果准备 RE 输入数据（同步数据处理）

    按照 (doi, section, part) 整合 NER 实体和对应的原文内容

    Returns:
        input_dict: {(doi, section, part): input_text}
    """
    # 构建 (doi, section, part) => content 的映射
    content_dict = {}
    for item in grouped_data:
        if len(item) >= 5:
            doi, section_idx, group_idx, heading, text = item
            key = (doi, section_idx, group_idx)
            content_dict[key] = text

    # 按 (doi, section, part) 聚合实体
    input_dict = {}

    for entity in entities:
        doi = entity.get('doi')
        section_idx = entity.get('section_idx')
        group_idx = entity.get('group_idx')

        if doi is None or section_idx is None or group_idx is None:
            continue

        key = (doi, section_idx, group_idx)

        if key not in input_dict:
            input_dict[key] = {
                "content": content_dict.get(key, None),
                "entities": []
            }

        # 复制实体，移除位置信息字段
        entity_copy = {k: v for k, v in entity.items()
                       if k not in ['doi', 'section_idx', 'group_idx']}
        input_dict[key]['entities'].append(entity_copy)

    logger.info(f"NER 实体聚合完成：{len(input_dict)} 个 (section,group) 包含实体")

    # 转换为适合 TaskProcessor 的格式
    final_input_dict = {}
    for key, value in input_dict.items():
        entities_json = json.dumps(value['entities'], ensure_ascii=False, indent=2)
        sentences = [value['content']] if value['content'] else []
        sentences_json = json.dumps(sentences, ensure_ascii=False, indent=2)

        input_text = f"""实体列表:
{entities_json}

文本句子:
{sentences_json}"""

        final_input_dict[key] = input_text

    logger.info(f"RE 输入数据准备完成，共 {len(final_input_dict)} 组")
    return final_input_dict


async def process_re_for_ner(
    ner_id: str,
    query_file_path: Optional[str] = None,
    task_name: str = "RE_task",
    user_id: Optional[int] = None,
    progress_callback: Optional[callable] = None
) -> Dict[str, Any]:
    """
    为指定的 NER 结果执行关系抽取（异步版本）

    Args:
        progress_callback: 可选进度回调 async def callback(completed, total, message)
    """
    logger.info(f"========== 开始关系抽取 ========== ")
    logger.info(f"NER ID: {ner_id}")

    async with get_db_context() as db:
        from sqlalchemy import select
        # 查询 NER 结果
        stmt = select(NERResult).where(NERResult.ner_id == ner_id)
        result = await db.execute(stmt)
        ner_result = result.scalar_one_or_none()

        if not ner_result:
            logger.error(f"未找到 NER 结果：{ner_id}")
            return {'success': False, 'error': f'未找到 NER 结果：{ner_id}'}

        # 检查 NER 文件是否存在
        if not ner_result.ner_pkl_path or not Path(ner_result.ner_pkl_path).exists():
            if not ner_result.ner_json_path or not Path(ner_result.ner_json_path).exists():
                return {'success': False, 'error': 'NER 结果文件不存在'}

        logger.info(f"NER 结果文件：{ner_result.ner_pkl_path}")

        result_id = ner_result.result_id

    # 加载 NER 数据
    # 从 PKL 文件加载
    if ner_result.ner_pkl_path and Path(ner_result.ner_pkl_path).exists():
        def _load_pkl():
            with open(ner_result.ner_pkl_path, 'rb') as f:
                return pickle.load(f)

        pkl_data = await asyncio.to_thread(_load_pkl)
        entities = pkl_data.get('entities', [])
        grouped_data = pkl_data.get('grouped_data', [])
    else:
        # 从 JSON 文件加载
        async with aiofiles.open(ner_result.ner_json_path, 'r', encoding='utf-8') as f:
            content = await f.read()
            json_data = json.loads(content)
            entities = json_data.get('entities', [])
            grouped_data = []

    logger.info(f"加载 NER 结果：{len(entities)} 个实体")

    if grouped_data:
        # 尝试加载 grouped_data
        if ner_result.ner_pkl_path:
            grouped_data = await load_grouped_data(ner_result.ner_pkl_path)

    # 准备 RE 输入数据
    input_dict = prepare_re_input_from_ner_results(entities, grouped_data)

    if not input_dict:
        logger.error("没有有效的 NER 数据用于关系抽取")
        return {'success': False, 'error': '没有有效的 NER 数据用于关系抽取'}

    # 检查 query_file_path
    if query_file_path is None:
        return {'success': False, 'error': '必须提供 query_file_path 参数'}

    # 使用 LLM API 进行关系抽取（带进度回调）
    unique_task_name = f"{task_name}_{ner_id}_{uuid.uuid4().hex[:8]}"
    logger.info(f"开始调用 LLM API 进行关系抽取...（任务：{unique_task_name}）")

    from backend.app.utils.task_processor import AsyncTaskProcessor

    processor = AsyncTaskProcessor(
        task_name=unique_task_name,
        max_concurrent=30,
        rate_limit_delay=0.1
    )

    try:
        query_template = processor.load_query(query_file_path)
        if not query_template:
            return {'success': False, 'error': 'RE Prompt 文件加载失败'}

        data_list = list(input_dict.items())
        total = len(data_list)
        semaphore = asyncio.Semaphore(processor.max_concurrent)
        completed_count = 0
        llm_result = {}
        completed_lock = asyncio.Lock()

        async def _process_re_one(item):
            nonlocal completed_count
            key, content = item

            async with semaphore:
                try:
                    messages, raw_response = await processor.call_api(content, query_template, extra_body={"enable_thinking": False})
                    import json5
                    parsed_data = json5.loads(raw_response)
                    llm_result[key] = parsed_data
                except Exception as e:
                    logger.warning(f"RE 处理失败 {key}: {e}")
                    llm_result[key] = []
                finally:
                    async with completed_lock:
                        completed_count += 1
                        if progress_callback:
                            await progress_callback(
                                completed_count, total,
                                f"RE 处理中: {completed_count}/{total}"
                            )
                    await asyncio.sleep(processor.rate_limit_delay)

        tasks = [_process_re_one(item) for item in data_list]
        await asyncio.gather(*tasks, return_exceptions=True)

    finally:
        await processor.close()

    logger.info(f"LLM 处理完成，返回 {len(llm_result)} 条记录")

    # 解析结果，提取关系数据
    relations = []
    for key, item in llm_result.items():
        doi, section, part = key

        if isinstance(item, list) and item:
            for temp in item:
                if isinstance(temp, dict):
                    temp['doi'] = doi
                    temp['section'] = section
                    temp['part'] = part
                    relations.append(temp)
        elif isinstance(item, dict):
            if 'relations' in item:
                for temp in item['relations']:
                    if isinstance(temp, dict):
                        temp['doi'] = doi
                        temp['section'] = section
                        temp['part'] = part
                        relations.append(temp)
            else:
                item['doi'] = doi
                item['section'] = section
                item['part'] = part
                relations.append(item)
        else:
            relations.append({
                'doi': doi,
                'section': section,
                'part': part,
                'raw': str(item),
                'parsed': None
            })

    # 生成 RE 结果 ID
    re_id = f"re_{ner_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # 保存结果
    re_json_path, re_excel_path, re_pkl_path = await save_re_results(
        re_id=re_id,
        result_id=result_id,
        ner_id=ner_id,
        relations=relations
    )

    logger.info(f"关系抽取结果保存至：{re_json_path}")

    # 保存到数据库
    async with get_db_context() as db:
        from sqlalchemy import select
        stmt = select(REResult).where(REResult.ner_id == ner_id)
        result = await db.execute(stmt)
        existing_re = result.scalar_one_or_none()

        if existing_re:
            existing_re.re_json_path = str(re_json_path)
            existing_re.re_excel_path = str(re_excel_path) if re_excel_path else None
            existing_re.re_pkl_path = str(re_pkl_path) if re_pkl_path else None
            existing_re.relation_count = len(relations)
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
                relation_count=len(relations),
                status='completed',
                processed_at=datetime.now(),
                user_id=user_id
            )
            db.add(new_re)

        await db.flush()

    logger.info(f"========== 关系抽取完成 ========== ")
    logger.info(f"识别关系数：{len(relations)}")

    return {
        'success': True,
        're_id': re_id,
        'ner_id': ner_id,
        'result_id': result_id,
        'relation_count': len(relations),
        're_json_path': str(re_json_path),
        're_excel_path': str(re_excel_path) if re_excel_path else None,
        're_pkl_path': str(re_pkl_path) if re_pkl_path else None
    }


async def get_re_result(re_id: str) -> Optional[Dict[str, Any]]:
    """获取 RE 结果（异步版本）"""
    async with get_db_context() as db:
        from sqlalchemy import select
        stmt = select(REResult).where(REResult.re_id == re_id)
        result = await db.execute(stmt)
        db_record = result.scalar_one_or_none()

        if not db_record:
            return None

        return {
            're_id': db_record.re_id,
            'ner_id': db_record.ner_id,
            'result_id': db_record.result_id,
            'relation_count': db_record.relation_count,
            'status': db_record.status,
            're_json_path': db_record.re_json_path,
            're_excel_path': db_record.re_excel_path,
            're_pkl_path': db_record.re_pkl_path,
            'created_at': db_record.created_at.isoformat() if db_record.created_at else None,
            'processed_at': db_record.processed_at.isoformat() if db_record.processed_at else None
        }


async def load_re_relations(re_id: str) -> List[Dict]:
    """加载 RE 关系数据（异步版本）"""
    pkl_path = RE_RESULTS_DIR / f"{re_id}.pkl"

    if not pkl_path.exists():
        json_path = RE_RESULTS_DIR / f"{re_id}.json"
        if json_path.exists():
            async with aiofiles.open(json_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                data = json.loads(content)
                return data.get('relations', [])
        return []

    def _load_pkl():
        with open(pkl_path, 'rb') as f:
            return pickle.load(f).get('relations', [])

    return await asyncio.to_thread(_load_pkl)


async def get_re_by_ner_id(ner_id: str) -> Optional[Dict[str, Any]]:
    """根据 NER ID 获取 RE 结果（异步版本）"""
    async with get_db_context() as db:
        from sqlalchemy import select
        stmt = select(REResult).where(REResult.ner_id == ner_id)
        result = await db.execute(stmt)
        db_record = result.scalar_one_or_none()

        if not db_record:
            return None

        return await get_re_result(db_record.re_id)