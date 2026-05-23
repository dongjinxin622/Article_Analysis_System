"""
Prompt模板数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class PromptTemplate(Base):
    """Prompt模板表"""
    __tablename__ = "prompt_templates"
    __table_args__ = (
        UniqueConstraint("name", "user_id", name="uix_prompt_name_user"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)  # 移除 unique=True，改为复合唯一约束
    content = Column(Text, nullable=False)  # prompt内容
    description = Column(String(500))  # 描述
    category = Column(String(50), nullable=False)  # 分类: "ner", "re"
    domain = Column(String(100))  # 领域: "material", "general"
    is_active = Column(Boolean, default=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)  # 新增：用户ID，NULL表示全局共享
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    user = relationship("User", back_populates="prompt_templates")