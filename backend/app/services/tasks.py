"""
异步任务服务层 — SQLAlchemy 版本

基于 case_one 的 SQLModel 服务层适配 SciPDF 项目的 SQLAlchemy 声明式模型，主要改动：
1. 导入路径：app.models.tasks → backend.app.models.tasks
2. SQLModel session.exec() → SQLAlchemy session.execute() + .scalars()
3. sqlmodel.col() → 直接使用 Column 属性（如 TaskItem.job_id.in_(...)）
4. utc_now → _utc_now（来自 backend.app.models.tasks）
5. 移除 disabled_at 相关逻辑（SciPDF 模型不含软删除字段）
6. completed_at → finished_at（与 SciPDF 模型字段名保持一致）
7. payload/result 为 JSON 类型，SQLAlchemy 自动序列化，无需手动 _dump_json/_load_json
8. TaskDeadLetter 字段适配（original_item_public_id、无 queue_name/result/updated_at）
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.tasks import TaskDeadLetter, TaskItem, TaskJob, TaskStatus, _utc_now
from backend.app.schemas.tasks import (
    TaskDeadLetterRead,
    TaskItemCreate,
    TaskItemRead,
    TaskJobCreate,
    TaskJobDetail,
    TaskJobPage,
    TaskJobRead,
    TaskStatusUpdate,
)


TERMINAL_STATUSES = {
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
    TaskStatus.PARTIAL,
}
JOB_TERMINAL_STATUSES = TERMINAL_STATUSES
RUNNABLE_ITEM_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
}
CANCELLABLE_ITEM_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
    TaskStatus.PAUSED,
}
PAUSABLE_ITEM_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.QUEUED,
}
RESUMABLE_ITEM_STATUSES = {
    TaskStatus.PAUSED,
}
RETRYABLE_ITEM_STATUSES = {
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
}


class TaskServiceError(Exception):
    """异步任务服务层基础异常。"""


class TaskJobNotFoundError(TaskServiceError):
    """异步任务不存在。"""


class TaskItemNotFoundError(TaskServiceError):
    """异步任务子项不存在。"""


class TaskValidationError(TaskServiceError):
    """异步任务请求不合法。"""


async def create_task_job(session: AsyncSession, payload: TaskJobCreate) -> TaskJobDetail:
    """创建异步任务及初始子项。"""
    now = _utc_now()
    job = TaskJob(
        task_type=payload.task_type.strip(),
        queue_name=payload.queue_name.strip() or "default",
        status=TaskStatus.PENDING,
        created_by=payload.created_by.strip(),
        project_public_id=payload.project_public_id.strip(),
        priority=payload.priority,
        total_items=len(payload.items),
        payload=payload.payload,
        scheduled_at=payload.scheduled_at,
    )
    session.add(job)
    await session.flush()
    if job.id is None:
        raise TaskValidationError("任务创建失败")

    items = [_build_task_item(job, item_payload, now) for item_payload in payload.items]
    if items:
        session.add_all(items)

    await _commit_and_refresh_task_models(session, job, items)
    return _to_job_detail(job, items)


async def append_task_items(
    session: AsyncSession,
    job_public_id: str,
    payloads: list[TaskItemCreate],
) -> TaskJobDetail:
    """追加异步任务子项。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    now = _utc_now()
    items = [_build_task_item(job, item_payload, now) for item_payload in payloads]
    if items:
        session.add_all(items)
        job.total_items += len(items)
        job.updated_at = now
        session.add(job)
    await _commit_and_refresh_task_models(session, job, items)
    return _to_job_detail(job, await _list_task_item_models(session, job.id or 0))


async def list_task_jobs(
    session: AsyncSession,
    *,
    page: int = 1,
    limit: int = 20,
    task_type: str = "",
    status: TaskStatus | None = None,
    created_by: str = "",
    queue_name: str = "",
    project_public_id: str = "",
) -> TaskJobPage:
    """分页查询异步任务列表。"""
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    conditions: list[Any] = []
    if status is not None:
        conditions.append(TaskJob.status == status)
    if project_public_id:
        conditions.append(TaskJob.project_public_id == project_public_id.strip())
    for value, column in (
        (task_type, TaskJob.task_type),
        (created_by, TaskJob.created_by),
        (queue_name, TaskJob.queue_name),
    ):
        if value:
            conditions.append(column == value.strip())

    count_statement = select(func.count()).select_from(TaskJob).where(*conditions)
    count_result = await session.execute(count_statement)
    total = int(count_result.scalar() or 0)

    statement = (
        select(TaskJob)
        .where(*conditions)
        .order_by(TaskJob.created_at.desc(), TaskJob.id.desc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    result = await session.execute(statement)
    jobs = list(result.scalars().all())
    return TaskJobPage(
        data=await _to_job_reads_with_item_counts(session, jobs),
        total=total,
        page=page,
        limit=limit,
    )


async def get_task_job(
    session: AsyncSession,
    job_public_id: str,
    *,
    include_items: bool = False,
) -> TaskJobRead | TaskJobDetail:
    """按公开标识获取异步任务。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    items = await _list_task_item_models(session, job.id or 0)
    if not include_items:
        return _to_job_read(job, items)
    return _to_job_detail(job, items)


async def list_task_items(
    session: AsyncSession,
    job_public_id: str,
    *,
    status: TaskStatus | None = None,
) -> list[TaskItemRead]:
    """查询异步任务子项列表。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    return [
        _to_item_read(item)
        for item in await _list_task_item_models(session, job.id or 0, status=status)
    ]


async def get_task_item(session: AsyncSession, item_public_id: str) -> TaskItemRead:
    """按公开标识获取异步任务子项。"""
    return _to_item_read(await _get_task_item_model_or_raise(session, item_public_id))


async def update_task_job_status(
    session: AsyncSession,
    job_public_id: str,
    payload: TaskStatusUpdate,
) -> TaskJobRead:
    """更新异步任务状态。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    _apply_status_update(job, payload)
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return _to_job_read(job, await _list_task_item_models(session, int(job.id or 0)))


async def update_task_item_status(
    session: AsyncSession,
    item_public_id: str,
    payload: TaskStatusUpdate,
    *,
    refresh_job: bool = True,
) -> TaskItemRead:
    """更新异步任务子项状态，并按需刷新父任务进度。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    _apply_status_update(item, payload)
    if payload.worker_id is not None:
        item.worker_id = payload.worker_id.strip()
    session.add(item)
    if refresh_job:
        job = await _get_task_job_model_by_id_or_raise(session, item.job_id)
        await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return _to_item_read(item)


async def mark_task_item_running(
    session: AsyncSession,
    item_public_id: str,
    worker_id: str,
) -> bool:
    """通过条件更新抢占任务子项，避免多个 Worker 重复执行。"""
    now = _utc_now()
    statement = (
        update(TaskItem)
        .where(
            TaskItem.public_id == item_public_id,
            TaskItem.status.in_(tuple(RUNNABLE_ITEM_STATUSES)),
            or_(TaskItem.scheduled_at.is_(None), TaskItem.scheduled_at <= now),
            TaskItem.attempt_count < TaskItem.max_attempts,
        )
        .values(
            status=TaskStatus.RUNNING,
            worker_id=worker_id.strip(),
            attempt_count=TaskItem.attempt_count + 1,
            started_at=now,
            heartbeat_at=now,
            finished_at=None,
            updated_at=now,
        )
    )
    result = await session.execute(statement)
    if int(result.rowcount or 0) != 1:
        await session.rollback()
        return False

    item = await _get_task_item_model_or_raise(session, item_public_id)
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return True


async def heartbeat_task_item(
    session: AsyncSession,
    item_public_id: str,
    worker_id: str,
) -> bool:
    """刷新运行中任务子项心跳。"""
    now = _utc_now()
    statement = (
        update(TaskItem)
        .where(
            TaskItem.public_id == item_public_id,
            TaskItem.status == TaskStatus.RUNNING,
            TaskItem.worker_id == worker_id.strip(),
        )
        .values(heartbeat_at=now, updated_at=now)
    )
    result = await session.execute(statement)
    if int(result.rowcount or 0) != 1:
        await session.rollback()
        return False
    await session.commit()
    return True


async def record_task_item_failure(
    session: AsyncSession,
    item_public_id: str,
    error_code: str,
    error_message: str,
    worker_id: str,
    *,
    retry_backoff_seconds: float = 30.0,
    stream_id: str = "",
    stage: str = "handler",
    result: dict[str, Any] | None = None,
) -> TaskItemRead:
    """记录任务子项失败；未达最大次数时按指数退避重新排队，超限后进入 DLQ。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)
    now = _utc_now()
    item.error_code = error_code.strip()
    item.error_message = error_message.strip()
    item.worker_id = worker_id.strip()
    item.heartbeat_at = None
    item.updated_at = now
    if result is not None:
        item.result = result

    if item.attempt_count < item.max_attempts:
        # 未超最大重试次数 → 按指数退避重新排队
        item.status = TaskStatus.PENDING
        item.started_at = None
        item.finished_at = None
        item.scheduled_at = now + _retry_delay(item.attempt_count, retry_backoff_seconds)
        session.add(item)
    else:
        # 超过最大重试次数 → 标记失败并写入死信
        item.status = TaskStatus.FAILED
        item.finished_at = now
        session.add(item)
        session.add(
            _build_dead_letter(
                job,
                item,
                stream_id=stream_id,
                stage=stage,
                worker_id=worker_id,
                error_code=error_code,
                error_message=error_message,
            )
        )

    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return _to_item_read(item)


async def pause_task_job(session: AsyncSession, job_public_id: str) -> TaskJobRead:
    """暂停任务下尚未开始执行的子项。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if job.status in JOB_TERMINAL_STATUSES:
        raise TaskValidationError("已结束的任务不能暂停")
    items = await _list_task_item_models(session, int(job.id or 0))
    now = _utc_now()
    for item in items:
        if item.status not in PAUSABLE_ITEM_STATUSES:
            continue
        item.status = TaskStatus.PAUSED
        item.worker_id = ""
        item.updated_at = now
        session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(job)
    return _to_job_read(job, await _list_task_item_models(session, int(job.id or 0)))


async def pause_task_items(
    session: AsyncSession,
    job_public_id: str,
    item_public_ids: set[str],
) -> TaskJobRead:
    """暂停任务下指定的尚未开始执行子项。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if job.status in JOB_TERMINAL_STATUSES:
        raise TaskValidationError("已结束的任务不能暂停")
    target_ids = {value.strip() for value in item_public_ids if value and value.strip()}
    items = await _list_task_item_models(session, int(job.id or 0))
    now = _utc_now()
    for item in items:
        if item.public_id not in target_ids or item.status not in PAUSABLE_ITEM_STATUSES:
            continue
        item.status = TaskStatus.PAUSED
        item.worker_id = ""
        item.updated_at = now
        session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(job)
    return _to_job_read(job, await _list_task_item_models(session, int(job.id or 0)))


async def resume_task_job(session: AsyncSession, job_public_id: str) -> TaskJobRead:
    """恢复任务下已暂停的子项。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if job.status in JOB_TERMINAL_STATUSES:
        raise TaskValidationError("已结束的任务不能恢复")
    items = await _list_task_item_models(session, int(job.id or 0))
    now = _utc_now()
    for item in items:
        if item.status not in RESUMABLE_ITEM_STATUSES:
            continue
        item.status = TaskStatus.PENDING
        item.worker_id = ""
        item.updated_at = now
        session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(job)
    return _to_job_read(job, await _list_task_item_models(session, int(job.id or 0)))


async def resume_task_items(
    session: AsyncSession,
    job_public_id: str,
    item_public_ids: set[str],
) -> TaskJobRead:
    """恢复任务下指定的已暂停子项。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if job.status in JOB_TERMINAL_STATUSES:
        raise TaskValidationError("已结束的任务不能恢复")
    target_ids = {value.strip() for value in item_public_ids if value and value.strip()}
    items = await _list_task_item_models(session, int(job.id or 0))
    now = _utc_now()
    for item in items:
        if item.public_id not in target_ids or item.status not in RESUMABLE_ITEM_STATUSES:
            continue
        item.status = TaskStatus.PENDING
        item.worker_id = ""
        item.updated_at = now
        session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(job)
    return _to_job_read(job, await _list_task_item_models(session, int(job.id or 0)))


async def cancel_task_job(session: AsyncSession, job_public_id: str) -> TaskJobRead:
    """取消任务下尚未开始执行的子项；运行中的子项由 Worker 自然结束。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    items = await _list_task_item_models(session, int(job.id or 0))
    now = _utc_now()
    for item in items:
        if item.status not in CANCELLABLE_ITEM_STATUSES:
            continue
        item.status = TaskStatus.CANCELLED
        item.worker_id = ""
        item.error_code = "task_item_cancelled"
        item.error_message = "任务子项已取消"
        item.finished_at = now
        item.updated_at = now
        session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(job)
    return _to_job_read(job, await _list_task_item_models(session, int(job.id or 0)))


async def delete_task_job(session: AsyncSession, job_public_id: str) -> None:
    """硬删除异步任务及其子项（级联删除）。"""
    job = await _get_task_job_model_or_raise(session, job_public_id)
    if job.id is None:
        raise TaskJobNotFoundError("异步任务不存在")
    await session.delete(job)
    await session.commit()


async def cancel_task_item(session: AsyncSession, item_public_id: str) -> TaskItemRead:
    """取消异步任务子项，并刷新父任务进度。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    if item.status not in CANCELLABLE_ITEM_STATUSES:
        raise TaskValidationError("只有待处理、已入队或已暂停的任务子项可以取消")
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)

    now = _utc_now()
    item.status = TaskStatus.CANCELLED
    item.worker_id = ""
    item.error_code = "task_item_cancelled"
    item.error_message = "任务子项已取消"
    item.finished_at = now
    item.updated_at = now
    session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return _to_item_read(item)


async def retry_task_item(session: AsyncSession, item_public_id: str) -> TaskItemRead:
    """将失败或已取消的异步任务子项重置为待处理。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    if item.status not in RETRYABLE_ITEM_STATUSES:
        raise TaskValidationError("只有失败或已取消的任务子项可以重试")
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)

    now = _utc_now()
    item.status = TaskStatus.PENDING
    item.worker_id = ""
    item.result = {}
    item.error_code = ""
    item.error_message = ""
    item.started_at = None
    item.heartbeat_at = None
    item.finished_at = None
    item.scheduled_at = None
    item.updated_at = now
    session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return _to_item_read(item)


async def delete_task_item(session: AsyncSession, item_public_id: str) -> None:
    """硬删除异步任务子项，并刷新父任务进度。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)

    await session.delete(item)
    await refresh_task_job_progress(session, job)
    await session.commit()


async def list_due_pending_task_item_public_ids(
    session: AsyncSession,
    *,
    limit: int = 100,
) -> list[str]:
    """列出已到调度时间的 pending 任务子项，用于孤儿恢复和重试调度。"""
    now = _utc_now()
    statement = (
        select(TaskItem.public_id)
        .where(
            TaskItem.status == TaskStatus.PENDING,
            or_(TaskItem.scheduled_at.is_(None), TaskItem.scheduled_at <= now),
        )
        .order_by(TaskItem.priority.desc(), TaskItem.scheduled_at, TaskItem.id)
        .limit(max(limit, 1))
    )
    result = await session.execute(statement)
    return [str(public_id) for public_id in result.scalars().all()]


async def recover_queued_task_item_to_pending(session: AsyncSession, item_public_id: str) -> bool:
    """将长时间滞留在 Redis PEL 中的 queued 子项恢复为 pending。"""
    item = await _get_task_item_model_or_raise(session, item_public_id)
    if item.status != TaskStatus.QUEUED:
        return False
    job = await _get_task_job_model_by_id_or_raise(session, item.job_id)
    now = _utc_now()
    item.status = TaskStatus.PENDING
    item.worker_id = ""
    item.updated_at = now
    session.add(item)
    await refresh_task_job_progress(session, job)
    await session.commit()
    await session.refresh(item)
    return True


async def recover_stale_running_task_items(
    session: AsyncSession,
    *,
    stale_after_seconds: float,
    retry_backoff_seconds: float,
    limit: int = 100,
) -> int:
    """恢复心跳超时的 running 子项，未超最大次数则重试，超限则进入 DLQ。"""
    cutoff = _utc_now() - timedelta(seconds=max(stale_after_seconds, 0))
    statement = (
        select(TaskItem.public_id)
        .where(
            TaskItem.status == TaskStatus.RUNNING,
            or_(TaskItem.heartbeat_at.is_(None), TaskItem.heartbeat_at <= cutoff),
        )
        .order_by(TaskItem.heartbeat_at, TaskItem.id)
        .limit(max(limit, 1))
    )
    result = await session.execute(statement)
    item_public_ids = [str(public_id) for public_id in result.scalars().all()]
    for item_public_id in item_public_ids:
        await record_task_item_failure(
            session,
            item_public_id,
            "task_running_stale",
            "任务心跳超时，已由 OrphanScavenger 恢复",
            "",
            retry_backoff_seconds=retry_backoff_seconds,
            stage="orphan_scavenger",
        )
    return len(item_public_ids)


async def create_task_dead_letter(
    session: AsyncSession,
    *,
    item_public_id: str = "",
    task_type: str = "",
    item_type: str = "",
    stream_id: str = "",
    stage: str,
    worker_id: str = "",
    attempt_count: int = 0,
    max_attempts: int = 0,
    error_code: str,
    error_message: str,
    payload: dict[str, Any] | None = None,
) -> TaskDeadLetterRead:
    """创建死信记录；用于任务超限失败以及写回失败兜底。"""
    item: TaskItem | None = None
    if item_public_id:
        item_result = await session.execute(
            select(TaskItem).where(TaskItem.public_id == item_public_id)
        )
        item = item_result.scalars().first()

    dead_letter = TaskDeadLetter(
        task_type=(item.task_type if item is not None else task_type).strip(),
        item_type=(item.item_type if item is not None else item_type).strip(),
        item_key=(item.item_key if item is not None else ""),
        payload=item.payload if item is not None else (payload or {}),
        error_code=error_code.strip(),
        error_message=error_message.strip(),
        attempt_count=item.attempt_count if item is not None else attempt_count,
        max_attempts=item.max_attempts if item is not None else max_attempts,
        original_item_public_id=item.public_id if item is not None else item_public_id.strip(),
        worker_id=worker_id.strip(),
        stream_id=stream_id.strip(),
    )
    session.add(dead_letter)
    await session.commit()
    await session.refresh(dead_letter)
    return _to_dead_letter_read(dead_letter)


async def refresh_task_job_progress(session: AsyncSession, job: TaskJob) -> TaskJob:
    """重新统计任务子项进度，并推导父任务状态。"""
    if job.id is None:
        raise TaskValidationError("任务内部主键不能为空")

    statement = (
        select(TaskItem.status, func.count())
        .where(TaskItem.job_id == job.id)
        .group_by(TaskItem.status)
    )
    result = await session.execute(statement)
    counts = Counter({status: int(count) for status, count in result.all()})
    total = sum(counts.values())
    succeeded = counts[TaskStatus.SUCCEEDED]
    failed = counts[TaskStatus.FAILED]
    cancelled = counts[TaskStatus.CANCELLED]
    running = counts[TaskStatus.RUNNING]
    queued = counts[TaskStatus.QUEUED]
    pending = counts[TaskStatus.PENDING]
    paused = counts[TaskStatus.PAUSED]

    now = _utc_now()
    job.total_items = total
    job.completed_items = succeeded
    job.failed_items = failed

    terminal_count = succeeded + failed + cancelled
    if total == 0:
        job.status = TaskStatus.PENDING
        job.finished_at = None
    elif terminal_count == total:
        if failed and succeeded:
            job.status = TaskStatus.PARTIAL
        elif failed:
            job.status = TaskStatus.FAILED
        elif cancelled and not succeeded:
            job.status = TaskStatus.CANCELLED
        else:
            job.status = TaskStatus.SUCCEEDED
        job.finished_at = job.finished_at or now
    elif running:
        job.status = TaskStatus.RUNNING
        job.started_at = job.started_at or now
        job.finished_at = None
    elif queued:
        job.status = TaskStatus.QUEUED
        job.finished_at = None
    elif pending:
        job.status = TaskStatus.PENDING
        job.finished_at = None
    elif paused:
        job.status = TaskStatus.PAUSED
        job.finished_at = None

    job.updated_at = now
    session.add(job)
    return job


# ── 内部辅助函数 ──


async def _get_task_job_model_or_raise(session: AsyncSession, job_public_id: str) -> TaskJob:
    """按 public_id 查找 TaskJob，不存在则抛异常。"""
    statement = select(TaskJob).where(TaskJob.public_id == job_public_id)
    return await _first_or_raise(session, statement, TaskJobNotFoundError("异步任务不存在"))


async def _get_task_job_model_by_id_or_raise(session: AsyncSession, job_id: int) -> TaskJob:
    """按内部主键查找 TaskJob，不存在则抛异常。"""
    statement = select(TaskJob).where(TaskJob.id == job_id)
    return await _first_or_raise(session, statement, TaskJobNotFoundError("异步任务不存在"))


async def _get_task_item_model_or_raise(session: AsyncSession, item_public_id: str) -> TaskItem:
    """按 public_id 查找 TaskItem，不存在则抛异常。"""
    statement = select(TaskItem).where(TaskItem.public_id == item_public_id)
    return await _first_or_raise(session, statement, TaskItemNotFoundError("异步任务子项不存在"))


async def _list_task_item_models(
    session: AsyncSession,
    job_id: int,
    *,
    status: TaskStatus | None = None,
) -> list[TaskItem]:
    """列出指定任务的子项，可按状态过滤。"""
    conditions: list[Any] = [TaskItem.job_id == job_id]
    if status is not None:
        conditions.append(TaskItem.status == status)
    statement = select(TaskItem).where(*conditions).order_by(TaskItem.priority.desc(), TaskItem.id)
    result = await session.execute(statement)
    return list(result.scalars().all())


async def _list_task_item_models_by_job_ids(
    session: AsyncSession,
    job_ids: list[int],
) -> dict[int, list[TaskItem]]:
    """按任务内部主键批量读取子项。"""
    if not job_ids:
        return {}
    statement = (
        select(TaskItem)
        .where(TaskItem.job_id.in_(job_ids))
        .order_by(TaskItem.priority.desc(), TaskItem.id)
    )
    result = await session.execute(statement)
    items_by_job_id: dict[int, list[TaskItem]] = {}
    for item in result.scalars().all():
        items_by_job_id.setdefault(item.job_id, []).append(item)
    return items_by_job_id


async def _to_job_reads_with_item_counts(
    session: AsyncSession,
    jobs: list[TaskJob],
) -> list[TaskJobRead]:
    """批量转换任务响应，并附带准确的子项状态计数。"""
    items_by_job_id = await _list_task_item_models_by_job_ids(
        session,
        [int(job.id or 0) for job in jobs if job.id is not None],
    )
    return [_to_job_read(job, items_by_job_id.get(int(job.id or 0), [])) for job in jobs]


def _build_task_item(job: TaskJob, payload: TaskItemCreate, now: datetime) -> TaskItem:
    """从 Schema 构建 TaskItem 模型实例。"""
    item_type = payload.item_type.strip() or job.task_type
    return TaskItem(
        job_id=int(job.id or 0),
        task_type=job.task_type,
        item_type=item_type,
        item_key=payload.item_key.strip() if payload.item_key else "",
        status=TaskStatus.PENDING,
        priority=payload.priority,
        max_attempts=payload.max_attempts,
        payload=payload.payload,
        scheduled_at=payload.scheduled_at or job.scheduled_at,
    )


def _build_dead_letter(
    job: TaskJob,
    item: TaskItem,
    *,
    stream_id: str,
    stage: str,
    worker_id: str,
    error_code: str,
    error_message: str,
) -> TaskDeadLetter:
    """从任务和子项构建死信记录。"""
    return TaskDeadLetter(
        task_type=job.task_type,
        item_type=item.item_type,
        item_key=item.item_key or "",
        payload=item.payload,
        error_code=error_code.strip(),
        error_message=error_message.strip(),
        attempt_count=item.attempt_count,
        max_attempts=item.max_attempts,
        original_item_public_id=item.public_id,
        worker_id=worker_id.strip(),
        stream_id=stream_id.strip(),
    )


async def _commit_and_refresh_task_models(
    session: AsyncSession,
    job: TaskJob,
    items: list[TaskItem],
) -> None:
    """提交事务并刷新所有模型实例。"""
    await session.commit()
    await session.refresh(job)
    for item in items:
        await session.refresh(item)


async def _first_or_raise(session: AsyncSession, statement: Any, exc: Exception) -> Any:
    """执行查询并返回第一条记录，无结果则抛异常。"""
    result = await session.execute(statement)
    value = result.scalars().first()
    if value is None:
        raise exc
    return value


def _apply_status_update(target: TaskJob | TaskItem, payload: TaskStatusUpdate) -> None:
    """将状态更新应用到 TaskJob 或 TaskItem。"""
    now = _utc_now()
    target.status = payload.status
    if payload.result is not None:
        target.result = payload.result
    target.error_code = payload.error_code.strip()
    target.error_message = payload.error_message.strip()
    if payload.status == TaskStatus.RUNNING:
        target.started_at = target.started_at or now
        if isinstance(target, TaskItem):
            target.attempt_count += 1
            target.heartbeat_at = now
        target.finished_at = None
    if payload.status in TERMINAL_STATUSES:
        target.finished_at = target.finished_at or now
    target.updated_at = now


def _retry_delay(attempt_count: int, retry_backoff_seconds: float) -> timedelta:
    """计算指数退避延迟。"""
    multiplier = 2 ** max(attempt_count - 1, 0)
    return timedelta(seconds=max(retry_backoff_seconds, 0) * multiplier)


# ── Schema 转换函数 ──


def _read_schema_values(model: Any) -> dict[str, Any]:
    """将 SQLAlchemy 模型转为 Schema 构造参数字典。

    SciPDF 的 payload/result 为 JSON 列，SQLAlchemy 自动反序列化为 dict，
    因此无需手动解析。
    """
    values = model.model_dump() if hasattr(model, "model_dump") else {
        c.name: getattr(model, c.name) for c in model.__table__.columns
    }
    values["id"] = int(model.id or 0)
    return values


def _to_job_read(job: TaskJob, items: list[TaskItem] | None = None) -> TaskJobRead:
    """将 TaskJob 模型转为 TaskJobRead。"""
    values = _read_schema_values(job)
    values.update(_item_status_count_values(items or []))
    return TaskJobRead(**values)


def _to_job_detail(job: TaskJob, items: list[TaskItem]) -> TaskJobDetail:
    """将 TaskJob 模型及子项转为 TaskJobDetail。"""
    return TaskJobDetail(
        **_to_job_read(job, items).model_dump(),
        items=[_to_item_read(item) for item in items],
    )


def _to_item_read(item: TaskItem) -> TaskItemRead:
    """将 TaskItem 模型转为 TaskItemRead。"""
    return TaskItemRead(**_read_schema_values(item))


def _to_dead_letter_read(dead_letter: TaskDeadLetter) -> TaskDeadLetterRead:
    """将 TaskDeadLetter 模型转为 TaskDeadLetterRead。"""
    return TaskDeadLetterRead(**_read_schema_values(dead_letter))


def _item_status_count_values(items: list[TaskItem]) -> dict[str, int]:
    """统计子项各状态数量，用于 TaskJobRead 的冗余计数字段。"""
    counts = Counter(item.status for item in items)
    return {
        "pending_items": counts[TaskStatus.PENDING],
        "queued_items": counts[TaskStatus.QUEUED],
        "running_items": counts[TaskStatus.RUNNING],
        "paused_items": counts[TaskStatus.PAUSED],
    }
