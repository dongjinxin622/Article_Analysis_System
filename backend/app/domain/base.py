# -*- coding: utf-8 -*-
"""
领域分析器基类

定义可扩展的领域分析器接口，所有领域分析器必须继承此基类。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
from loguru import logger


class DomainAnalyzerBase(ABC):
    """
    领域分析器基类

    所有领域分析器必须实现以下抽象方法：
    - get_entity_types(): 返回领域实体类型定义
    - get_relation_types(): 返回领域关系类型定义
    - get_prompt_template(): 返回 NER Prompt 模板
    - build_profile(): 构建领域特征描述
    - analyze(): 执行领域特定分析
    """

    def __init__(
        self,
        embedding_service: Any = None,
        vector_service: Any = None,
        llm_service: Any = None
    ):
        """
        初始化领域分析器

        Args:
            embedding_service: 向量化服务实例
            vector_service: Milvus 向量存储服务实例
            llm_service: LLM 服务实例
        """
        self.embedding_service = embedding_service
        self.vector_service = vector_service
        self.llm_service = llm_service
        logger.info(f"领域分析器基类已初始化")

    @abstractmethod
    def get_name(self) -> str:
        """
        返回领域名称

        Returns:
            领域名称字符串
        """
        pass

    @abstractmethod
    def get_entity_types(self) -> Dict[str, str]:
        """
        返回领域实体类型定义

        Returns:
            {entity_type: description} 字典
        """
        pass

    @abstractmethod
    def get_relation_types(self) -> Dict[str, str]:
        """
        返回领域关系类型定义

        Returns:
            {relation_type: description} 字典
        """
        pass

    @abstractmethod
    def get_prompt_template(self) -> str:
        """
        返回 NER Prompt 模板

        Returns:
            Prompt 模板字符串
        """
        pass

    @abstractmethod
    async def build_profile(self, ner_result: Dict) -> str:
        """
        构建领域特征描述

        Args:
            ner_result: NER 结果数据

        Returns:
            领域特征描述文本
        """
        pass

    @abstractmethod
    async def analyze(self, input_data: Dict) -> Dict:
        """
        执行领域特定分析

        Args:
            input_data: 分析输入数据

        Returns:
            分析结果字典
        """
        pass

    async def retrieve_similar(
        self,
        profile: str,
        collection_name: str = "tech_routes",
        top_k: int = 10
    ) -> List[Dict]:
        """
        从 Milvus 检索相似论文

        Args:
            profile: 特征描述文本
            collection_name: Milvus Collection 名称
            top_k: 返回前 K 个结果

        Returns:
            相似论文列表
        """
        if not self.embedding_service or not self.vector_service:
            logger.warning("向量服务未初始化，无法检索相似论文")
            return []

        try:
            # 向量化特征描述
            vector = await self.embedding_service.embed_text(profile)

            # 从 Milvus 搜索
            results = await self.vector_service.search_similar(
                collection_name=collection_name,
                query_vector=vector,
                top_k=top_k
            )

            return results

        except Exception as e:
            logger.error(f"检索相似论文失败: {e}")
            return []

    async def store_profile_vector(
        self,
        paper_id: str,
        profile: str,
        collection_name: str = "tech_routes",
        metadata: Dict = None
    ) -> bool:
        """
        将特征描述向量存储到 Milvus

        Args:
            paper_id: 论文标识
            profile: 特征描述文本
            collection_name: Milvus Collection 名称
            metadata: 元数据字典

        Returns:
            是否成功
        """
        if not self.embedding_service or not self.vector_service:
            logger.warning("向量服务未初始化，无法存储向量")
            return False

        try:
            # 向量化特征描述
            vector = await self.embedding_service.embed_text(profile)

            # 存储到 Milvus
            await self.vector_service.insert_vector(
                collection_name=collection_name,
                data={
                    "paper_id": paper_id,
                    "profile_text": profile,
                    "embedding": vector,
                    **(metadata or {})
                }
            )

            logger.info(f"特征向量已存储: {paper_id}")
            return True

        except Exception as e:
            logger.error(f"存储特征向量失败: {e}")
            return False

    def get_config(self) -> Dict:
        """
        获取领域完整配置

        Returns:
            领域配置字典
        """
        return {
            "domain_name": self.get_name(),
            "entity_types": self.get_entity_types(),
            "relation_types": self.get_relation_types(),
            "prompt_template": self.get_prompt_template(),
            "is_active": True
        }