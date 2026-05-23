# -*- coding: utf-8 -*-
"""
Celery 任务队列配置

使用 Redis 作为 Broker 和 Backend。
"""

from celery import Celery
from backend.app.core.config import settings

# 创建 Celery 应用实例
celery_app = Celery(
    "scipdf_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery 配置
celery_app.conf.update(
    # 序列化配置
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # 时区配置
    timezone="Asia/Shanghai",
    enable_utc=True,

    # 任务追踪
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    task_soft_time_limit=3300,  # 55分钟软超时

    # 结果配置
    result_expires=3600,  # 结果保留1小时

    # 任务路由
    task_routes={
        "backend.app.tasks.pdf_tasks.*": {"queue": "pdf"},
        "backend.app.tasks.ner_tasks.*": {"queue": "ner"},
        "backend.app.tasks.re_tasks.*": {"queue": "re"},
        "backend.app.tasks.batch_tasks.*": {"queue": "batch"},
        "backend.app.tasks.scheduled_tasks.*": {"queue": "scheduled"},
    },

    # 默认队列
    task_default_queue="default",

    # 并发配置
    worker_prefetch_multiplier=1,
    worker_concurrency=4,

    # 任务优先级
    task_queue_max_priority=10,
)

# 自动发现任务模块
celery_app.autodiscover_tasks([
    "backend.app.tasks.pdf_tasks",
    "backend.app.tasks.ner_tasks",
    "backend.app.tasks.re_tasks",
    "backend.app.tasks.batch_tasks",
    "backend.app.tasks.scheduled_tasks",
])


__all__ = ["celery_app"]