"""
论文处理结果数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class ProcessingResult(Base):
    """处理结果表"""
    __tablename__ = "processing_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    result_id = Column(String(255), unique=True, nullable=False, index=True)
    file_name = Column(String(500), nullable=False)
    file_path = Column(String(1000))
    title = Column(String(1000))
    doi = Column(String(255), index=True)
    abstract = Column(Text)
    status = Column(String(50), default="pending")
    error_message = Column(Text)
    result_pkl_path = Column(String(1000))
    result_json_path = Column(String(1000))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    processed_at = Column(DateTime)

    # 关联关系
    ner_results = relationship("NERResult", back_populates="processing_result", cascade="all, delete-orphan")
    re_results = relationship("REResult", back_populates="processing_result", cascade="all, delete-orphan")


class Paper(Base):
    """论文模型（用于向量存储映射）"""
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(String(255), unique=True, nullable=False, index=True)
    result_id = Column(String(255), ForeignKey("processing_results.result_id"))
    title = Column(String(1000))
    doi = Column(String(255))
    abstract = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)