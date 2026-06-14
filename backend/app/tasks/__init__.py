# -*- coding: utf-8 -*-
"""
异步任务注册入口

导出各业务模块的 ASYNC_TASKS 供任务引擎自动发现注册。
同时保留 celery_app 导出，供过渡期内旧 Celery 任务文件继续使用。
"""
from backend.app.tasks.pdf import ASYNC_TASKS as PDF_TASKS
from backend.app.tasks.ner import ASYNC_TASKS as NER_TASKS
from backend.app.tasks.re import ASYNC_TASKS as RE_TASKS
from backend.app.tasks.pipeline import ASYNC_TASKS as PIPELINE_TASKS
from backend.app.tasks.domain import ASYNC_TASKS as DOMAIN_TASKS

ALL_ASYNC_TASKS = PDF_TASKS + NER_TASKS + RE_TASKS + PIPELINE_TASKS + DOMAIN_TASKS

# ──────────────────────────────────────────────────────────────
# 过渡期兼容：旧 Celery 任务文件仍依赖 celery_app
# 待所有任务迁移到新引擎后可删除以下代码
# ──────────────────────────────────────────────────────────────
from celery import Celery
from backend.app.core.config import settings

celery_app = Celery(
    "scipdf_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3300,
    result_expires=3600,
    task_routes={
        "backend.app.tasks.pdf_tasks.*": {"queue": "pdf"},
        "backend.app.tasks.ner_tasks.*": {"queue": "ner"},
        "backend.app.tasks.re_tasks.*": {"queue": "re"},
        "backend.app.tasks.batch_tasks.*": {"queue": "batch"},
        "backend.app.tasks.scheduled_tasks.*": {"queue": "scheduled"},
    },
    task_default_queue="default",
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
    task_queue_max_priority=10,
)

celery_app.autodiscover_tasks([
    "backend.app.tasks.pdf_tasks",
    "backend.app.tasks.ner_tasks",
    "backend.app.tasks.re_tasks",
    "backend.app.tasks.batch_tasks",
    "backend.app.tasks.scheduled_tasks",
])


__all__ = [
    "ALL_ASYNC_TASKS",
    "PDF_TASKS",
    "NER_TASKS",
    "RE_TASKS",
    "PIPELINE_TASKS",
    "DOMAIN_TASKS",
    "celery_app",
]
