"""
WebSocket 处理 - 实时进度推送
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from typing import Dict, Set
import asyncio
import json
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_connections: Dict[int, Set[str]] = {}  # user_id -> task_ids

    async def connect(self, task_id: str, websocket: WebSocket, user_id: int = None):
        """建立连接"""
        await websocket.accept()
        self.active_connections[task_id] = websocket

        # 记录用户连接
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(task_id)

        logger.info(f"WebSocket 连接建立: {task_id}")

    def disconnect(self, task_id: str, user_id: int = None):
        """断开连接"""
        if task_id in self.active_connections:
            del self.active_connections[task_id]

        # 移除用户连接记录
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

    async def broadcast(self, message: dict):
        """广播消息"""
        for connection in self.active_connections.values():
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"广播消息失败: {e}")

    async def push_task_status(self, task_id: str):
        """
        主动推送任务状态

        从 Redis 获取任务状态并推送
        """
        from backend.app.services.task_manager import TaskManager
        task_manager = TaskManager()

        task_status = task_manager.get_task_status(task_id)

        if task_id in self.active_connections:
            await self.send_progress(task_id, {
                "event": "task_status",
                "data": task_status
            })


manager = ConnectionManager()


@router.websocket("/ws/tasks/{task_id}")
async def task_progress_ws(websocket: WebSocket, task_id: str):
    """
    WebSocket 任务进度推送

    - **task_id**: 任务 ID
    """
    await manager.connect(task_id, websocket)

    try:
        # 首次连接时推送当前状态
        await manager.push_task_status(task_id)

        while True:
            # 等待客户端消息
            data = await websocket.receive_text()

            # 处理客户端请求
            try:
                message = json.loads(data)
                action = message.get("action")

                if action == "get_status":
                    # 返回任务状态
                    await manager.push_task_status(task_id)

                elif action == "cancel":
                    # 取消任务
                    from backend.app.services.task_manager import TaskManager
                    from celery.result import AsyncResult
                    from backend.app.tasks import celery_app

                    task_manager = TaskManager()

                    # 尝试取消 Celery 任务
                    result = AsyncResult(task_id, app=celery_app)
                    result.revoke(terminate=True)

                    # 更新状态
                    task_manager.update_task_status(
                        task_id,
                        status="cancelled",
                        message="任务已取消"
                    )

                    await manager.send_progress(task_id, {
                        "event": "task_cancelled",
                        "data": {"task_id": task_id, "status": "cancelled"}
                    })

            except json.JSONDecodeError:
                await manager.send_progress(task_id, {
                    "event": "error",
                    "message": "Invalid JSON"
                })

    except WebSocketDisconnect:
        manager.disconnect(task_id)


@router.websocket("/ws/user/{user_id}")
async def user_notifications_ws(websocket: WebSocket, user_id: int):
    """
    WebSocket 用户通知推送

    - **user_id**: 用户 ID
    """
    task_id = f"user_{user_id}_{id(websocket)}"
    await manager.connect(task_id, websocket, user_id)

    try:
        while True:
            # 保持连接，定期推送用户任务状态
            from backend.app.services.task_manager import TaskManager
            task_manager = TaskManager()

            # 获取用户活跃任务
            user_tasks = task_manager.get_user_tasks(user_id)
            active_tasks = [t for t in user_tasks if t.get('status') in ['pending', 'processing']]

            if active_tasks:
                await manager.send_progress(task_id, {
                    "event": "user_tasks_update",
                    "data": {
                        "user_id": user_id,
                        "active_tasks": active_tasks,
                        "count": len(active_tasks)
                    }
                })

            await asyncio.sleep(5)  # 每5秒推送一次

    except WebSocketDisconnect:
        manager.disconnect(task_id, user_id)


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket):
    """
    WebSocket 系统通知推送
    """
    await websocket.accept()

    try:
        while True:
            # 保持连接，等待系统通知
            await asyncio.sleep(10)

    except WebSocketDisconnect:
        pass