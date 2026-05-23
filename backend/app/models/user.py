"""
用户数据库模型
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import relationship

from backend.app.models.base import Base
from backend.app.models.base_model import BaseModelMixin


class User(Base, BaseModelMixin):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    nickname = Column(String(64), nullable=True)
    email = Column(String(255), unique=True, nullable=True, index=True)
    avatar_url = Column(String(512), nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_superuser = Column(Boolean, default=False)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    # 关联关系（保留 PromptTemplate 的 back_populates 引用）
    prompt_templates = relationship("PromptTemplate", back_populates="user")

    async def update_last_login(self) -> None:
        """更新最近登录时间"""
        self.last_login_at = datetime.now(timezone.utc)
