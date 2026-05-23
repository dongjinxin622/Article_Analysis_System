"""
Embedding 服务 - 使用 OpenAI/Qwen API 进行文本向量化
"""
import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
import numpy as np
from openai import AsyncOpenAI
import httpx

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Embedding 服务类"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        embedding_model: str = None,
        dimensions: int = None,
        request_timeout: int = 60
    ):
        """
        初始化 Embedding 服务

        Args:
            api_key: API 密钥
            base_url: API 基础 URL
            embedding_model: 嵌入模型名称（默认从配置读取，需与 Milvus 中已有数据一致）
            dimensions: 向量维度（默认从配置读取）
            request_timeout: 请求超时时间（秒）
        """
        self.api_key = api_key or settings.API_KEY
        self.base_url = base_url or settings.BASE_URL
        self.embedding_model = embedding_model or settings.EMBEDDING_MODEL
        self.dimensions = dimensions or settings.EMBEDDING_DIM

        # 创建异步 HTTP 客户端
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout, connect=30.0),
            limits=httpx.Limits(max_connections=100)
        )

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=self.http_client
        )

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()

    async def text_to_vector(
        self,
        text: str,
        dimensions: Optional[int] = None
    ) -> List[float]:
        """
        将单个文本转换为向量

        Args:
            text: 输入文本
            dimensions: 向量维度（可选，覆盖默认值）

        Returns:
            向量列表
        """
        if not text or not text.strip():
            logger.warning("输入文本为空，返回零向量")
            return [0.0] * (dimensions or self.dimensions)

        dims = dimensions or self.dimensions

        try:
            response = await self.client.embeddings.create(
                model=self.embedding_model,
                input=[text],
                dimensions=dims
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"文本向量化失败: {e}")
            raise

    async def batch_text_to_vectors(
        self,
        texts: List[str],
        dimensions: Optional[int] = None,
        batch_size: int = 6
    ) -> List[List[float]]:
        """
        批量文本向量化

        Args:
            texts: 文本列表
            dimensions: 向量维度
            batch_size: 每批处理数量

        Returns:
            向量列表
        """
        if not texts:
            return []

        dims = dimensions or self.dimensions
        all_vectors = []

        # 分批处理
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]

            # 过滤空文本
            valid_texts = [t if t and t.strip() else " " for t in batch_texts]

            try:
                response = await self.client.embeddings.create(
                    model=self.embedding_model,
                    input=valid_texts,
                    dimensions=dims
                )

                batch_vectors = [item.embedding for item in response.data]
                all_vectors.extend(batch_vectors)

                logger.debug(f"批次 {i//batch_size + 1}: 向量化完成 {len(batch_texts)} 条文本")

            except Exception as e:
                logger.error(f"批次向量化失败: {e}")
                # 返回零向量作为备用
                zero_vectors = [[0.0] * dims for _ in batch_texts]
                all_vectors.extend(zero_vectors)

        logger.info(f"批量向量化完成，共 {len(all_vectors)} 条")
        return all_vectors

    def cosine_similarity(
        self,
        vector1: List[float],
        vector2: List[float]
    ) -> float:
        """
        计算两个向量的余弦相似度

        Args:
            vector1: 向量 1
            vector2: 向量 2

        Returns:
            余弦相似度值 (0-1 之间)
        """
        if len(vector1) != len(vector2):
            logger.warning('向量维度不匹配')
            return 0.0

        v1 = np.array(vector1)
        v2 = np.array(vector2)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(np.dot(v1, v2) / (norm1 * norm2))

    def batch_cosine_similarity(
        self,
        query_vector: List[float],
        vectors: List[List[float]]
    ) -> List[float]:
        """
        批量计算余弦相似度

        Args:
            query_vector: 查询向量
            vectors: 向量列表

        Returns:
            相似度列表
        """
        if not vectors:
            return []

        query = np.array(query_vector)
        database = np.array(vectors)

        # 计算所有相似度
        query_norm = np.linalg.norm(query)
        if query_norm == 0:
            return [0.0] * len(vectors)

        db_norms = np.linalg.norm(database, axis=1)
        db_norms[db_norms == 0] = 1  # 避免除零

        similarities = np.dot(database, query) / (db_norms * query_norm)
        return similarities.tolist()


# 全局 Embedding 服务实例（懒加载）
_embedding_service: Optional[EmbeddingService] = None


async def get_embedding_service() -> EmbeddingService:
    """获取 Embedding 服务实例"""
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


async def text_to_embedding(text: str) -> List[float]:
    """便捷函数：文本转向量"""
    service = await get_embedding_service()
    return await service.text_to_vector(text)


async def texts_to_embeddings(texts: List[str]) -> List[List[float]]:
    """便捷函数：批量文本转向量"""
    service = await get_embedding_service()
    return await service.batch_text_to_vectors(texts)