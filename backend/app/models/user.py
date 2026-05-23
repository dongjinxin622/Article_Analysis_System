"""
用户数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)  # 匹配数据库字段名
    email = Column(String(100), unique=True, nullable=True)
    full_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)  # 直接使用 is_admin
    last_login = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    processing_results = relationship("ProcessingResult", backref="user")
    ner_results = relationship("NERResult", backref="user")
    re_results = relationship("REResult", backref="user")
    batch_tasks = relationship("BatchTask", backref="user")
    prompt_templates = relationship("PromptTemplate", back_populates="user")