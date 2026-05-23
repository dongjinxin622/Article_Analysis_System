"""
配置管理 API 路由
包含 Prompt 模板的完整 CRUD 实现
支持用户隔离：私有模板 + 全局共享模板
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import logging

from backend.app.api.deps import get_db, get_current_user_required
from backend.app.services.prompt_service import get_prompt_service

router = APIRouter()
logger = logging.getLogger(__name__)


# ===== Prompt 模板 Schema =====
class PromptTemplateCreate(BaseModel):
    """创建 Prompt 模板请求"""
    name: str = Field(..., description="模板名称", min_length=1, max_length=200)
    content: str = Field(..., description="模板内容", min_length=1)
    description: Optional[str] = Field(None, description="模板描述", max_length=500)
    category: str = Field("ner", description="分类: ner 或 re")
    domain: Optional[str] = Field(None, description="领域", max_length=100)


class PromptTemplateUpdate(BaseModel):
    """更新 Prompt 模板请求"""
    content: Optional[str] = Field(None, description="模板内容")
    description: Optional[str] = Field(None, description="模板描述")
    is_active: Optional[bool] = Field(None, description="是否活跃")


class PromptTemplateResponse(BaseModel):
    """Prompt 模板响应"""
    name: str
    content: str
    description: Optional[str] = None
    category: str
    domain: Optional[str] = None
    is_active: bool
    user_id: Optional[int] = None  # 新增：用于区分归属
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PromptTemplateListResponse(BaseModel):
    """Prompt 模板列表响应"""
    templates: List[PromptTemplateResponse]
    total: int


# ===== Prompt 模板 API =====
@router.get("/config/prompts", response_model=PromptTemplateListResponse, summary="获取 Prompt 模板列表")
async def get_prompt_templates(
    category: Optional[str] = None,
    domain: Optional[str] = None,
    user = Depends(get_current_user_required)
):
    """
    获取 Prompt 模板列表（用户私有 + 全局共享）

    - **category**: 分类筛选（ner/re）
    - **domain**: 领域筛选
    """
    try:
        prompt_service = get_prompt_service()
        templates = await prompt_service.list_prompts(
            user_id=user.id,
            category=category,
            domain=domain
        )

        return PromptTemplateListResponse(
            templates=[PromptTemplateResponse(**t) for t in templates],
            total=len(templates)
        )
    except Exception as e:
        logger.error(f"获取Prompt模板列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config/prompts/{prompt_name}", response_model=PromptTemplateResponse, summary="获取 Prompt 模板")
async def get_prompt_template(
    prompt_name: str,
    user = Depends(get_current_user_required)
):
    """
    获取指定 Prompt 模板内容

    - **prompt_name**: 模板名称
    """
    try:
        prompt_service = get_prompt_service()
        template = await prompt_service.get_prompt(prompt_name, user_id=user.id)

        if not template:
            raise HTTPException(status_code=404, detail=f"Prompt模板 '{prompt_name}' 不存在")

        return PromptTemplateResponse(**template)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取Prompt模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/config/prompts", response_model=PromptTemplateResponse, summary="创建 Prompt 模板")
async def create_prompt_template(
    request: PromptTemplateCreate,
    user = Depends(get_current_user_required)
):
    """
    创建新的 Prompt 模板（用户私有）

    - **name**: 模板名称（用户内唯一）
    - **content**: 模板内容
    - **description**: 模板描述（可选）
    - **category**: 分类（ner/re）
    - **domain**: 领域（可选）
    """
    try:
        prompt_service = get_prompt_service()

        # 验证category
        if request.category not in ["ner", "re"]:
            raise HTTPException(status_code=400, detail="category 必须是 'ner' 或 're'")

        template = await prompt_service.create_prompt(
            name=request.name,
            content=request.content,
            description=request.description,
            category=request.category,
            domain=request.domain,
            user_id=user.id  # 用户私有
        )

        return PromptTemplateResponse(**template)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建Prompt模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/config/prompts/{prompt_name}", response_model=PromptTemplateResponse, summary="更新 Prompt 模板")
async def update_prompt_template(
    prompt_name: str,
    request: PromptTemplateUpdate,
    user = Depends(get_current_user_required)
):
    """
    更新 Prompt 模板内容

    权限规则：
    - 用户自己的模板（user_id == 当前用户）：可编辑
    - 系统共享模板（user_id == NULL）：仅管理员可编辑
    - 其他用户的模板：不可编辑

    - **prompt_name**: 模板名称
    - **content**: 新模板内容（可选）
    - **description**: 新描述（可选）
    - **is_active**: 是否活跃（可选）
    """
    try:
        prompt_service = get_prompt_service()

        # 先获取模板，检查归属
        template = await prompt_service.get_prompt(prompt_name, user_id=user.id)

        if not template:
            raise HTTPException(status_code=404, detail=f"Prompt模板 '{prompt_name}' 不存在")

        # 权限检查
        template_user_id = template.get("user_id")
        if template_user_id is None:
            # 共享模板：仅管理员可编辑
            if not user.is_admin:
                raise HTTPException(status_code=403, detail="不能编辑系统共享模板，仅管理员可操作")
        elif template_user_id != user.id:
            # 其他用户的模板
            raise HTTPException(status_code=403, detail="无权编辑其他用户的模板")

        # 执行更新
        updated = await prompt_service.update_prompt(
            prompt_name,
            user_id=user.id,
            content=request.content,
            description=request.description,
            is_active=request.is_active
        )

        if not updated:
            raise HTTPException(status_code=404, detail=f"Prompt模板 '{prompt_name}' 不存在")

        return PromptTemplateResponse(**updated)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新Prompt模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/config/prompts/{prompt_name}", summary="删除 Prompt 模板")
async def delete_prompt_template(
    prompt_name: str,
    user = Depends(get_current_user_required)
):
    """
    删除 Prompt 模板

    只能删除用户自己的模板，不能删除全局共享模板（user_id=NULL）

    - **prompt_name**: 模板名称
    """
    try:
        prompt_service = get_prompt_service()

        # 先检查模板是否存在及其归属
        template = await prompt_service.get_prompt(prompt_name, user_id=user.id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Prompt模板 '{prompt_name}' 不存在")

        # 检查是否为共享模板
        if template.get("user_id") is None:
            raise HTTPException(status_code=403, detail="不能删除系统共享模板")

        success = await prompt_service.delete_prompt(prompt_name, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Prompt模板 '{prompt_name}' 不存在")

        return {"success": True, "message": f"Prompt模板 '{prompt_name}' 已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除Prompt模板失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== 系统配置 API =====
@router.get("/config/system", summary="获取系统配置")
async def get_system_config(
    user = Depends(get_current_user_required)
):
    """
    获取系统配置信息
    """
    from backend.app.core.config import settings
    return {
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "debug": settings.DEBUG,
        "api_prefix": settings.API_V1_PREFIX
    }


@router.get("/config/status", summary="获取服务状态")
async def get_service_status():
    """
    获取各服务连接状态（无需认证）
    """
    from backend.app.core.config import settings
    return {
        "success": True,
        "services": {
            "mysql": {"host": settings.MYSQL_HOST, "port": settings.MYSQL_PORT, "status": "configured"},
            "milvus": {"host": settings.MILVUS_HOST, "port": settings.MILVUS_PORT, "status": "configured"},
            "redis": {"host": settings.REDIS_HOST, "port": settings.REDIS_PORT, "status": "configured"},
            "grobid": {"url": settings.GROBID_URL, "status": "configured"}
        }
    }