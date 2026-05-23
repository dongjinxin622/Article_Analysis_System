"""
数据库模型公共 Mixin
提供 public_id、时间戳、软删除等通用字段和方法
"""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, String, DateTime, Integer


class BaseModelMixin:
    """可混入 SQLAlchemy 模型的公共字段和方法"""

    public_id = Column(
        String(36),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: str(uuid4()),
    )
    sort_order = Column(Integer, default=0, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )
    disabled_at = Column(DateTime(timezone=True), nullable=True, index=True)

    @property
    def is_disabled(self) -> bool:
        """实体是否已被禁用"""
        return self.disabled_at is not None

    @property
    def is_active(self) -> bool:
        """实体是否可用"""
        return self.disabled_at is None

    async def disable(self) -> None:
        """禁用实体"""
        self.disabled_at = datetime.now(timezone.utc)

    async def enable(self) -> None:
        """启用实体"""
        self.disabled_at = None
