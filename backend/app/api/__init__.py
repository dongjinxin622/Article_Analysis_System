"""
API路由模块
"""
from backend.app.api.deps import get_db
from backend.app.api.deps_user import get_current_user, get_current_user_required, get_admin_user

__all__ = ["get_db", "get_current_user", "get_current_user_required", "get_admin_user"]