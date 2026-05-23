# -*- coding: utf-8 -*-
"""
定时任务（Celery Beat）

定期执行的清理、维护任务。
"""

import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any
from loguru import logger

from backend.app.tasks import celery_app
from backend.app.core.config import settings, UPLOADS_DIR, RESULTS_DIR, NER_RESULTS_DIR, RE_RESULTS_DIR, FAILED_LOGS_DIR


@celery_app.task
def cleanup_temp_files() -> Dict[str, Any]:
    """
    清理临时文件

    删除超过 24 小时的上传文件
    """
    logger.info("开始清理临时文件")

    cleaned_count = 0
    cleaned_size = 0

    # 清理上传目录
    if UPLOADS_DIR.exists():
        for file in UPLOADS_DIR.iterdir():
            if file.is_file():
                # 检查文件修改时间
                mtime = datetime.fromtimestamp(file.stat().st_mtime)
                if datetime.now() - mtime > timedelta(hours=24):
                    file_size = file.stat().st_size
                    file.unlink()
                    cleaned_count += 1
                    cleaned_size += file_size
                    logger.debug(f"删除临时文件: {file.name}")

    logger.info(f"临时文件清理完成: 删除 {cleaned_count} 个文件，释放 {cleaned_size / 1024:.2f} KB")

    return {
        "status": "completed",
        "cleaned_count": cleaned_count,
        "cleaned_size": cleaned_size
    }


@celery_app.task
def cleanup_old_results() -> Dict[str, Any]:
    """
    清理旧结果文件

    删除超过 7 天的结果文件
    """
    logger.info("开始清理旧结果文件")

    cleaned_count = 0
    cleaned_size = 0

    dirs_to_clean = [RESULTS_DIR, NER_RESULTS_DIR, RE_RESULTS_DIR, FAILED_LOGS_DIR]

    for dir_path in dirs_to_clean:
        if dir_path.exists():
            for file in dir_path.iterdir():
                if file.is_file():
                    mtime = datetime.fromtimestamp(file.stat().st_mtime)
                    if datetime.now() - mtime > timedelta(days=7):
                        file_size = file.stat().st_size
                        file.unlink()
                        cleaned_count += 1
                        cleaned_size += file_size

    logger.info(f"旧结果文件清理完成: 删除 {cleaned_count} 个文件，释放 {cleaned_size / 1024:.2f} KB")

    return {
        "status": "completed",
        "cleaned_count": cleaned_count,
        "cleaned_size": cleaned_size
    }


@celery_app.task
def cleanup_expired_tasks() -> Dict[str, Any]:
    """
    清理过期任务记录

    从 Redis 清理超过 24 小时的已完成任务
    """
    logger.info("开始清理过期任务记录")

    from backend.app.services.task_manager import TaskManager
    task_manager = TaskManager()

    cleaned = task_manager.cleanup_expired_tasks()

    logger.info(f"过期任务清理完成: 删除 {cleaned} 个任务记录")

    return {
        "status": "completed",
        "cleaned_count": cleaned
    }


@celery_app.task
def cleanup_failed_logs() -> Dict[str, Any]:
    """
    清理失败日志

    删除超过 30 天的失败日志
    """
    logger.info("开始清理失败日志")

    cleaned_count = 0

    if FAILED_LOGS_DIR.exists():
        for file in FAILED_LOGS_DIR.iterdir():
            if file.is_file():
                mtime = datetime.fromtimestamp(file.stat().st_mtime)
                if datetime.now() - mtime > timedelta(days=30):
                    file.unlink()
                    cleaned_count += 1

    logger.info(f"失败日志清理完成: 删除 {cleaned_count} 个文件")

    return {
        "status": "completed",
        "cleaned_count": cleaned_count
    }


@celery_app.task
def health_check() -> Dict[str, Any]:
    """
    系统健康检查

    检查各服务状态
    """
    logger.info("执行系统健康检查")

    checks = {
        "redis": False,
        "database": False,
        "milvus": False,
        "storage": False
    }

    # 检查 Redis
    try:
        import redis
        client = redis.from_url(settings.REDIS_URL)
        client.ping()
        checks["redis"] = True
    except Exception as e:
        logger.warning(f"Redis 检查失败: {e}")

    # 检查数据库
    try:
        from backend.app.models.base import engine
        import asyncio

        async def _check():
            async with engine.connect() as conn:
                await conn.execute("SELECT 1")

        asyncio.run(_check())
        checks["database"] = True
    except Exception as e:
        logger.warning(f"数据库检查失败: {e}")

    # 检查 Milvus
    try:
        from pymilvus import MilvusClient
        client = MilvusClient(uri=settings.MILVUS_URI)
        # 尝试列出数据库
        client.list_databases()
        checks["milvus"] = True
    except Exception as e:
        logger.warning(f"Milvus 检查失败: {e}")

    # 检查存储目录
    try:
        if UPLOADS_DIR.exists() and RESULTS_DIR.exists():
            checks["storage"] = True
    except Exception as e:
        logger.warning(f"存储检查失败: {e}")

    all_healthy = all(checks.values())

    status = "healthy" if all_healthy else "degraded"

    logger.info(f"健康检查完成: {status}, 详情: {checks}")

    return {
        "status": status,
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }


@celery_app.task
def generate_statistics() -> Dict[str, Any]:
    """
    生成系统统计报告

    统计处理数量、存储使用等
    """
    logger.info("生成系统统计报告")

    stats = {
        "papers": 0,
        "ner_results": 0,
        "re_results": 0,
        "storage_used_mb": 0,
        "tasks_active": 0
    }

    try:
        from backend.app.models.base import AsyncSessionLocal
        from backend.app.models import ProcessingResult, NERResult, REResult
        from sqlalchemy import select, func
        import asyncio

        async def _count():
            async with AsyncSessionLocal() as db:
                # 统计论文
                result = await db.execute(select(func.count(ProcessingResult.id)))
                stats["papers"] = result.scalar() or 0

                # 统计 NER
                result = await db.execute(select(func.count(NERResult.id)))
                stats["ner_results"] = result.scalar() or 0

                # 统计 RE
                result = await db.execute(select(func.count(REResult.id)))
                stats["re_results"] = result.scalar() or 0

        asyncio.run(_count())

    except Exception as e:
        logger.warning(f"数据库统计失败: {e}")

    # 统计存储使用
    try:
        total_size = 0
        for dir_path in [UPLOADS_DIR, RESULTS_DIR, NER_RESULTS_DIR, RE_RESULTS_DIR]:
            if dir_path.exists():
                for file in dir_path.iterdir():
                    if file.is_file():
                        total_size += file.stat().st_size
        stats["storage_used_mb"] = total_size / (1024 * 1024)
    except Exception as e:
        logger.warning(f"存储统计失败: {e}")

    # 统计活跃任务
    try:
        from backend.app.services.task_manager import TaskManager
        task_manager = TaskManager()
        active_tasks = task_manager.get_active_tasks()
        stats["tasks_active"] = len(active_tasks)
    except Exception as e:
        logger.warning(f"任务统计失败: {e}")

    logger.info(f"统计报告生成完成: {stats}")

    return {
        "status": "completed",
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }


# Celery Beat 配置
celery_app.conf.beat_schedule = {
    # 每小时清理临时文件
    'cleanup-temp-files-every-hour': {
        'task': 'backend.app.tasks.scheduled_tasks.cleanup_temp_files',
        'schedule': 3600.0,  # 1小时
    },
    # 每天凌晨清理旧结果
    'cleanup-old-results-daily': {
        'task': 'backend.app.tasks.scheduled_tasks.cleanup_old_results',
        'schedule': 86400.0,  # 24小时
        'options': {'queue': 'scheduled'},
    },
    # 每小时清理过期任务
    'cleanup-expired-tasks-every-hour': {
        'task': 'backend.app.tasks.scheduled_tasks.cleanup_expired_tasks',
        'schedule': 3600.0,
    },
    # 每 5 分钟健康检查
    'health-check-every-5-min': {
        'task': 'backend.app.tasks.scheduled_tasks.health_check',
        'schedule': 300.0,
    },
    # 每小时生成统计
    'generate-statistics-every-hour': {
        'task': 'backend.app.tasks.scheduled_tasks.generate_statistics',
        'schedule': 3600.0,
    },
}