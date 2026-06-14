"""
异步任务引擎核心模块

基于 Redis Stream 的通用异步任务引擎，提供持久化、重试、取消、进度追踪等能力。
"""
from backend.app.core.tasks.engine import (
    AsyncTaskDefinition,
    AsyncTaskEngine,
    TaskEngineConfig,
    TaskHandler,
    TaskHandlerFailure,
    TaskHandlerRegistry,
    default_async_task_engine,
    default_task_handler_registry,
)
from backend.app.core.tasks.constants import ASYNC_TASKS_ATTRIBUTE

__all__ = [
    "ASYNC_TASKS_ATTRIBUTE",
    "AsyncTaskDefinition",
    "AsyncTaskEngine",
    "TaskEngineConfig",
    "TaskHandler",
    "TaskHandlerFailure",
    "TaskHandlerRegistry",
    "default_async_task_engine",
    "default_task_handler_registry",
]
