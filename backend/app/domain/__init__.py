# -*- coding: utf-8 -*-
"""
领域分析模块

提供可扩展的领域分析器框架。
"""

from .base import DomainAnalyzerBase
from .registry import DomainRegistry, register_domain

__all__ = [
    "DomainAnalyzerBase",
    "DomainRegistry",
    "register_domain"
]