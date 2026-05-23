"""
领域配置数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class DomainConfig(Base):
    """领域配置表"""
    __tablename__ = "domain_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain_name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text)
    entity_types = Column(JSON)  # 实体类型定义
    relation_types = Column(JSON)  # 关系类型定义
    prompt_templates = Column(JSON)  # Prompt 模板配置
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class TechRoute(Base):
    """技术路线表"""
    __tablename__ = "tech_routes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    profile_id = Column(String(255), unique=True, nullable=False, index=True)
    paper_id = Column(String(255), ForeignKey("processing_results.result_id"))
    ner_id = Column(String(255), ForeignKey("ner_results.ner_id"))
    profile_text = Column(Text)
    domain = Column(String(50))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)


class ExpScheme(Base):
    """实验方案表"""
    __tablename__ = "exp_schemes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scheme_id = Column(String(255), unique=True, nullable=False, index=True)
    paper_id = Column(String(255), ForeignKey("processing_results.result_id"))
    ner_id = Column(String(255), ForeignKey("ner_results.ner_id"))
    scheme_text = Column(Text)
    dimensions = Column(JSON)  # 8维度分析数据
    domain = Column(String(50))
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)


class FailedLog(Base):
    """失败日志表"""
    __tablename__ = "failed_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    log_id = Column(String(255), unique=True, nullable=False)
    result_id = Column(String(255))
    file_name = Column(String(500))
    error_type = Column(String(100))
    error_message = Column(Text)
    error_stack = Column(Text)
    retry_count = Column(Integer, default=0)
    status = Column(String(50), default="new")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)