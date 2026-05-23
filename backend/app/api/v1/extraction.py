"""
批量提取 API 路由 - LangGraph 工作流
"""
from fastapi import APIRouter, Depends

from backend.app.schemas.batch import BatchExtractionRequest, BatchTaskResponse, HITLCheckpoint
from backend.app.api.deps import get_db, get_current_user_required

router = APIRouter()


@router.post("/extraction", response_model=BatchTaskResponse, summary="启动批量提取工作流")
async def start_extraction_workflow(
    request: BatchExtractionRequest,
    db = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    启动 LangGraph 批量提取工作流

    - **result_ids**: 处理结果 ID 列表
    - **extraction_config**: 提取配置
    - **enable_hitl**: 是否启用 HITL
    """
    # TODO: 实现 LangGraph 工作流启动逻辑
    return BatchTaskResponse(
        success=True,
        message="批量提取工作流已启动",
        task_id="extraction_workflow_001",
        status="processing",
        total_count=len(request.result_ids)
    )


@router.get("/extraction/{task_id}/checkpoint", response_model=HITLCheckpoint, summary="获取检查点")
async def get_checkpoint(
    task_id: str,
    db = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    获取当前 HITL 检查点数据

    - **task_id**: 任务 ID
    """
    # TODO: 实现获取检查点逻辑
    return HITLCheckpoint(
        checkpoint_id=f"cp_{task_id}",
        step_name="data_quality",
        data={},
        requires_review=True
    )


@router.post("/extraction/{task_id}/checkpoint/review", summary="审核检查点")
async def review_checkpoint(
    task_id: str,
    action: str,  # approve/reject/modify
    modifications: dict = None,
    db = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """
    审核 HITL 检查点

    - **task_id**: 任务 ID
    - **action**: 审核动作 (approve/reject/modify)
    """
    # TODO: 实现审核检查点逻辑
    return {"success": True, "message": f"检查点审核完成，动作: {action}"}