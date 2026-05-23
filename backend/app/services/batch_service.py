"""
批量提取服务 - 数据库持久化 + 异步处理
使用 asyncio 后台任务处理批量 NER/RE 提取，任务状态持久化到数据库
"""
import asyncio
import uuid
import json
import re
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger
from pathlib import Path
from sqlalchemy import select, update

from backend.app.core.config import settings, BASE_DIR
from backend.app.services.ner_service import process_ner_for_result
from backend.app.services.re_service import process_re_for_ner
from backend.app.models.base import get_db_context, AsyncSessionLocal
from backend.app.models.batch import BatchTask

# 非法 Excel 字符的正则（控制字符，排除 \t\n\r）
_ILLEGAL_EXCEL_RE = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]')


def _clean_excel_text(val):
    """清洗非法 Excel 字符"""
    if isinstance(val, str):
        return _ILLEGAL_EXCEL_RE.sub('', val)
    return val


async def create_batch_task_db(
    task_id: str,
    task_name: str,
    user_id: int,
    total_count: int,
    result_ids: List[str],
    config: Dict = None
) -> BatchTask:
    """创建任务记录到数据库"""
    async with AsyncSessionLocal() as db:
        task = BatchTask(
            task_id=task_id,
            task_name=task_name,
            task_type="extraction_workflow",
            result_ids=result_ids,
            config=config or {},
            status="pending",
            total_count=total_count,
            processed_count=0,
            success_count=0,
            failed_count=0,
            progress=0.0,
            user_id=user_id,
            created_at=datetime.now()
        )
        db.add(task)
        await db.commit()
        await db.refresh(task)
        logger.info(f"任务已创建: {task_id}")
        return task


async def update_batch_task_db(
    task_id: str,
    **kwargs
) -> Optional[BatchTask]:
    """更新任务状态到数据库"""
    async with AsyncSessionLocal() as db:
        stmt = select(BatchTask).where(BatchTask.task_id == task_id)
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            logger.warning(f"任务不存在: {task_id}")
            return None

        # 更新字段
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)

        task.updated_at = datetime.now()

        # 状态变化时更新时间戳
        if kwargs.get('status') == 'processing' and not task.started_at:
            task.started_at = datetime.now()
        if kwargs.get('status') in ['completed', 'failed', 'cancelled']:
            task.completed_at = datetime.now()

        await db.commit()
        await db.refresh(task)
        return task


async def get_batch_task_db(task_id: str) -> Optional[Dict[str, Any]]:
    """从数据库获取任务状态"""
    async with AsyncSessionLocal() as db:
        stmt = select(BatchTask).where(BatchTask.task_id == task_id)
        result = await db.execute(stmt)
        task = result.scalar_one_or_none()

        if not task:
            return None

        return {
            "task_id": task.task_id,
            "task_name": task.task_name,
            "status": task.status,
            "progress": task.progress,
            "total_count": task.total_count,
            "completed_count": task.success_count,
            "failed_count": task.failed_count,
            "message": task.current_step or "",
            "config": task.config or {},
            "results": task.config.get("results", []) if task.config else [],
            "errors": task.config.get("errors", []) if task.config else [],
            "created_at": task.created_at.timestamp() if task.created_at else time.time(),
            "updated_at": task.updated_at.timestamp() if task.updated_at else time.time(),
            "error_message": task.error_message
        }


async def get_user_batch_tasks_db(user_id: int) -> List[Dict[str, Any]]:
    """从数据库获取用户的所有任务"""
    async with AsyncSessionLocal() as db:
        stmt = select(BatchTask).where(BatchTask.user_id == user_id).order_by(BatchTask.created_at.desc())
        result = await db.execute(stmt)
        tasks = result.scalars().all()

        return [
            {
                "task_id": task.task_id,
                "task_name": task.task_name,
                "status": task.status,
                "progress": task.progress,
                "total_count": task.total_count,
                "completed_count": task.success_count,
                "failed_count": task.failed_count,
                "message": task.current_step or "",
                "created_at": task.created_at.timestamp() if task.created_at else time.time(),
                "updated_at": task.updated_at.timestamp() if task.updated_at else time.time(),
                "error_message": task.error_message
            }
            for task in tasks
        ]


async def _process_single_paper(
    task_id: str,
    idx: int,
    total_count: int,
    result_id: str,
    user_id: int,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    处理单篇论文的 NER/RE 提取（并行任务）

    Args:
        task_id: 批量任务 ID
        idx: 论文索引
        total_count: 总论文数
        result_id: 处理结果 ID
        user_id: 用户 ID
        config: 配置选项

    Returns:
        处理结果
    """
    # 获取配置
    do_ner = config.get("do_ner", True)
    do_re = config.get("do_re", True)
    ner_query_file = config.get("ner_query_file")
    re_query_file = config.get("re_query_file")
    skip_introduction = config.get("skip_introduction", True)
    sentence_group_size = config.get("sentence_group_size", 5)

    paper_result = {
        "result_id": result_id,
        "ner_id": None,
        "re_id": None,
        "index": idx
    }

    try:
        logger.info(f"[并行任务] 处理第 {idx + 1}/{total_count} 篇论文: {result_id}")

        # 步骤 1: NER 提取
        if do_ner:
            ner_result = await process_ner_for_result(
                result_id=result_id,
                skip_introduction=skip_introduction,
                sentence_group_size=sentence_group_size,
                query_file_path=ner_query_file,
                task_name=f"batch_{task_id}_ner_{idx}",
                user_id=user_id
            )

            if ner_result.get("success"):
                paper_result["ner_id"] = ner_result.get("ner_id")
                paper_result["entity_count"] = ner_result.get("entity_count")
                logger.info(f"[并行任务] NER 完成: {ner_result.get('ner_id')}, 实体数: {ner_result.get('entity_count')}")
            else:
                paper_result["ner_error"] = ner_result.get("error", "NER 处理失败")
                logger.warning(f"[并行任务] NER 失败: {result_id}, {paper_result['ner_error']}")

        # 步骤 2: RE 提取（依赖 NER 结果）
        if do_re and paper_result.get("ner_id"):
            re_result = await process_re_for_ner(
                ner_id=paper_result["ner_id"],
                query_file_path=re_query_file,
                task_name=f"batch_{task_id}_re_{idx}",
                user_id=user_id
            )

            if re_result.get("success"):
                paper_result["re_id"] = re_result.get("re_id")
                paper_result["relation_count"] = re_result.get("relation_count")
                logger.info(f"[并行任务] RE 完成: {re_result.get('re_id')}, 关系数: {re_result.get('relation_count')}")
            else:
                paper_result["re_error"] = re_result.get("error", "RE 处理失败")
                logger.warning(f"[并行任务] RE 失败: {result_id}, {paper_result['re_error']}")

        paper_result["success"] = bool(paper_result.get("ner_id") or (not do_ner and paper_result.get("re_id")))

    except Exception as e:
        logger.error(f"[并行任务] 处理论文失败: {result_id}, 错误: {e}")
        paper_result["success"] = False
        paper_result["error"] = str(e)

    return paper_result


async def run_batch_extraction(
    task_id: str,
    result_ids: List[str],
    user_id: int,
    config: Dict[str, Any]
):
    """
    执行批量提取的后台任务（并行处理）

    Args:
        task_id: 任务 ID
        result_ids: 处理结果 ID 列表
        user_id: 用户 ID
        config: 配置选项
            - do_ner: 是否执行 NER
            - do_re: 是否执行 RE
            - ner_query_file: NER prompt 文件路径
            - re_query_file: RE prompt 文件路径
            - skip_introduction: 是否跳过 introduction
            - sentence_group_size: 句子分组大小
            - max_concurrent: 最大并发数（默认 3）
    """
    total_count = len(result_ids)
    max_concurrent = config.get("max_concurrent", 3)  # 默认并发 3 个

    logger.info(f"开始批量提取任务: {task_id}, 共 {total_count} 篇论文, 最大并发: {max_concurrent}")

    # 更新任务状态为处理中
    await update_batch_task_db(
        task_id,
        status="processing",
        progress=0,
        current_step=f"开始处理，共 {total_count} 篇论文（并行处理）"
    )

    # 检查必要的配置
    do_ner = config.get("do_ner", True)
    do_re = config.get("do_re", True)
    ner_query_file = config.get("ner_query_file")
    re_query_file = config.get("re_query_file")

    if do_ner and not ner_query_file:
        await update_batch_task_db(
            task_id,
            status="failed",
            error_message="缺少 NER prompt 文件配置"
        )
        return

    if do_re and not re_query_file:
        await update_batch_task_db(
            task_id,
            status="failed",
            error_message="缺少 RE prompt 文件配置"
        )
        return

    # 创建信号量控制并发数
    semaphore = asyncio.Semaphore(max_concurrent)

    # 完成计数器（用于实时更新进度）
    completed_count = 0
    progress_lock = asyncio.Lock()

    async def process_with_semaphore(idx: int, result_id: str) -> Dict[str, Any]:
        """使用信号量控制并发"""
        nonlocal completed_count

        async with semaphore:
            result = await _process_single_paper(
                task_id=task_id,
                idx=idx,
                total_count=total_count,
                result_id=result_id,
                user_id=user_id,
                config=config
            )

            # 更新进度
            async with progress_lock:
                completed_count += 1
                progress = int((completed_count / total_count) * 100)
                await update_batch_task_db(
                    task_id,
                    progress=progress,
                    processed_count=completed_count,
                    current_step=f"处理中 {completed_count}/{total_count} 篇论文"
                )

            return result

    # 并行执行所有任务
    tasks = [
        process_with_semaphore(idx, result_id)
        for idx, result_id in enumerate(result_ids)
    ]

    # 使用 asyncio.gather 并行执行，不因单个失败而中断
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 整理结果
    final_results = []
    errors = []

    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            # 任务抛出异常
            errors.append({
                "result_id": result_ids[idx],
                "stage": "unknown",
                "error": str(result)
            })
            final_results.append({
                "result_id": result_ids[idx],
                "success": False,
                "error": str(result)
            })
        else:
            # 正常结果
            final_results.append(result)
            if not result.get("success"):
                error_info = {
                    "result_id": result.get("result_id"),
                    "stage": "processing"
                }
                if result.get("ner_error"):
                    error_info["stage"] = "ner"
                    error_info["error"] = result["ner_error"]
                elif result.get("re_error"):
                    error_info["stage"] = "re"
                    error_info["error"] = result["re_error"]
                elif result.get("error"):
                    error_info["stage"] = "unknown"
                    error_info["error"] = result["error"]
                errors.append(error_info)

    # 任务完成
    successful_count = len([r for r in final_results if r.get("success")])
    failed_count = len(errors)
    final_status = "completed" if successful_count > 0 else "failed"
    final_message = f"处理完成，成功 {successful_count} 篇，失败 {failed_count} 篇"

    # 更新配置中的结果和错误
    config["results"] = final_results
    config["errors"] = errors

    await update_batch_task_db(
        task_id,
        status=final_status,
        progress=100,
        success_count=successful_count,
        failed_count=failed_count,
        current_step=final_message,
        config=config
    )

    logger.info(f"批量提取任务完成: {task_id}, {final_message}")


async def create_batch_task(
    task_name: str,
    result_ids: List[str],
    user_id: int,
    config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    创建并启动批量提取任务

    Returns:
        任务信息
    """
    # 生成任务 ID
    task_id = f"batch_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    # 创建任务记录到数据库
    await create_batch_task_db(
        task_id=task_id,
        task_name=task_name,
        user_id=user_id,
        total_count=len(result_ids),
        result_ids=result_ids,
        config=config
    )

    # 启动后台任务
    asyncio.create_task(run_batch_extraction(
        task_id=task_id,
        result_ids=result_ids,
        user_id=user_id,
        config=config
    ))

    return {
        "task_id": task_id,
        "task_name": task_name,
        "status": "pending",
        "total_count": len(result_ids),
        "message": "任务已创建并开始执行"
    }


async def get_batch_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    """获取批量任务状态"""
    return await get_batch_task_db(task_id)


async def get_user_batch_tasks(user_id: int) -> List[Dict[str, Any]]:
    """获取用户的批量任务列表"""
    return await get_user_batch_tasks_db(user_id)


async def cancel_batch_task(task_id: str) -> Dict[str, Any]:
    """
    取消批量任务

    注意：由于使用 asyncio 任务，无法直接取消正在执行的任务
    只能标记为已取消，任务会在下一个检查点停止
    """
    task_info = await get_batch_task_db(task_id)

    if not task_info:
        return {"success": False, "message": "任务不存在"}

    if task_info.get("status") in ["completed", "failed", "cancelled"]:
        return {"success": False, "message": "任务已完成，无法取消"}

    # 标记为已取消
    await update_batch_task_db(
        task_id,
        status="cancelled",
        current_step="用户取消任务"
    )

    return {"success": True, "message": f"任务 {task_id} 已取消"}


def get_default_prompt_files() -> Dict[str, str]:
    """
    获取默认的 prompt 文件路径
    """
    from backend.app.core.config import BASE_DIR

    scipdf_dir = BASE_DIR / "scipdf"

    # 查找 NER prompt 文件
    ner_prompt = None
    ner_dir = scipdf_dir / "ner_queries"
    if ner_dir.exists():
        for pattern in ["material_ner.txt", "ner*.txt"]:
            matches = list(ner_dir.glob(pattern))
            if matches:
                ner_prompt = str(matches[0])
                break

    # 查找 RE prompt 文件
    re_prompt = None
    re_dir = scipdf_dir / "re_queries"
    if re_dir.exists():
        for pattern in ["material_re.txt", "re*.txt"]:
            matches = list(re_dir.glob(pattern))
            if matches:
                re_prompt = str(matches[0])
                break

    return {
        "ner_query_file": ner_prompt,
        "re_query_file": re_prompt
    }


async def export_batch_results_excel(task_id: str) -> Dict[str, Any]:
    """
    导出批量任务结果为 Excel 文件（包含 content, NER, RE 三个 sheet）

    Args:
        task_id: 任务 ID

    Returns:
        导出结果，包含文件路径和 sheet 信息
    """
    import pandas as pd
    from pathlib import Path

    # 获取任务状态
    task_status = await get_batch_task_db(task_id)
    if not task_status:
        return {"success": False, "error": "任务不存在"}

    results = task_status.get("results", [])
    if not results:
        return {"success": False, "error": "任务没有处理结果"}

    logger.info(f"开始导出任务 {task_id}，共 {len(results)} 篇论文结果")

    all_content = []
    all_ner = []
    all_re = []
    sheet_info = {}

    # 收集所有数据
    for idx, result in enumerate(results):
        result_id = result.get("result_id")
        ner_id = result.get("ner_id")
        re_id = result.get("re_id")

        logger.info(f"处理第 {idx+1} 篇论文: result_id={result_id}, ner_id={ner_id}, re_id={re_id}")

        # 加载 content 数据（对所有论文）
        content_data = await _load_content_data(result_id)
        logger.info(f"  加载 content: {len(content_data)} 条")
        all_content.extend(content_data)

        # 加载 NER 数据
        if ner_id:
            ner_data = await _load_ner_data(ner_id, result_id)
            logger.info(f"  加载 NER: {len(ner_data)} 条")
            all_ner.extend(ner_data)

        # 加载 RE 数据
        if re_id:
            re_data = await _load_re_data(re_id)
            logger.info(f"  加载 RE: {len(re_data)} 条")
            all_re.extend(re_data)

    logger.info(f"数据汇总: content={len(all_content)}, NER={len(all_ner)}, RE={len(all_re)}")

    # 生成 Excel 文件
    output_dir = BASE_DIR / "outputs" / "batch_exports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{task_id}_results.xlsx"

    try:
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # Content sheet
            if all_content:
                df_content = pd.DataFrame(all_content).map(_clean_excel_text)
                df_content.to_excel(writer, sheet_name='content', index=False)
                sheet_info['content'] = len(df_content)
            else:
                pd.DataFrame(columns=['doi', 'section_idx', 'group_idx', 'heading', 'text']).to_excel(
                    writer, sheet_name='content', index=False)
                sheet_info['content'] = 0

            # NER sheet
            if all_ner:
                df_ner = pd.DataFrame(all_ner).map(_clean_excel_text)
                df_ner.to_excel(writer, sheet_name='NER', index=False)
                sheet_info['NER'] = len(df_ner)
            else:
                pd.DataFrame().to_excel(writer, sheet_name='NER', index=False)
                sheet_info['NER'] = 0

            # RE sheet
            if all_re:
                df_re = pd.DataFrame(all_re).map(_clean_excel_text)
                df_re.to_excel(writer, sheet_name='RE', index=False)
                sheet_info['RE'] = len(df_re)
            else:
                pd.DataFrame().to_excel(writer, sheet_name='RE', index=False)
                sheet_info['RE'] = 0

        logger.info(f"Excel 导出成功: {output_path}, sheet 信息: {sheet_info}")

        return {
            "success": True,
            "file_path": str(output_path),
            "sheet_info": sheet_info
        }

    except Exception as e:
        logger.error(f"Excel 导出失败: {e}")
        return {"success": False, "error": str(e)}


async def _load_content_data(result_id: str) -> List[Dict]:
    """加载论文的原文内容"""
    from backend.app.models.paper import ProcessingResult

    content_data = []

    async with AsyncSessionLocal() as db:
        stmt = select(ProcessingResult).where(ProcessingResult.result_id == result_id)
        result = await db.execute(stmt)
        db_result = result.scalar_one_or_none()

        if not db_result:
            logger.warning(f"未找到处理结果: {result_id}")
            return content_data

        if not db_result.result_json_path:
            logger.warning(f"处理结果没有 JSON 路径: {result_id}")
            return content_data

        original_doi = db_result.doi if db_result.doi else result_id
        json_path = Path(db_result.result_json_path)

        logger.debug(f"尝试加载 JSON: {json_path}, exists={json_path.exists()}")

        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                parse_result = json.load(f)

            # 提取 abstract
            abstract = parse_result.get('abstract', '')
            if abstract:
                content_data.append({
                    'doi': original_doi,
                    'section_idx': 0,
                    'group_idx': 1,
                    'heading': 'abstract',
                    'text': abstract
                })

            # 提取 sections（只要 text 存在就包含）
            sections = parse_result.get('sections', [])
            for sec in sections:
                if isinstance(sec, dict):
                    heading = sec.get('heading', '') or 'content'  # 如果 heading 为空，使用 'content'
                    text = sec.get('text', '')
                    if text:  # 只要 text 存在就包含
                        content_data.append({
                            'doi': original_doi,
                            'section_idx': len(content_data) + 1,
                            'group_idx': 1,
                            'heading': heading,
                            'text': text
                        })

            logger.info(f"从 {json_path} 加载 {len(content_data)} 条 content 数据")
        else:
            logger.warning(f"JSON 文件不存在: {json_path}")

    return content_data


async def _load_ner_data(ner_id: str, result_id: str) -> List[Dict]:
    """加载 NER 结果"""
    from backend.app.models.ner import NERResult
    from backend.app.models.paper import ProcessingResult

    ner_data = []

    # 获取原始 DOI
    original_doi = None
    async with AsyncSessionLocal() as db:
        stmt = select(ProcessingResult).where(ProcessingResult.result_id == result_id)
        result = await db.execute(stmt)
        db_result = result.scalar_one_or_none()
        if db_result and db_result.doi:
            original_doi = db_result.doi

        # 获取 NER 结果
        stmt = select(NERResult).where(NERResult.ner_id == ner_id)
        result = await db.execute(stmt)
        ner_record = result.scalar_one_or_none()

        if not ner_record or not ner_record.ner_json_path:
            return ner_data

        # 加载 NER JSON
        json_path = Path(ner_record.ner_json_path)
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                ner_result = json.load(f)

            entities = ner_result.get('entities', [])
            if isinstance(entities, list):
                for ent in entities:
                    if isinstance(ent, dict):
                        # 替换 doi
                        if 'doi' in ent and original_doi and ent['doi'] == result_id:
                            ent['doi'] = original_doi
                        ner_data.append(ent)

    return ner_data


async def _load_re_data(re_id: str) -> List[Dict]:
    """加载 RE 结果"""
    from backend.app.models.re import REResult

    re_data = []

    async with AsyncSessionLocal() as db:
        stmt = select(REResult).where(REResult.re_id == re_id)
        result = await db.execute(stmt)
        re_record = result.scalar_one_or_none()

        if not re_record or not re_record.re_json_path:
            return re_data

        # 加载 RE JSON
        json_path = Path(re_record.re_json_path)
        if json_path.exists():
            with open(json_path, 'r', encoding='utf-8') as f:
                re_result = json.load(f)

            relations = re_result.get('relations', [])
            if isinstance(relations, list):
                for rel in relations:
                    if isinstance(rel, dict):
                        re_data.append(rel)

    return re_data