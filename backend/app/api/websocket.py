"""
WebSocket 连接管理器
提供 ConnectionManager 供 Celery 任务和 Excel 提取模块使用
"""
from typing import Dict, Set
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, object] = {}
        self.user_connections: Dict[int, Set[str]] = {}  # user_id -> task_ids

    async def connect(self, task_id: str, websocket, user_id: int = None):
        """建立连接"""
        await websocket.accept()
        self.active_connections[task_id] = websocket

        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(task_id)

        logger.info(f"WebSocket 连接建立: {task_id}")

    def disconnect(self, task_id: str, user_id: int = None):
        """断开连接"""
        if task_id in self.active_connections:
            del self.active_connections[task_id]

        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(task_id)

        logger.info(f"WebSocket 连接断开: {task_id}")

    async def send_progress(self, task_id: str, data: dict):
        """发送进度消息"""
        if task_id in self.active_connections:
            try:
                await self.active_connections[task_id].send_json(data)
            except Exception as e:
                logger.warning(f"发送消息失败: {task_id}, {e}")

    async def send_to_user(self, user_id: int, data: dict):
        """向用户所有连接发送消息"""
        if user_id in self.user_connections:
            for task_id in self.user_connections[user_id]:
                await self.send_progress(task_id, data)


manager = ConnectionManager()