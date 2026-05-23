"""
NER 结果数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class NERResult(Base):
    """NER 结果表"""
    __tablename__ = "ner_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ner_id = Column(String(255), unique=True, nullable=False, index=True)
    result_id = Column(String(255), ForeignKey("processing_results.result_id", ondelete="CASCADE"), nullable=False)
    ner_json_path = Column(String(1000))
    ner_excel_path = Column(String(1000))
    ner_pkl_path = Column(String(1000))
    entity_count = Column(Integer, default=0)
    entity_types = Column(JSON)  # 存储实体类型统计
    status = Column(String(50), default="pending")
    error_message = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    processed_at = Column(DateTime)

    # 关联关系
    processing_result = relationship("ProcessingResult", back_populates="ner_results")
    re_results = relationship("REResult", back_populates="ner_result", cascade="all, delete-orphan")


class Entity(Base):
    """实体表（可选，用于向量存储映射）"""
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_id = Column(String(255), unique=True, nullable=False, index=True)
    ner_id = Column(String(255), ForeignKey("ner_results.ner_id", ondelete="CASCADE"))
    entity_type = Column(String(100))
    entity_name = Column(String(500))
    entity_text = Column(Text)
    section_idx = Column(Integer)
    group_idx = Column(Integer)
    sentence_idx = Column(Integer)
    confidence = Column(Integer)
    source_sentence = Column(Text)
    created_at = Column(DateTime, default=datetime.now)