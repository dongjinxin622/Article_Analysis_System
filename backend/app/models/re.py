"""
关系抽取结果数据库模型
"""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from backend.app.models.base import Base


class REResult(Base):
    """关系抽取结果表"""
    __tablename__ = "re_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    re_id = Column(String(255), unique=True, nullable=False, index=True)
    result_id = Column(String(255), ForeignKey("processing_results.result_id", ondelete="CASCADE"))
    ner_id = Column(String(255), ForeignKey("ner_results.ner_id", ondelete="CASCADE"), nullable=False)
    re_json_path = Column(String(1000))
    re_excel_path = Column(String(1000))
    re_pkl_path = Column(String(1000))
    relation_count = Column(Integer, default=0)
    relation_types = Column(JSON)  # 存储关系类型统计
    status = Column(String(50), default="pending")
    error_message = Column(Text)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    processed_at = Column(DateTime)

    # 关联关系
    ner_result = relationship("NERResult", back_populates="re_results")
    processing_result = relationship("ProcessingResult", back_populates="re_results")


class Relation(Base):
    """关系表（可选，用于向量存储映射）"""
    __tablename__ = "relations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    relation_id = Column(String(255), unique=True, nullable=False, index=True)
    re_id = Column(String(255), ForeignKey("re_results.re_id", ondelete="CASCADE"))
    relation_type = Column(String(100))
    source_type = Column(String(100))
    source_entity = Column(String(500))
    target_type = Column(String(100))
    target_entity = Column(String(500))
    effect = Column(String(50))  # neutral/positive/negative
    supporting_sentence = Column(Text)
    confidence = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)