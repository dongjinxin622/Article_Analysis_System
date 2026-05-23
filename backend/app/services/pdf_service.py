"""
PDF 解析服务 - 异步版本
负责使用 scipdf_parser 解析 PDF 文件，支持 PyMuPDF 备用方案
"""
import os
import json
import pickle
import logging
import uuid
import re
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

import aiofiles
import fitz  # PyMuPDF

from backend.app.core.config import settings, RESULTS_DIR, FAILED_LOGS_DIR, UPLOADS_DIR
from backend.app.models.base import get_db_context
from backend.app.models.paper import ProcessingResult
from backend.app.models.domain import FailedLog

logger = logging.getLogger(__name__)


def generate_result_id(doi: Optional[str], file_name: str) -> str:
    """
    生成结果唯一标识符
    - 如果有 DOI，使用 DOI
    - 否则使用文件名
    """
    if doi:
        return doi.replace("/", "_").replace(":", "_")

    name_without_ext = Path(file_name).stem
    name_without_ext = re.sub(r'[^a-zA-Z0-9_-]', '_', name_without_ext)
    return f"file_{name_without_ext}"


async def extract_doi_from_pdf(file_path: str) -> Optional[str]:
    """
    使用 PyMuPDF 从 PDF 中提取 DOI（异步版本）
    """
    def _extract():
        try:
            doc = fitz.open(file_path)
            text = ""
            for i in range(min(2, len(doc))):
                text += doc[i].get_text()

            doi_pattern = r'10\.\d{4,9}/[-._;():/A-Za-z0-9]+'
            matches = re.search(doi_pattern, text)
            if matches:
                return matches.group(0)
            doc.close()
            return None
        except Exception as e:
            logger.warning(f"提取 DOI 失败：{e}")
            return None

    return await asyncio.to_thread(_extract)


async def parse_pdf_with_pymupdf(file_path: str) -> Dict[str, Any]:
    """
    使用 PyMuPDF 解析 PDF 文件（异步版本）
    """
    def _parse():
        try:
            doc = fitz.open(file_path)
            sections = []
            full_text = ""

            for i, page in enumerate(doc):
                text = page.get_text()
                full_text += text

                paragraphs = text.split('\n\n')
                for para in paragraphs:
                    if para.strip():
                        sections.append({
                            "heading": f"Section_{i}_{len(sections)}",
                            "text": para.strip()
                        })

            doc.close()

            return {
                "title": "",
                "abstract": "",
                "doi": None,
                "sections": sections,
                "references": [],
                "figures": [],
                "full_text": full_text
            }
        except Exception as e:
            logger.error(f"PyMuPDF 解析失败：{e}")
            raise

    return await asyncio.to_thread(_parse)


async def parse_pdf_file(file_path: str, result_id: str) -> Dict[str, Any]:
    """
    解析单个 PDF 文件（异步版本）
    优先使用 scipdf_parser，失败时使用 PyMuPDF
    """
    logger.info(f"开始解析 PDF: {file_path}")

    def _parse_with_scipdf():
        try:
            import scipdf
            article_dict = scipdf.parse_pdf_to_dict(file_path, as_list=False)
            return {
                "result_id": result_id,
                "file_path": file_path,
                "parsed_at": datetime.now().isoformat(),
                "title": article_dict.get("title", ""),
                "abstract": article_dict.get("abstract", ""),
                "doi": article_dict.get("doi", ""),
                "sections": article_dict.get("sections", []),
                "references": article_dict.get("references", []),
                "figures": article_dict.get("figures", []),
            }
        except Exception as e:
            logger.warning(f"scipdf_parser 解析失败: {e}")
            return None

    # 尝试使用 scipdf_parser
    result = await asyncio.to_thread(_parse_with_scipdf)

    if result:
        logger.info(f"PDF 解析成功 (scipdf_parser): {file_path}")
        return result

    # 使用 PyMuPDF 备用方案
    logger.warning(f"使用 PyMuPDF 备用方案解析: {file_path}")
    result = await parse_pdf_with_pymupdf(file_path)
    result["result_id"] = result_id
    result["file_path"] = file_path
    result["parsed_at"] = datetime.now().isoformat()

    # 异步提取 DOI
    doi = await extract_doi_from_pdf(file_path)
    result["doi"] = doi

    logger.info(f"PDF 解析成功 (PyMuPDF): {file_path}")
    return result


async def save_result(result: Dict[str, Any]) -> Tuple[str, str]:
    """
    保存解析结果到 pkl 和 json 文件（异步版本）
    """
    result_id = result["result_id"]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    pkl_path = RESULTS_DIR / f"{result_id}.pkl"
    json_path = RESULTS_DIR / f"{result_id}.json"

    # 异步保存 pkl 文件
    def _save_pkl():
        with open(pkl_path, "wb") as f:
            pickle.dump(result, f)

    await asyncio.to_thread(_save_pkl)

    # 异步保存 json 文件
    json_result = {
        "result_id": result["result_id"],
        "title": result.get("title", ""),
        "abstract": result.get("abstract", ""),
        "doi": result.get("doi", ""),
        "file_path": result["file_path"],
        "parsed_at": result["parsed_at"],
        "sections": result.get("sections", []),
        "references": result.get("references", []),
        "figures": result.get("figures", []),
    }

    async with aiofiles.open(json_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(json_result, ensure_ascii=False, indent=2))

    logger.info(f"结果已保存：{pkl_path}, {json_path}")

    return str(pkl_path), str(json_path)


async def save_to_database(
    result: Dict[str, Any],
    pkl_path: str,
    json_path: str,
    file_name: str,
    user_id: Optional[int] = None,
    status: str = "completed",
    error_message: Optional[str] = None
) -> int:
    """
    将解析结果保存到数据库（异步版本）
    """
    async with get_db_context() as db:
        # 检查是否已存在
        from sqlalchemy import select
        stmt = select(ProcessingResult).where(
            ProcessingResult.result_id == result["result_id"]
        )
        existing_result = await db.execute(stmt)
        existing = existing_result.scalar_one_or_none()

        if existing:
            existing.title = result.get("title")
            existing.abstract = result.get("abstract")
            existing.doi = result.get("doi")
            existing.status = status
            existing.result_pkl_path = pkl_path
            existing.result_json_path = json_path
            existing.error_message = error_message
            existing.processed_at = datetime.now()
            if user_id:
                existing.user_id = user_id
            await db.flush()
            return existing.id
        else:
            db_record = ProcessingResult(
                result_id=result["result_id"],
                file_name=file_name,
                file_path=result["file_path"],
                title=result.get("title"),
                abstract=result.get("abstract"),
                doi=result.get("doi"),
                status=status,
                result_pkl_path=pkl_path,
                result_json_path=json_path,
                error_message=error_message,
                processed_at=datetime.now(),
                user_id=user_id
            )
            db.add(db_record)
            await db.flush()
            return db_record.id


async def save_failed_log(
    file_name: str,
    error_type: str,
    error_message: str,
    error_stack: Optional[str] = None,
    result_id: Optional[str] = None
):
    """保存失败日志到数据库和文件（异步版本）"""
    import traceback

    log_id = str(uuid.uuid4())

    async with get_db_context() as db:
        log_record = FailedLog(
            log_id=log_id,
            result_id=result_id,
            file_name=file_name,
            error_type=error_type,
            error_message=error_message,
            error_stack=error_stack or traceback.format_exc(),
            retry_count=0
        )
        db.add(log_record)
        await db.flush()

    # 异步保存 JSON 日志文件
    FAILED_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = FAILED_LOGS_DIR / f"{log_id}.json"
    log_data = {
        "log_id": log_id,
        "result_id": result_id,
        "file_name": file_name,
        "error_type": error_type,
        "error_message": error_message,
        "error_stack": error_stack or traceback.format_exc(),
        "created_at": datetime.now().isoformat()
    }

    async with aiofiles.open(log_file, "w", encoding="utf-8") as f:
        await f.write(json.dumps(log_data, ensure_ascii=False, indent=2))

    logger.error(f"失败日志已保存：{log_file}")


async def process_pdf(
    file_path: str,
    file_name: str,
    user_id: Optional[int] = None,
    max_retries: int = 3,
    retry_delay: int = 2
) -> Dict[str, Any]:
    """
    处理单个 PDF 文件的完整流程（异步版本，支持失败自动重试）
    """
    logger.info(f"========== 开始处理 PDF ========== ")
    logger.info(f"文件名: {file_name}")
    logger.info(f"文件路径: {file_path}")
    logger.info(f"最大重试次数：{max_retries}")

    last_error = None
    retry_count = 0
    result_id = None

    while retry_count < max_retries:
        try:
            # 步骤 1: 提取 DOI
            logger.info(f"[步骤 1] 正在提取 DOI...")
            doi = await extract_doi_from_pdf(file_path)
            if doi:
                logger.info(f"[步骤 1] DOI 提取成功: {doi}")
            else:
                logger.warning(f"[步骤 1] 未找到 DOI，将使用文件名作为标识")

            # 生成 result_id
            result_id = generate_result_id(doi, file_name)
            logger.info(f"生成结果 ID: {result_id}")

            # 步骤 2: 解析 PDF
            logger.info(f"[步骤 2] 正在解析 PDF...")
            result = await parse_pdf_file(file_path, result_id)
            logger.info(f"[步骤 2] PDF 解析完成，获取 {len(result.get('sections', []))} 个章节")

            # 更新 DOI（如果解析后获取到了）
            if not doi and result.get("doi"):
                doi = result["doi"]
                logger.info(f"[步骤 2] 从解析结果获取 DOI: {doi}")

            # 步骤 3: 保存结果文件
            logger.info(f"[步骤 3] 正在保存解析结果文件...")
            pkl_path, json_path = await save_result(result)
            logger.info(f"[步骤 3] 结果文件保存完成")

            # 步骤 4: 保存到数据库
            logger.info(f"[步骤 4] 正在保存到数据库...")
            db_id = await save_to_database(
                result=result,
                pkl_path=pkl_path,
                json_path=json_path,
                file_name=file_name,
                user_id=user_id,
                status="completed"
            )
            logger.info(f"[步骤 4] 数据库记录保存完成, ID={db_id}")

            if retry_count > 0:
                logger.info(f"PDF 处理后重试成功：{file_name}, 重试次数：{retry_count}")

            logger.info(f"========== PDF 处理完成 ========== ")

            return {
                "success": True,
                "result_id": result_id,
                "file_name": file_name,
                "doi": doi,
                "title": result.get("title", ""),
                "pkl_path": pkl_path,
                "json_path": json_path,
                "db_id": db_id
            }

        except Exception as e:
            retry_count += 1
            last_error = e
            import traceback as tb
            error_stack = tb.format_exc()

            logger.warning(
                f"[失败] 处理 PDF 失败 (尝试 {retry_count}/{max_retries}): {file_name}, "
                f"错误：{e}"
            )

            if retry_count < max_retries:
                logger.info(f"[重试] 等待 {retry_delay} 秒后重试...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error(f"[最终失败] 处理 PDF 最终失败: {file_name}")

                await save_failed_log(
                    file_name=file_name,
                    error_type="parse_error",
                    error_message=str(e),
                    error_stack=error_stack,
                    result_id=result_id
                )

                # 更新数据库状态为失败
                if result_id:
                    async with get_db_context() as db:
                        from sqlalchemy import select
                        stmt = select(ProcessingResult).where(
                            ProcessingResult.result_id == result_id
                        )
                        existing_result = await db.execute(stmt)
                        existing = existing_result.scalar_one_or_none()
                        if existing:
                            existing.status = "failed"
                            existing.error_message = str(e)

    return {
        "success": False,
        "file_name": file_name,
        "error": str(last_error),
        "retry_count": retry_count,
        "max_retries": max_retries
    }


async def get_processing_result(result_id: str) -> Optional[Dict[str, Any]]:
    """
    获取处理结果（异步版本）
    """
    async with get_db_context() as db:
        from sqlalchemy import select
        stmt = select(ProcessingResult).where(ProcessingResult.result_id == result_id)
        result = await db.execute(stmt)
        db_record = result.scalar_one_or_none()

        if not db_record:
            return None

        return {
            "result_id": db_record.result_id,
            "file_name": db_record.file_name,
            "title": db_record.title,
            "doi": db_record.doi,
            "abstract": db_record.abstract,
            "status": db_record.status,
            "result_pkl_path": db_record.result_pkl_path,
            "result_json_path": db_record.result_json_path,
            "created_at": db_record.created_at.isoformat() if db_record.created_at else None,
            "processed_at": db_record.processed_at.isoformat() if db_record.processed_at else None
        }


async def load_result_json(result_id: str) -> Optional[Dict[str, Any]]:
    """
    加载 JSON 解析结果（异步版本）
    """
    json_path = RESULTS_DIR / f"{result_id}.json"

    if not json_path.exists():
        return None

    async with aiofiles.open(json_path, "r", encoding="utf-8") as f:
        content = await f.read()
        return json.loads(content)


async def delete_processing_result(result_id: str) -> bool:
    """
    删除处理结果及相关文件（异步版本）
    """
    import os

    async with get_db_context() as db:
        from sqlalchemy import select, delete
        from backend.app.models.ner import NERResult
        from backend.app.models.re import REResult

        stmt = select(ProcessingResult).where(ProcessingResult.result_id == result_id)
        result = await db.execute(stmt)
        db_record = result.scalar_one_or_none()

        if not db_record:
            return False

        # 查找关联的 NER 和 RE 结果
        ner_stmt = select(NERResult).where(NERResult.result_id == result_id)
        ner_result = await db.execute(ner_stmt)
        ner_records = ner_result.scalars().all()

        re_stmt = select(REResult).where(REResult.result_id == result_id)
        re_result = await db.execute(re_stmt)
        re_records = re_result.scalars().all()

        # 收集所有要删除的文件路径
        files_to_delete = [
            db_record.result_pkl_path,
            db_record.result_json_path,
            db_record.file_path
        ]

        # 添加 NER 结果文件
        for ner in ner_records:
            if ner.ner_json_path:
                files_to_delete.append(ner.ner_json_path)
            if ner.ner_excel_path:
                files_to_delete.append(ner.ner_excel_path)
            if ner.ner_pkl_path:
                files_to_delete.append(ner.ner_pkl_path)

        # 添加 RE 结果文件
        for re_rec in re_records:
            if re_rec.re_json_path:
                files_to_delete.append(re_rec.re_json_path)
            if re_rec.re_excel_path:
                files_to_delete.append(re_rec.re_excel_path)
            if re_rec.re_pkl_path:
                files_to_delete.append(re_rec.re_pkl_path)

        # 删除所有文件
        for file_path in set(files_to_delete):  # 去重
            if file_path and Path(file_path).exists():
                try:
                    await asyncio.to_thread(os.remove, file_path)
                except Exception as e:
                    logger.warning(f"删除文件失败: {file_path}, {e}")

        # 删除数据库记录（级联删除会处理 NER/RE 记录）
        await db.execute(delete(ProcessingResult).where(ProcessingResult.result_id == result_id))

        return True