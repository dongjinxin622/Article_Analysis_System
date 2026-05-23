# -*- coding: utf-8 -*-
"""
领域分析器注册中心

实现领域分析器的注册、获取和管理机制。
"""

from typing import Dict, List, Optional, Type
from loguru import logger

from .base import DomainAnalyzerBase


class DomainRegistry:
    """
    领域分析器注册中心

    使用类级别变量存储已注册的领域分析器。
    """

    # 已注册的领域分析器字典
    _analyzers: Dict[str, DomainAnalyzerBase] = {}

    # 领域分析器类型字典（用于延迟初始化）
    _analyzer_classes: Dict[str, Type[DomainAnalyzerBase]] = {}

    @classmethod
    def register(cls, domain: str, analyzer: DomainAnalyzerBase) -> None:
        """
        注册领域分析器

        Args:
            domain: 领域名称
            analyzer: 领域分析器实例
        """
        if domain in cls._analyzers:
            logger.warning(f"领域 '{domain}' 已存在，将覆盖原有分析器")

        cls._analyzers[domain] = analyzer
        logger.info(f"领域分析器已注册: {domain}")

    @classmethod
    def register_class(cls, domain: str, analyzer_class: Type[DomainAnalyzerBase]) -> None:
        """
        注册领域分析器类（延迟初始化）

        Args:
            domain: 领域名称
            analyzer_class: 领域分析器类
        """
        cls._analyzer_classes[domain] = analyzer_class
        logger.info(f"领域分析器类已注册: {domain}")

    @classmethod
    def get(cls, domain: str) -> Optional[DomainAnalyzerBase]:
        """
        获取领域分析器

        Args:
            domain: 领域名称

        Returns:
            领域分析器实例，如果不存在返回 None
        """
        # 如果已初始化，直接返回
        if domain in cls._analyzers:
            return cls._analyzers[domain]

        # 如果有注册的类，尝试初始化
        if domain in cls._analyzer_classes:
            analyzer_class = cls._analyzer_classes[domain]
            try:
                analyzer = analyzer_class()
                cls._analyzers[domain] = analyzer
                return analyzer
            except Exception as e:
                logger.error(f"初始化领域分析器失败: {domain}, {e}")
                return None

        return None

    @classmethod
    def list_domains(cls) -> List[str]:
        """
        列出所有已注册领域

        Returns:
            领域名称列表
        """
        # 合并已初始化和未初始化的领域
        all_domains = set(cls._analyzers.keys()) | set(cls._analyzer_classes.keys())
        return list(all_domains)

    @classmethod
    def get_config(cls, domain: str) -> Optional[Dict]:
        """
        获取领域配置

        Args:
            domain: 领域名称

        Returns:
            领域配置字典，如果不存在返回 None
        """
        analyzer = cls.get(domain)
        if analyzer:
            return analyzer.get_config()
        return None

    @classmethod
    def get_all_configs(cls) -> Dict[str, Dict]:
        """
        获取所有领域配置

        Returns:
            {domain: config} 字典
        """
        configs = {}
        for domain in cls.list_domains():
            config = cls.get_config(domain)
            if config:
                configs[domain] = config
        return configs

    @classmethod
    def unregister(cls, domain: str) -> bool:
        """
        注销领域分析器

        Args:
            domain: 领域名称

        Returns:
            是否成功注销
        """
        if domain in cls._analyzers:
            del cls._analyzers[domain]
            logger.info(f"领域分析器已注销: {domain}")
            return True

        if domain in cls._analyzer_classes:
            del cls._analyzer_classes[domain]
            logger.info(f"领域分析器类已注销: {domain}")
            return True

        return False

    @classmethod
    def clear(cls) -> None:
        """
        清空所有已注册的领域分析器
        """
        cls._analyzers.clear()
        cls._analyzer_classes.clear()
        logger.info("所有领域分析器已清空")


# 领域注册装饰器
def register_domain(domain_name: str):
    """
    领域注册装饰器

    用于自动注册领域分析器类。

    Args:
        domain_name: 领域名称

    Example:
        @register_domain('rebco')
        class REBCOAnalyzer(DomainAnalyzerBase):
            ...
    """
    def decorator(analyzer_class: Type[DomainAnalyzerBase]):
        DomainRegistry.register_class(domain_name, analyzer_class)
        return analyzer_class
    return decorator