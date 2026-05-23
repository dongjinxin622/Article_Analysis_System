"""
存储服务 - 处理文件上传和管理
"""
import os
import uuid
import logging
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, BinaryIO

import aiofiles

from backend.app.core.config import settings, UPLOADS_DIR, RESULTS_DIR, NER_RESULTS_DIR, RE_RESULTS_DIR, FAILED_LOGS_DIR

logger = logging.getLogger(__name__)


class StorageService:
    """存储服务类"""

    def __init__(self):
        self.max_upload_size = settings.MAX_UPLOAD_SIZE
        self.allowed_extensions = settings.ALLOWED_EXTENSIONS

    def validate_file(self, file_name: str, file_size: int) -> bool:
        """验证文件"""
        # 检查扩展名
        ext = Path(file_name).suffix.lower()
        if ext not in self.allowed_extensions:
            logger.warning(f"文件扩展名不允许: {ext}")
            return False

        # 检查大小
        if file_size > self.max_upload_size:
            logger.warning(f"文件大小超限: {file_size} > {self.max_upload_size}")
            return False

        return True

    async def save_upload_file(
        self,
        file_content: BinaryIO,
        file_name: str,
        user_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        保存上传文件

        Args:
            file_content: 文件内容流
            file_name: 文件名
            user_id: 用户 ID

        Returns:
            保存结果
        """
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

        # 生成唯一文件名
        unique_id = uuid.uuid4().hex[:8]
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        safe_name = Path(file_name).stem.replace(" ", "_")
        new_file_name = f"{safe_name}_{timestamp}_{unique_id}.pdf"

        file_path = UPLOADS_DIR / new_file_name

        # 异步保存文件
        async with aiofiles.open(file_path, 'wb') as f:
            content = await asyncio.to_thread(file_content.read)
            await f.write(content)

        file_size = os.path.getsize(file_path)

        logger.info(f"文件保存成功: {file_path}, 大小: {file_size}")

        return {
            "success": True,
            "file_path": str(file_path),
            "file_name": new_file_name,
            "original_name": file_name,
            "file_size": file_size
        }

    async def delete_file(self, file_path: str) -> bool:
        """删除文件"""
        if not Path(file_path).exists():
            logger.warning(f"文件不存在: {file_path}")
            return False

        try:
            await asyncio.to_thread(os.remove, file_path)
            logger.info(f"文件删除成功: {file_path}")
            return True
        except Exception as e:
            logger.error(f"文件删除失败: {file_path}, {e}")
            return False

    async def get_file_info(self, file_path: str) -> Optional[Dict[str, Any]]:
        """获取文件信息"""
        path = Path(file_path)
        if not path.exists():
            return None

        return {
            "file_path": str(path),
            "file_name": path.name,
            "file_size": path.stat().st_size,
            "created_at": datetime.fromtimestamp(path.stat().st_ctime).isoformat()
        }

    def get_result_path(self, result_id: str, ext: str = "json") -> Path:
        """获取结果文件路径"""
        return RESULTS_DIR / f"{result_id}.{ext}"

    def get_ner_result_path(self, ner_id: str, ext: str = "json") -> Path:
        """获取 NER 结果文件路径"""
        return NER_RESULTS_DIR / f"{ner_id}.{ext}"

    def get_re_result_path(self, re_id: str, ext: str = "json") -> Path:
        """获取 RE 结果文件路径"""
        return RE_RESULTS_DIR / f"{re_id}.{ext}"


# 全局存储服务实例
_storage_service: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    """获取存储服务实例"""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service