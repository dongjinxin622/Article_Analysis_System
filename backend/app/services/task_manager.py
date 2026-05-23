# -*- coding: utf-8 -*-
"""
任务管理器

使用 Redis 存储和管理任务状态、进度和结果。
"""

import json
import time
from typing import Dict, Any, Optional, List
from loguru import logger
import redis

from backend.app.core.config import settings


class TaskManager:
    """
    任务管理器

    使用 Redis 存储任务状态信息。
    """

    def __init__(self):
        """初始化任务管理器"""
        self.redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True
        )
        self.key_prefix = "task:"
        self.key_expire = 7200  # 2小时过期（支持长时间运行的NER+RE任务）
        logger.info("任务管理器已初始化")

    def _get_key(self, task_id: str) -> str:
        """获取 Redis key"""
        return f"{self.key_prefix}{task_id}"

    def create_task(
        self,
        task_id: str,
        task_type: str,
        user_id: int,
        params: Dict = None
    ) -> Dict[str, Any]:
        """
        创建任务记录

        Args:
            task_id: 任务 ID
            task_type: 任务类型
            user_id: 用户 ID
            params: 任务参数

        Returns:
            任务信息
        """
        task_info = {
            "task_id": task_id,
            "task_type": task_type,
            "user_id": user_id,
            "status": "pending",
            "progress": 0,
            "message": "任务已创建",
            "params": params or {},
            "result": None,
            "error": None,
            "created_at": time.time(),
            "updated_at": time.time()
        }

        key = self._get_key(task_id)
        self.redis_client.setex(
            key,
            self.key_expire,
            json.dumps(task_info)
        )

        logger.info(f"任务已创建: {task_id}")
        return task_info

    def update_task_status(
        self,
        task_id: str,
        status: str = None,
        progress: int = None,
        stage: str = None,
        message: str = None,
        result: Dict = None,
        error: str = None
    ) -> Dict[str, Any]:
        """
        更新任务状态

        Args:
            task_id: 任务 ID
            status: 状态（pending/processing/completed/failed）
            progress: 进度（0-100）
            stage: 当前阶段
            message: 消息
            result: 结果
            error: 错误信息

        Returns:
            更新后的任务信息
        """
        key = self._get_key(task_id)
        task_data = self.redis_client.get(key)

        if not task_data:
            logger.warning(f"任务不存在: {task_id}")
            return {}

        task_info = json.loads(task_data)

        # 更新字段
        if status:
            task_info["status"] = status
        if progress is not None:
            task_info["progress"] = progress
        if stage:
            task_info["stage"] = stage
        if message:
            task_info["message"] = message
        if result:
            task_info["result"] = result
        if error:
            task_info["error"] = error

        task_info["updated_at"] = time.time()

        # 保存
        self.redis_client.setex(
            key,
            self.key_expire,
            json.dumps(task_info)
        )

        return task_info

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务信息
        """
        key = self._get_key(task_id)
        task_data = self.redis_client.get(key)

        if not task_data:
            return {"task_id": task_id, "status": "not_found"}

        return json.loads(task_data)

    def get_user_tasks(self, user_id: int) -> List[Dict[str, Any]]:
        """
        获取用户的所有任务

        Args:
            user_id: 用户 ID

        Returns:
            任务列表
        """
        tasks = []
        pattern = f"{self.key_prefix}*"

        for key in self.redis_client.scan_iter(match=pattern):
            task_data = self.redis_client.get(key)
            if task_data:
                task_info = json.loads(task_data)
                if task_info.get("user_id") == user_id:
                    tasks.append(task_info)

        # 按创建时间降序排序
        tasks.sort(key=lambda x: x.get("created_at", 0), reverse=True)

        return tasks

    def delete_task(self, task_id: str) -> bool:
        """
        删除任务记录

        Args:
            task_id: 任务 ID

        Returns:
            是否成功
        """
        key = self._get_key(task_id)
        result = self.redis_client.delete(key)

        if result:
            logger.info(f"任务已删除: {task_id}")
            return True
        else:
            logger.warning(f"任务不存在或已过期: {task_id}")
            return False

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """
        获取所有活跃任务

        Returns:
            活跃任务列表
        """
        tasks = []
        pattern = f"{self.key_prefix}*"

        for key in self.redis_client.scan_iter(match=pattern):
            task_data = self.redis_client.get(key)
            if task_data:
                task_info = json.loads(task_data)
                if task_info.get("status") in ["pending", "processing"]:
                    tasks.append(task_info)

        return tasks

    def cleanup_expired_tasks(self) -> int:
        """
        清理过期任务

        Returns:
            清理数量
        """
        # Redis 自动过期，此方法可手动清理已完成但未过期的任务
        cleaned = 0
        pattern = f"{self.key_prefix}*"

        for key in self.redis_client.scan_iter(match=pattern):
            task_data = self.redis_client.get(key)
            if task_data:
                task_info = json.loads(task_data)
                # 清理超过24小时的已完成任务
                if task_info.get("status") in ["completed", "failed"]:
                    updated_at = task_info.get("updated_at", 0)
                    if time.time() - updated_at > 86400:  # 24小时
                        self.redis_client.delete(key)
                        cleaned += 1

        logger.info(f"清理过期任务: {cleaned} 个")
        return cleaned

    def set_task_progress_steps(
        self,
        task_id: str,
        steps: List[Dict[str, Any]]
    ) -> None:
        """
        设置任务进度步骤

        Args:
            task_id: 任务 ID
            steps: 步骤列表 [{"name": "step1", "weight": 30}, ...]
        """
        key = f"{self.key_prefix}{task_id}:steps"
        self.redis_client.setex(
            key,
            self.key_expire,
            json.dumps(steps)
        )

    def get_task_progress_steps(self, task_id: str) -> List[Dict[str, Any]]:
        """
        获取任务进度步骤

        Args:
            task_id: 任务 ID

        Returns:
            步骤列表
        """
        key = f"{self.key_prefix}{task_id}:steps"
        steps_data = self.redis_client.get(key)

        if not steps_data:
            return []

        return json.loads(steps_data)