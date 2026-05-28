"""
Excel 批量提取 API 路由
支持文件上传、任务管理、WebSocket 实时通信
"""
import os
import uuid
import json
import logging
import asyncio
import pandas as pd
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query, Body, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy import select, and_

from backend.app.models.base import AsyncSessionLocal, get_db
from backend.app.models.excel_extraction import ExcelExtractionTask, ExcelExtractionRow, ExcelExtractionSession
from backend.app.models.user import User
from backend.app.api.deps_user import get_current_user_required
from backend.app.schemas.excel_extraction import (
    ExcelExtractionTaskStatus, RowStatus,
    UploadPreviewResponse, TaskCreateResponse, TaskDetailResponse, TaskListResponse,
    RowDetailResponse, RowListResponse, UserInputRequest,
)
from backend.app.excel_extraction.agent import WebAgentRunner, handle_user_action, cleanup_session
from backend.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# WebSocket 连接管理
# ============================================================================

class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: dict = {}  # {session_id: WebSocket}

    async def connect(self, session_id: str, websocket: WebSocket):
        """建立连接"""
        await websocket.accept()
        self.active_connections[session_id] = websocket
        logger.info(f"[WebSocket] 连接建立: {session_id}")

    def disconnect(self, session_id: str):
        """断开连接"""
        if session_id in self.active_connections:
            del self.active_connections[session_id]
            logger.info(f"[WebSocket] 连接断开: {session_id}")

    async def send_message(self, session_id: str, message: dict):
        """发送消息"""
        if session_id in self.active_connections:
            try:
                await self.active_connections[session_id].send_json(message)
            except Exception as e:
                logger.error(f"[WebSocket] 发送失败: {e}")

    async def broadcast(self, message: dict):
        """广播消息"""
        for session_id in self.active_connections:
            await self.send_message(session_id, message)


manager = ConnectionManager()

# 存储运行中的 Agent
_running_agents: dict = {}  # {session_id: WebAgentRunner}


# ============================================================================
# 数据库更新逻辑（从 WebSocket 解耦）
# ============================================================================

async def _update_task_on_completion(session_id: str, wf_result: dict):
    """工作流完成后更新数据库，不依赖 WebSocket 连接"""
    has_error = wf_result.get("error_message") if wf_result else None
    has_actual_error = has_error and str(has_error).strip() != ""

    logger.info(f"[update_task] 工作流返回: session_id={session_id}, has_actual_error={has_actual_error}, "
                f"output_xlsx_path={wf_result.get('output_xlsx_path')}, "
                f"error_message={repr(wf_result.get('error_message'))}")

    try:
        async with AsyncSessionLocal() as session:
            result_db = await session.execute(
                select(ExcelExtractionTask).where(ExcelExtractionTask.session_id == session_id)
            )
            db_task = result_db.scalar_one_or_none()

            if not db_task:
                logger.warning(f"[update_task] 未找到 session_id={session_id} 对应的任务")
                return

            logger.info(f"[update_task] 找到任务 {db_task.task_id}，当前状态={db_task.status}")

            if has_actual_error:
                db_task.status = ExcelExtractionTaskStatus.FAILED.value
                db_task.error_message = wf_result.get("error_message")
                await session.commit()
                logger.warning(f"[update_task] 任务标记为失败: {db_task.task_id}")
            else:
                # 已完成的任务跳过更新
                if db_task.status == ExcelExtractionTaskStatus.COMPLETED.value:
                    logger.info(f"[update_task] 任务已完成，跳过重复更新: {db_task.task_id}")
                    return

                # 清理 workflow_state 中的非 JSON 可序列化对象（如 DataFrame）
                clean_state = _clean_workflow_state(wf_result)

                db_task.status = ExcelExtractionTaskStatus.COMPLETED.value
                db_task.completed_at = datetime.now()
                db_task.output_file_path = wf_result.get("output_xlsx_path")
                db_task.total_rows = len(wf_result.get("input_dict", {}))
                db_task.success_rows = len(wf_result.get("results_dict", {}))
                db_task.failed_rows = len(wf_result.get("failed_dois", []))
                db_task.workflow_state = clean_state
                await session.commit()
                logger.info(f"[update_task] 任务更新完成: {db_task.task_id}, output_file_path={db_task.output_file_path}")

    except Exception as e:
        logger.exception(f"[update_task] 数据库更新失败: {session_id}")


def _clean_workflow_state(state: dict) -> dict:
    """清理 workflow_state，移除无法 JSON 序列化的对象（如 DataFrame）"""
    import pandas as pd
    import numpy as np

    if not state or not isinstance(state, dict):
        return state

    # 需要移除的非序列化字段
    non_serializable_keys = ["df", "dataframe", "_df", "input_df", "output_df"]

    def is_dataframe(obj):
        """检测是否是 DataFrame 或类似对象"""
        if obj is None:
            return False
        # 检查类型名
        type_name = type(obj).__name__
        if type_name == 'DataFrame' or 'DataFrame' in str(type(obj)):
            return True
        # 检查是否有 DataFrame 的特征属性
        if hasattr(obj, 'columns') and hasattr(obj, 'iloc') and hasattr(obj, 'to_dict'):
            return True
        return False

    def is_ndarray(obj):
        """检测是否是 numpy ndarray"""
        if obj is None:
            return False
        type_name = type(obj).__name__
        return type_name == 'ndarray' or 'ndarray' in str(type(obj))

    def clean_value(key, value):
        """清理单个值"""
        # 跳过非序列化字段名
        if key in non_serializable_keys:
            return None

        # 检查是否是 DataFrame
        if is_dataframe(value):
            return None

        # 检查是否是 ndarray
        if is_ndarray(value):
            return None

        # 尝试直接序列化测试
        try:
            json.dumps(value)
            return value
        except (TypeError, ValueError):
            pass

        # 递归处理字典
        if isinstance(value, dict):
            return _clean_workflow_state(value)

        # 递归处理列表
        if isinstance(value, list):
            clean_list = []
            for i, item in enumerate(value):
                if is_dataframe(item) or is_ndarray(item):
                    continue
                cleaned = clean_value(i, item)
                if cleaned is not None:
                    clean_list.append(cleaned)
            return clean_list

        # 递归处理元组（转为列表）
        if isinstance(value, tuple):
            clean_list = []
            for i, item in enumerate(value):
                if is_dataframe(item) or is_ndarray(item):
                    continue
                cleaned = clean_value(i, item)
                if cleaned is not None:
                    clean_list.append(cleaned)
            return clean_list

        # 尝试转为字符串
        try:
            return str(value)
        except:
            return None

    clean_state = {}
    for key, value in state.items():
        cleaned = clean_value(key, value)
        if cleaned is not None:
            clean_state[key] = cleaned

    return clean_state


# ============================================================================
# 文件上传与预览
# ============================================================================

@router.post("/excel-extraction/upload", response_model=UploadPreviewResponse)
async def upload_excel_files(
    files: List[UploadFile] = File(...),
    strategy_file: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user_required)
):
    """
    上传 Excel 文件并预览数据

    Args:
        files: Excel 文件列表
        strategy_file: 可选的策略 Word 文档
        user: 当前用户

    Returns:
        预览数据（列名、行数、质量统计）
    """
    # 生成 session_id
    session_id = str(uuid.uuid4())[:16]

    # 创建临时目录
    upload_dir = os.path.join(str(settings.UPLOAD_DIR), "excel_extraction", session_id)
    os.makedirs(upload_dir, exist_ok=True)

    try:
        # 保存 Excel 文件
        saved_files = []
        for file in files:
            if not file.filename.endswith((".xlsx", ".xls")):
                continue
            file_path = os.path.join(upload_dir, file.filename)
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)
            saved_files.append(file_path)

        if not saved_files:
            raise HTTPException(status_code=400, detail="未找到有效的 Excel 文件")

        # 保存策略文档
        strategy_path = None
        if strategy_file and strategy_file.filename.endswith(".docx"):
            strategy_path = os.path.join(upload_dir, strategy_file.filename)
            content = await strategy_file.read()
            with open(strategy_path, "wb") as f:
                f.write(content)

        # 合并并预览数据
        dfs = []
        for file_path in saved_files:
            df = pd.read_excel(file_path)
            dfs.append(df)

        merged_df = pd.concat(dfs, ignore_index=True)

        # 标准化列名
        column_mapping = {
            "DOI": "doi", "doi": "doi",
            "Title": "title", "title": "title", "Article Title": "title",
            "Abstract": "abstract", "abstract": "abstract",
            "Authors": "authors", "authors": "authors",
            "Year": "year", "year": "year",
            "Journal": "journal", "journal": "journal",
        }
        merged_df.columns = [column_mapping.get(c, c.lower()) for c in merged_df.columns]

        # 质量统计
        quality_stats = {}
        required_fields = ["doi", "title", "abstract"]
        for field in required_fields:
            if field in merged_df.columns:
                missing = merged_df[field].isna().sum() + (merged_df[field] == "").sum()
                quality_stats[f"missing_{field}"] = int(missing)
            else:
                quality_stats[f"missing_{field}"] = len(merged_df)

        # 预览数据
        preview_rows = merged_df.head(10).to_dict(orient="records")

        # 创建会话记录
        async with AsyncSessionLocal() as session:
            db_session = ExcelExtractionSession(
                session_id=session_id,
                is_connected=False,
                hitl_pending=False,
            )
            session.add(db_session)
            await session.commit()

        logger.info(f"[upload] 上传完成: {session_id}, {len(saved_files)} 个文件, {len(merged_df)} 条记录")

        return UploadPreviewResponse(
            success=True,
            message=f"上传成功，共 {len(merged_df)} 条记录",
            session_id=session_id,
            preview={
                "columns": list(merged_df.columns),
                "row_count": len(merged_df),
                "quality_stats": quality_stats,
                "preview_rows": preview_rows,
                "upload_dir": upload_dir,
                "strategy_path": strategy_path,
            }
        )

    except Exception as e:
        logger.exception(f"[upload] 上传失败")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# 任务管理
# ============================================================================

@router.post("/excel-extraction/tasks", response_model=TaskCreateResponse)
async def create_task(
    task_name: str = Body(...),
    session_id: str = Body(...),
    config: dict = Body(...),
    upload_dir: str = Body(...),
    strategy_path: Optional[str] = Body(None),
    user: User = Depends(get_current_user_required)
):
    """
    创建 Excel 提取任务并启动后台处理
    """
    # 验证 upload_dir
    if not upload_dir or not os.path.isdir(upload_dir):
        raise HTTPException(status_code=400, detail=f"上传目录不存在或无效: {upload_dir}")
    # 生成 task_id
    task_id = str(uuid.uuid4())[:16]

    # 添加配置
    config["folder_path"] = upload_dir
    config["strategy_docx"] = strategy_path
    config["task_id"] = task_id
    config["user_id"] = user.id

    # 创建数据库记录
    async with AsyncSessionLocal() as session:
        db_task = ExcelExtractionTask(
            task_id=task_id,
            task_name=task_name,
            user_id=user.id,
            original_filenames=[os.path.basename(f) for f in os.listdir(upload_dir) if f.endswith((".xlsx", ".xls"))],
            strategy_file_path=strategy_path,
            status=ExcelExtractionTaskStatus.PENDING.value,
            config=config,
            session_id=session_id,
        )
        session.add(db_task)
        await session.commit()

    logger.info(f"[create_task] 任务创建: {task_id}, session: {session_id}")

    return TaskCreateResponse(
        success=True,
        message="任务已创建，请通过 WebSocket 连接开始处理",
        task_id=task_id,
        session_id=session_id,
        status=ExcelExtractionTaskStatus.PENDING,
        total_rows=0,
    )


@router.get("/excel-extraction/tasks", response_model=TaskListResponse)
async def list_tasks(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user_required)
):
    """获取用户任务列表（取消超过24小时的任务自动隐藏）"""
    from sqlalchemy import or_, and_
    from datetime import timedelta

    cutoff = datetime.now() - timedelta(hours=24)

    async with AsyncSessionLocal() as session:
        # 查询条件：用户的任务，排除已取消且超过24小时的
        base_condition = and_(
            ExcelExtractionTask.user_id == user.id,
            or_(
                ExcelExtractionTask.status != ExcelExtractionTaskStatus.CANCELLED.value,
                and_(
                    ExcelExtractionTask.status == ExcelExtractionTaskStatus.CANCELLED.value,
                    ExcelExtractionTask.updated_at >= cutoff
                )
            )
        )

        result = await session.execute(
            select(ExcelExtractionTask)
            .where(base_condition)
            .order_by(ExcelExtractionTask.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        tasks = result.scalars().all()

        # 获取总数
        count_result = await session.execute(
            select(ExcelExtractionTask).where(base_condition)
        )
        total = len(count_result.scalars().all())

        # 在 session block 内转换，确保属性不被过期
        items = [_task_to_response(t) for t in tasks]

    logger.info(f"[list_tasks] 返回 {len(items)} 个任务（已过滤过期取消任务）")

    return TaskListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/excel-extraction/tasks/{task_id}", response_model=TaskDetailResponse)
async def get_task(
    task_id: str,
    user: User = Depends(get_current_user_required)
):
    """获取任务详情"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ExcelExtractionTask)
            .where(and_(ExcelExtractionTask.task_id == task_id, ExcelExtractionTask.user_id == user.id))
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

    return _task_to_response(task)


@router.post("/excel-extraction/tasks/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    user: User = Depends(get_current_user_required)
):
    """取消任务"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ExcelExtractionTask)
            .where(and_(ExcelExtractionTask.task_id == task_id, ExcelExtractionTask.user_id == user.id))
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        if task.status in [ExcelExtractionTaskStatus.COMPLETED.value, ExcelExtractionTaskStatus.FAILED.value]:
            raise HTTPException(status_code=400, detail="任务已完成，无法取消")

        task.status = ExcelExtractionTaskStatus.CANCELLED.value
        await session.commit()

        # 停止运行的 Agent
        session_id = task.session_id
        if session_id in _running_agents:
            _running_agents[session_id].stop()

    return {"success": True, "message": "任务已取消"}


@router.get("/excel-extraction/tasks/{task_id}/rows", response_model=RowListResponse)
async def get_task_rows(
    task_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    user: User = Depends(get_current_user_required)
):
    """获取任务行数据列表"""
    async with AsyncSessionLocal() as session:
        # 验证任务存在
        task_result = await session.execute(
            select(ExcelExtractionTask)
            .where(and_(ExcelExtractionTask.task_id == task_id, ExcelExtractionTask.user_id == user.id))
        )
        task = task_result.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        # 查询行数据
        query = select(ExcelExtractionRow).where(ExcelExtractionRow.task_id == task_id)
        if status:
            query = query.where(ExcelExtractionRow.status == status)

        query = query.order_by(ExcelExtractionRow.row_index).offset((page - 1) * page_size).limit(page_size)

        result = await session.execute(query)
        rows = result.scalars().all()

        # 获取总数
        count_query = select(ExcelExtractionRow).where(ExcelExtractionRow.task_id == task_id)
        if status:
            count_query = count_query.where(ExcelExtractionRow.status == status)
        count_result = await session.execute(count_query)
        total = len(count_result.scalars().all())

    items = [_row_to_response(r) for r in rows]

    return RowListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/excel-extraction/tasks/{task_id}/download")
async def download_results(
    task_id: str,
    user: User = Depends(get_current_user_required)
):
    """下载结果 Excel 文件"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ExcelExtractionTask)
            .where(and_(ExcelExtractionTask.task_id == task_id, ExcelExtractionTask.user_id == user.id))
        )
        task = result.scalar_one_or_none()

        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")

        if task.status != ExcelExtractionTaskStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="任务未完成")

        if not task.output_file_path:
            raise HTTPException(status_code=404, detail="结果文件不存在")

    return FileResponse(
        task.output_file_path,
        filename=os.path.basename(task.output_file_path),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ============================================================================
# WebSocket 端点
# ============================================================================

@router.websocket("/ws/excel-extraction/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    WebSocket 端点
    实时通信：进度更新 + HITL 对话
    """
    await manager.connect(session_id, websocket)

    # 连接建立后，发送当前任务状态（用于恢复监控）
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ExcelExtractionTask).where(ExcelExtractionTask.session_id == session_id)
        )
        db_task = result.scalar_one_or_none()
        if db_task:
            # 发送当前进度状态
            await manager.send_message(session_id, {
                "type": "progress",
                "content": {
                    "step": db_task.current_step or "",
                    "progress": db_task.progress or 0,
                    "message": f"已连接到任务 {db_task.task_name}"
                }
            })
            # 如果有聊天历史，发送最后的 HITL 消息
            if db_task.chat_history and len(db_task.chat_history) > 0:
                last_msg = db_task.chat_history[-1]
                if last_msg.get("role") == "assistant":
                    await manager.send_message(session_id, {
                        "type": "llm_chat",
                        "content": {
                            "role": "assistant",
                            "message": last_msg.get("content", ""),
                            "suggested_actions": [],
                            "issue_details": None
                        }
                    })

    # 工作流任务引用，用于后台运行
    workflow_task: Optional["asyncio.Task"] = None

    try:
        while True:
            # 检查后台工作流是否已完成（run_workflow_bg 已处理数据库更新）
            if workflow_task is not None and workflow_task.done():
                try:
                    wf_result = workflow_task.result()
                    workflow_task = None

                    has_error = wf_result.get("error_message") if wf_result else None
                    has_actual_error = has_error and str(has_error).strip() != ""

                    # 发送前端通知（数据库更新已由 run_workflow_bg 处理）
                    if wf_result and not has_actual_error:
                        await manager.send_message(session_id, {
                            "type": "completed",
                            "content": {
                                "message": "处理完成",
                                "output_file_path": wf_result.get("output_xlsx_path"),
                            }
                        })
                        logger.info(f"[WebSocket] 工作流完成: {session_id}")
                    elif wf_result and has_actual_error:
                        await manager.send_message(session_id, {
                            "type": "failed",
                            "content": {"error": wf_result.get("error_message")}
                        })
                        logger.warning(f"[WebSocket] 工作流失败: {session_id}")
                except Exception as e:
                    logger.exception(f"[WebSocket] 处理工作流结果异常: {session_id}")
                    workflow_task = None

            # 接收消息（带超时，以便定期检查工作流状态）
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=1.0)
            except asyncio.TimeoutError:
                continue

            logger.info(f"[WebSocket] 收到消息: {data.get('type', 'unknown')}")

            message_type = data.get("type", "")

            if message_type == "start":
                # 启动任务
                config = data.get("config", {})
                task_id = config.get("task_id", "")

                # 获取任务配置
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(ExcelExtractionTask).where(ExcelExtractionTask.task_id == task_id)
                    )
                    db_task = result.scalar_one_or_none()

                    if db_task:
                        config = db_task.config
                        config["task_id"] = task_id

                # 创建 Agent
                async def ws_callback(msg: dict):
                    await manager.send_message(session_id, msg)

                runner = WebAgentRunner(session_id, ws_callback)
                _running_agents[session_id] = runner

                # 更新任务状态
                async with AsyncSessionLocal() as session:
                    result = await session.execute(
                        select(ExcelExtractionTask).where(ExcelExtractionTask.session_id == session_id)
                    )
                    db_task = result.scalar_one_or_none()
                    if db_task:
                        db_task.status = ExcelExtractionTaskStatus.PROCESSING.value
                        db_task.started_at = datetime.now()
                        await session.commit()

                # 启动后台工作流任务（不阻塞消息接收）
                async def run_workflow_bg():
                    try:
                        result = await runner.run(config)
                        # 工作流完成后自动更新数据库（不依赖 WebSocket）
                        await _update_task_on_completion(session_id, result)
                        return result
                    except Exception as e:
                        logger.exception(f"Agent 执行失败: {session_id}")
                        error_result = {"error_message": str(e)}
                        # 即使 WebSocket 断开，也尝试更新数据库
                        try:
                            await _update_task_on_completion(session_id, error_result)
                        except Exception:
                            pass
                        try:
                            await manager.send_message(session_id, {
                                "type": "failed",
                                "content": {"error": str(e)}
                            })
                        except Exception:
                            pass
                        return error_result
                    finally:
                        if session_id in _running_agents:
                            del _running_agents[session_id]

                workflow_task = asyncio.create_task(run_workflow_bg())
                logger.info(f"[WebSocket] 工作流已启动: {session_id}")

            elif message_type == "user_input":
                # 用户输入响应（HITL 对话）
                input_type = data.get("input_type", "text")
                text = data.get("text", "")
                action = data.get("action", "")
                extra_data = data.get("data", {})

                logger.info(f"[user_input] input_type={input_type}, action={action}, text_len={len(text)}")

                # 设置用户动作，唤醒等待中的工作流
                await handle_user_action(
                    session_id,
                    action or "text_input",
                    {"text": text, "action": action, "data": extra_data}
                )

            elif message_type == "cancel":
                # 取消任务
                if workflow_task and not workflow_task.done():
                    workflow_task.cancel()
                if session_id in _running_agents:
                    try:
                        _running_agents[session_id].stop()
                    except Exception as e:
                        logger.warning(f"[WebSocket] 停止 Agent 异常: {e}")
                    finally:
                        del _running_agents[session_id]
                await manager.send_message(session_id, {
                    "type": "cancelled",
                    "content": {"message": "任务已取消"}
                })

    except WebSocketDisconnect:
        manager.disconnect(session_id)
        try:
            await cleanup_session(session_id)
        except Exception as e:
            logger.warning(f"[WebSocket] cleanup_session 异常: {session_id}, {e}")

        # WebSocket 断开时不取消工作流，让它完成后自动更新数据库
        logger.info(f"[WebSocket] 连接断开: {session_id}，工作流将继续在后台运行")

    except Exception as e:
        logger.exception(f"WebSocket 异常: {session_id}")
        manager.disconnect(session_id)


# ============================================================================
# 辅助函数
# ============================================================================

def _task_to_response(task: ExcelExtractionTask) -> TaskDetailResponse:
    """转换数据库任务到响应格式"""
    return TaskDetailResponse(
        task_id=task.task_id,
        task_name=task.task_name or "",
        session_id=task.session_id,
        status=ExcelExtractionTaskStatus(task.status),
        total_rows=task.total_rows or 0,
        processed_rows=task.processed_rows or 0,
        success_rows=task.success_rows or 0,
        failed_rows=task.failed_rows or 0,
        progress=task.progress or 0.0,
        current_step=task.current_step,
        current_node=task.current_node,
        pending_check=task.pending_check,
        config=task.config or {},
        chat_history=task.chat_history or [],
        created_at=task.created_at,
        started_at=task.started_at,
        completed_at=task.completed_at,
        error_message=task.error_message,
        output_file_path=task.output_file_path,
    )


def _row_to_response(row: ExcelExtractionRow) -> RowDetailResponse:
    """转换数据库行数据到响应格式"""
    return RowDetailResponse(
        id=row.id,
        row_index=row.row_index,
        unique_key=row.unique_key,
        raw_data=row.raw_data or {},
        quality_score=row.quality_score,
        quality_issues=row.quality_issues or [],
        status=RowStatus(row.status),
        extraction_result=row.extraction_result,
        error_message=row.error_message,
    )