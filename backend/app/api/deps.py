"""
API 通用依赖注入
仅保留数据库会话依赖，用户认证依赖已迁移至 deps_user.py
"""
from backend.app.models.base import get_db