"""
异步任务 API 路由

基于 case_one 的 TaskView / ProjectTaskView 适配 SciPDF 项目，主要改动：
1. 导入路径：app.core.database → backend.app.models.base（get_db）
2. 导入路径：app.core.tasks.engine → backend.app.core.tasks.engine
3. 导入路径：app.services → backend.app.services
4. 导入路径：app.schemas.tasks → backend.app.schemas.tasks
5. 认证方式：case_one 的 jwt_auth_middleware → get_current_user_required（backend.app.api.deps_user）
6. 依赖注入：get_session → get_db
7. 视图模式：case_one 的 BaseView + route 装饰器 → FastAPI 函数式路由
8. 移除 request_duration_middleware（SciPDF 无此中间件）
9. 移除 ProjectTaskView 中的项目权限校验（SciPDF 无 project_service）
10. 移除任务指标端点 /metrics 和 /metrics/timeseries（SciPDF 无 task_metrics 服务）
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.api.deps_user import get_current_user_required
from backend.app.core.tasks.engine import default_async_task_engine
from backend.app.models.base import get_db
from backend.app.models.tasks import TaskStatus
from backend.app.schemas.tasks import (
    TaskItemPage,
    TaskItemRead,
    TaskJobCancelRequest,
    TaskJobCancelResponse,
    TaskJobCreate,
    TaskJobDeleteResponse,
    TaskJobDetail,
    TaskJobPage,
    TaskJobPauseRequest,
    TaskJobPauseResponse,
    TaskJobRead,
    TaskJobResumeRequest,
    TaskJobResumeResponse,
    TaskJobRetryRequest,
    TaskJobRetryResponse,
)
from backend.app.services import tasks as task_service
from backend.app.services.tasks import (
    TaskItemNotFoundError,
    TaskJobNotFoundError,
    TaskServiceError,
    TaskValidationError,
)


# ── 依赖注入别名 ──

SessionDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Depends(get_current_user_required)

# ── 状态常量 ──

CANCELLABLE_ITEM_STATUSES = {TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.PAUSED}
PAUSABLE_ITEM_STATUSES = {TaskStatus.PENDING, TaskStatus.QUEUED}
RESUMABLE_ITEM_STATUSES = {TaskStatus.PAUSED}
RETRYABLE_ITEM_STATUSES = {TaskStatus.FAILED, TaskStatus.CANCELLED}


# ── 辅助函数 ──

def _target_item_ids(values: list[str] | None) -> set[str]:
    """规整前端传入的子项公开标识。"""
    return {value.strip() for value in values or [] if value and value.strip()}


@contextmanager
def _handle_task_errors():
    """将任务服务层异常转换为 HTTP 异常。"""
    try:
        yield
    except TaskJobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskItemNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except TaskValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except TaskServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _count_items(
    items: list[TaskItemRead],
    allowed_statuses: set[TaskStatus],
    target_item_ids: set[str] | None = None,
) -> int:
    """统计符合状态和目标范围的子项数量。"""
    return sum(
        1
        for item in items
        if item.status in allowed_statuses and (not target_item_ids or item.public_id in target_item_ids)
    )


def _filter_task_items_by_status(
    items: list[TaskItemRead],
    status_: TaskStatus | None,
) -> list[TaskItemRead]:
    """按前端展示语义筛选子项；排队中同时包含待处理和已入队。"""
    if status_ is None:
        return items
    allowed_statuses = {status_}
    if status_ == TaskStatus.PENDING:
        allowed_statuses.add(TaskStatus.QUEUED)
    return [item for item in items if item.status in allowed_statuses]


def _page_task_items(items: list[TaskItemRead], page: int, page_size: int) -> TaskItemPage:
    """对子项列表做内存分页，保持与任务底座查询结果一致。"""
    safe_page = max(page, 1)
    safe_page_size = min(max(page_size, 1), 100)
    start = (safe_page - 1) * safe_page_size
    return TaskItemPage(
        data=items[start : start + safe_page_size],
        total=len(items),
        page=safe_page,
        limit=safe_page_size,
    )


# ── 路由注册 ──

router = APIRouter(prefix="/api/v1/tasks", tags=["任务管理"])


# ══════════════════════════════════════════════════════════════
# 通用任务端点
# ══════════════════════════════════════════════════════════════


@router.post(
    "",
    response_model=TaskJobDetail,
    status_code=status.HTTP_201_CREATED,
    summary="添加单个异步任务",
    description="创建单个异步任务记录，不立即投递到执行队列。",
)
async def create_task(
    payload: TaskJobCreate,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobDetail:
    """添加单个异步任务。"""
    with _handle_task_errors():
        return await default_async_task_engine.create_task_job(session, payload)


@router.post(
    "/enqueue",
    response_model=TaskJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="添加并启动单个异步任务",
    description="创建单个异步任务记录，并立即投递可执行的任务子项。",
)
async def create_and_enqueue_task(
    payload: TaskJobCreate,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobDetail:
    """添加并启动单个异步任务。"""
    with _handle_task_errors():
        return await default_async_task_engine.create_and_enqueue_task_job(session, payload)


@router.post(
    "/batch",
    response_model=list[TaskJobDetail],
    status_code=status.HTTP_201_CREATED,
    summary="批量添加异步任务",
    description="批量创建异步任务记录，不立即投递到执行队列。",
)
async def create_tasks(
    payloads: list[TaskJobCreate],
    session: SessionDep,
    user=CurrentUser,
) -> list[TaskJobDetail]:
    """批量添加异步任务。"""
    with _handle_task_errors():
        jobs: list[TaskJobDetail] = []
        for payload in payloads:
            jobs.append(await default_async_task_engine.create_task_job(session, payload))
        return jobs


@router.post(
    "/batch/enqueue",
    response_model=list[TaskJobDetail],
    status_code=status.HTTP_202_ACCEPTED,
    summary="批量添加并启动异步任务",
    description="批量创建异步任务记录，并立即投递可执行的任务子项。",
)
async def create_and_enqueue_tasks(
    payloads: list[TaskJobCreate],
    session: SessionDep,
    user=CurrentUser,
) -> list[TaskJobDetail]:
    """批量添加并启动异步任务。"""
    with _handle_task_errors():
        jobs: list[TaskJobDetail] = []
        for payload in payloads:
            jobs.append(await default_async_task_engine.create_and_enqueue_task_job(session, payload))
        return jobs


@router.post(
    "/{job_public_id}/start",
    response_model=list[str],
    status_code=status.HTTP_202_ACCEPTED,
    summary="开启任务",
    description="将指定异步任务的可执行子项投递到任务队列。",
)
async def start_task(
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> list[str]:
    """开启指定异步任务。"""
    with _handle_task_errors():
        records = await default_async_task_engine.enqueue_task_job(session, job_public_id)
        return [record.stream_id for record in records]


@router.post(
    "/{job_public_id}/pause",
    response_model=TaskJobRead,
    summary="暂停任务",
    description="暂停指定异步任务，避免继续调度未执行的任务子项。",
)
async def pause_task(
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobRead:
    """暂停指定异步任务。"""
    with _handle_task_errors():
        return await default_async_task_engine.pause_task_job(session, job_public_id)


@router.post(
    "/{job_public_id}/resume",
    response_model=list[str],
    status_code=status.HTTP_202_ACCEPTED,
    summary="恢复任务",
    description="恢复指定异步任务，并重新投递可执行的任务子项。",
)
async def resume_task(
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> list[str]:
    """恢复指定异步任务。"""
    with _handle_task_errors():
        records = await default_async_task_engine.resume_task_job(session, job_public_id)
        return [record.stream_id for record in records]


@router.post(
    "/{job_public_id}/cancel",
    response_model=TaskJobRead,
    summary="取消任务",
    description="取消指定异步任务及其尚未完成的任务子项。",
)
async def cancel_task(
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobRead:
    """取消指定异步任务。"""
    with _handle_task_errors():
        return await default_async_task_engine.cancel_task_job(session, job_public_id)


@router.post(
    "/items/{item_public_id}/cancel",
    response_model=TaskItemRead,
    summary="取消任务子项",
    description="取消指定异步任务子项，并刷新所属任务的进度统计。",
)
async def cancel_task_item(
    item_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskItemRead:
    """取消指定异步任务子项。"""
    with _handle_task_errors():
        return await default_async_task_engine.cancel_task_item(session, item_public_id)


@router.post(
    "/items/{item_public_id}/retry",
    response_model=TaskItemRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="重试任务子项",
    description="将指定异步任务子项重置为待执行状态，等待后续重新调度。",
)
async def retry_task_item(
    item_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskItemRead:
    """重试指定异步任务子项。"""
    with _handle_task_errors():
        return await default_async_task_engine.retry_task_item(session, item_public_id)


@router.delete(
    "/{job_public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除任务",
    description="软删除指定异步任务及其任务子项。",
)
async def delete_task(
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> Response:
    """删除指定异步任务。"""
    with _handle_task_errors():
        await default_async_task_engine.delete_task_job(session, job_public_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{job_public_id}",
    response_model=TaskJobDetail,
    summary="查看单个任务",
    description="查看指定异步任务详情，并包含任务子项列表。",
)
async def get_task(
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobDetail:
    """查看单个异步任务。"""
    with _handle_task_errors():
        return await default_async_task_engine.get_task_job(
            session,
            job_public_id,
            include_items=True,
        )


@router.get(
    "",
    response_model=TaskJobPage,
    summary="查看批量任务",
    description="按分页和筛选条件查看异步任务列表。",
)
async def list_tasks(
    session: SessionDep,
    user=CurrentUser,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    task_type: str = "",
    queue_name: str = "",
    project_public_id: str = "",
    status_: TaskStatus | None = Query(default=None, alias="status"),
) -> TaskJobPage:
    """查看批量异步任务。"""
    with _handle_task_errors():
        return await default_async_task_engine.list_task_jobs(
            session,
            page=page,
            limit=limit,
            task_type=task_type,
            queue_name=queue_name,
            project_public_id=project_public_id,
            status=status_,
        )


# ══════════════════════════════════════════════════════════════
# 项目维度任务端点
# ══════════════════════════════════════════════════════════════


async def _get_project_task(
    session: AsyncSession,
    project_public_id: str,
    job_public_id: str,
    *,
    include_items: bool = False,
) -> TaskJobRead | TaskJobDetail:
    """读取任务并校验其归属项目。"""
    job = await default_async_task_engine.get_task_job(
        session,
        job_public_id,
        include_items=include_items,
    )
    if str(job.payload.get("project_public_id") or "") != project_public_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
    return job


@router.post(
    "/projects/{project_public_id}/tasks",
    response_model=TaskJobDetail,
    status_code=status.HTTP_202_ACCEPTED,
    summary="添加并启动项目异步任务",
    description="在指定项目下创建异步任务记录，并立即投递可执行的任务子项。",
)
async def create_project_task(
    project_public_id: str,
    payload: TaskJobCreate,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobDetail:
    """添加并启动指定项目下的异步任务。"""
    current_user_public_id = str(getattr(user, "public_id", ""))
    payload_data = payload.model_dump()
    payload_data["created_by"] = payload.created_by or current_user_public_id
    payload_data["project_public_id"] = project_public_id
    payload_data["payload"] = {
        **(payload.payload or {}),
        "project_public_id": project_public_id,
    }
    with _handle_task_errors():
        return await default_async_task_engine.create_and_enqueue_task_job(
            session,
            TaskJobCreate(**payload_data),
        )


@router.get(
    "/projects/{project_public_id}/tasks",
    response_model=TaskJobPage,
    summary="查看项目异步任务列表",
    description="按项目公开 ID 分页查看该项目关联的异步任务列表。",
)
async def list_project_tasks(
    project_public_id: str,
    session: SessionDep,
    user=CurrentUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    task_type: str = "",
    queue_name: str = "",
    status_: TaskStatus | None = Query(default=None, alias="status"),
) -> TaskJobPage:
    """查看指定项目下的异步任务列表。"""
    with _handle_task_errors():
        return await default_async_task_engine.list_task_jobs(
            session,
            page=page,
            limit=page_size,
            task_type=task_type,
            queue_name=queue_name,
            project_public_id=project_public_id,
            status=status_,
        )


@router.get(
    "/projects/{project_public_id}/tasks/{job_public_id}/items",
    response_model=TaskItemPage,
    summary="查看项目异步任务子项列表",
    description="按分页和可选状态筛选查看指定异步任务的子项列表。",
)
async def list_project_task_items(
    project_public_id: str,
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
    status_: TaskStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> TaskItemPage:
    """查看指定项目任务的子项列表。"""
    with _handle_task_errors():
        await _get_project_task(session, project_public_id, job_public_id)
        query_status = None if status_ == TaskStatus.PENDING else status_
        items = await default_async_task_engine.list_task_items(
            session, job_public_id, status=query_status,
        )
        items = _filter_task_items_by_status(items, status_)
        return _page_task_items(items, page, page_size)


@router.get(
    "/projects/{project_public_id}/tasks/{job_public_id}/items/{item_public_id}",
    response_model=TaskItemRead,
    summary="查看项目异步任务子项详情",
    description="查看指定项目任务下的单个子项执行详情。",
)
async def get_project_task_item(
    project_public_id: str,
    job_public_id: str,
    item_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskItemRead:
    """查看指定项目任务下的单个子项。"""
    with _handle_task_errors():
        job = await _get_project_task(
            session, project_public_id, job_public_id, include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        for item in job.items:
            if item.public_id == item_public_id:
                return item
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务子项不存在")


@router.get(
    "/projects/{project_public_id}/tasks/{job_public_id}",
    response_model=TaskJobDetail,
    summary="查看项目异步任务详情",
    description="查看指定项目下的单个异步任务详情，并包含任务子项列表。",
)
async def get_project_task(
    project_public_id: str,
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobDetail:
    """查看指定项目下的单个异步任务。"""
    with _handle_task_errors():
        job = await _get_project_task(
            session, project_public_id, job_public_id, include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        return job


@router.post(
    "/projects/{project_public_id}/tasks/{job_public_id}/cancel",
    response_model=TaskJobCancelResponse,
    summary="取消项目异步任务",
    description="取消指定项目任务及其尚未完成的任务子项。",
)
async def cancel_project_task(
    project_public_id: str,
    job_public_id: str,
    payload: TaskJobCancelRequest,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobCancelResponse:
    """取消指定项目下的异步任务。"""
    with _handle_task_errors():
        job = await _get_project_task(
            session, project_public_id, job_public_id, include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")

        target_ids = _target_item_ids(payload.item_public_ids)
        canceled_count = _count_items(job.items, CANCELLABLE_ITEM_STATUSES, target_ids or None)
        if target_ids:
            for item in job.items:
                if item.public_id in target_ids and item.status in CANCELLABLE_ITEM_STATUSES:
                    await default_async_task_engine.cancel_task_item(session, item.public_id)
        else:
            await default_async_task_engine.cancel_task_job(session, job_public_id)
        return TaskJobCancelResponse(canceled_count=canceled_count)


@router.post(
    "/projects/{project_public_id}/tasks/{job_public_id}/pause",
    response_model=TaskJobPauseResponse,
    summary="暂停项目异步任务",
    description="暂停指定项目任务，避免继续调度未执行的任务子项。",
)
async def pause_project_task(
    project_public_id: str,
    job_public_id: str,
    payload: TaskJobPauseRequest,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobPauseResponse:
    """暂停指定项目下的异步任务。"""
    with _handle_task_errors():
        job = await _get_project_task(
            session, project_public_id, job_public_id, include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        target_ids = _target_item_ids(payload.item_public_ids)
        paused_count = _count_items(job.items, PAUSABLE_ITEM_STATUSES, target_ids or None)
        if target_ids:
            await task_service.pause_task_items(session, job_public_id, target_ids)
        else:
            await default_async_task_engine.pause_task_job(session, job_public_id)
        return TaskJobPauseResponse(paused_count=paused_count)


@router.post(
    "/projects/{project_public_id}/tasks/{job_public_id}/resume",
    response_model=TaskJobResumeResponse,
    summary="恢复项目异步任务",
    description="恢复指定项目任务，并重新投递可执行的任务子项。",
)
async def resume_project_task(
    project_public_id: str,
    job_public_id: str,
    payload: TaskJobResumeRequest,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobResumeResponse:
    """恢复指定项目下的异步任务。"""
    with _handle_task_errors():
        job = await _get_project_task(
            session, project_public_id, job_public_id, include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        target_ids = _target_item_ids(payload.item_public_ids)
        resumed_count = _count_items(job.items, RESUMABLE_ITEM_STATUSES, target_ids or None)
        if target_ids:
            await task_service.resume_task_items(session, job_public_id, target_ids)
            for item in job.items:
                if item.public_id in target_ids and item.status in RESUMABLE_ITEM_STATUSES:
                    await default_async_task_engine.enqueue_task_item(session, item.public_id)
        else:
            await default_async_task_engine.resume_task_job(session, job_public_id)
        return TaskJobResumeResponse(resumed_count=resumed_count)


@router.post(
    "/projects/{project_public_id}/tasks/{job_public_id}/retry",
    response_model=TaskJobRetryResponse,
    summary="重试项目异步任务失败子项",
    description="将指定失败或已取消子项重新置为待执行，并立即重新投递。",
)
async def retry_project_task_items(
    project_public_id: str,
    job_public_id: str,
    payload: TaskJobRetryRequest,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobRetryResponse:
    """重试指定项目任务下的子项。"""
    with _handle_task_errors():
        job = await _get_project_task(
            session, project_public_id, job_public_id, include_items=True,
        )
        if not isinstance(job, TaskJobDetail):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="异步任务不存在")
        target_ids = _target_item_ids(payload.item_public_ids)
        retried_ids: list[str] = []
        for item in job.items:
            if item.public_id in target_ids and item.status in RETRYABLE_ITEM_STATUSES:
                retried = await default_async_task_engine.retry_task_item(session, item.public_id)
                retried_ids.append(retried.public_id)
        return TaskJobRetryResponse(new_item_public_ids=retried_ids)


@router.delete(
    "/projects/{project_public_id}/tasks/{job_public_id}",
    response_model=TaskJobDeleteResponse,
    summary="删除项目异步任务",
    description="软删除指定项目任务及其任务子项。",
)
async def delete_project_task(
    project_public_id: str,
    job_public_id: str,
    session: SessionDep,
    user=CurrentUser,
) -> TaskJobDeleteResponse:
    """删除指定项目下的异步任务。"""
    with _handle_task_errors():
        await _get_project_task(session, project_public_id, job_public_id)
        await default_async_task_engine.delete_task_job(session, job_public_id)
        return TaskJobDeleteResponse(status="deleted")
