"""
Milvus 向量数据库服务
负责 Collection 创建、向量存储、检索等功能
"""
import logging
from typing import List, Dict, Any, Optional
from pymilvus import (
    MilvusClient,
    Collection,
    FieldSchema,
    CollectionSchema,
    DataType,
    utility
)

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class MilvusService:
    """Milvus 向量数据库服务"""

    def __init__(
        self,
        uri: str = None,
        db_name: str = None
    ):
        """
        初始化 Milvus 服务

        Args:
            uri: Milvus 连接 URI
            db_name: 数据库名称
        """
        self.uri = uri or settings.MILVUS_URI
        self.db_name = db_name or settings.MILVUS_DATABASE
        self.dimensions = settings.EMBEDDING_DIM

        # 连接 Milvus
        self.client = MilvusClient(uri=self.uri)
        logger.info(f"Milvus 连接成功: {self.uri}")

        # 确保数据库存在
        self._ensure_database()

    def _ensure_database(self):
        """确保数据库存在"""
        try:
            # 检查数据库是否存在（兼容旧版本 Milvus）
            try:
                databases = self.client.list_databases()
                if self.db_name not in databases:
                    self.client.create_database(self.db_name)
                    logger.info(f"创建数据库: {self.db_name}")
            except Exception as db_err:
                logger.warning(f"数据库列表检查失败: {db_err}，尝试直接使用数据库")

            # 切换到目标数据库
            self.client.use_database(self.db_name)
            logger.info(f"切换到数据库: {self.db_name}")
        except Exception as e:
            logger.warning(f"数据库操作警告: {e}")

    def create_paper_collection(
        self,
        collection_name: str = None,
        dimensions: int = None
    ) -> bool:
        """
        创建论文向量 Collection

        Schema:
        - id: 主键 (自增 INT64)
        - result_id: 论文结果 ID (VARCHAR)
        - doi: DOI (VARCHAR)
        - title: 标题向量 (FLOAT_VECTOR)
        - abstract: 摘要向量 (FLOAT_VECTOR)
        - embedding_time: 创建时间 (INT64)

        Args:
            collection_name: Collection 名称
            dimensions: 向量维度

        Returns:
            是否成功
        """
        name = collection_name or settings.MILVUS_COLLECTION_PAPER
        dims = dimensions or self.dimensions

        try:
            # 检查是否已存在
            if self.client.has_collection(name):
                logger.info(f"Collection {name} 已存在")
                return True

            # 创建 Collection Schema
            schema = self.client.create_schema(
                auto_id=True,
                enable_dynamic_field=True
            )

            schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
            schema.add_field("result_id", DataType.VARCHAR, max_length=256)
            schema.add_field("doi", DataType.VARCHAR, max_length=256)
            schema.add_field("title_embedding", DataType.FLOAT_VECTOR, dim=dims)
            schema.add_field("abstract_embedding", DataType.FLOAT_VECTOR, dim=dims)
            schema.add_field("embedding_time", DataType.INT64)

            # 创建索引参数
            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="title_embedding",
                metric_type="COSINE",
                index_type="AUTOINDEX"
            )
            index_params.add_index(
                field_name="abstract_embedding",
                metric_type="COSINE",
                index_type="AUTOINDEX"
            )

            # 创建 Collection
            self.client.create_collection(
                collection_name=name,
                schema=schema,
                index_params=index_params
            )

            logger.info(f"Collection {name} 创建成功，维度: {dims}")
            return True

        except Exception as e:
            logger.error(f"创建 Collection {name} 失败: {e}")
            return False

    def create_entity_collection(
        self,
        collection_name: str = None,
        dimensions: int = None
    ) -> bool:
        """
        创建实体向量 Collection

        Schema:
        - id: 主键
        - ner_id: NER 结果 ID
        - entity_type: 实体类型
        - entity_text: 实体文本
        - embedding: 实体向量
        - result_id: 论文结果 ID
        - section_idx: 章节索引
        - group_idx: 组索引

        Args:
            collection_name: Collection 名称
            dimensions: 向量维度

        Returns:
            是否成功
        """
        name = collection_name or settings.MILVUS_COLLECTION_ENTITY
        dims = dimensions or self.dimensions

        try:
            if self.client.has_collection(name):
                logger.info(f"Collection {name} 已存在")
                return True

            schema = self.client.create_schema(
                auto_id=True,
                enable_dynamic_field=True
            )

            schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
            schema.add_field("ner_id", DataType.VARCHAR, max_length=256)
            schema.add_field("result_id", DataType.VARCHAR, max_length=256)
            schema.add_field("entity_type", DataType.VARCHAR, max_length=128)
            schema.add_field("entity_text", DataType.VARCHAR, max_length=1024)
            schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dims)
            schema.add_field("section_idx", DataType.INT64)
            schema.add_field("group_idx", DataType.INT64)
            schema.add_field("embedding_time", DataType.INT64)

            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                metric_type="COSINE",
                index_type="AUTOINDEX"
            )

            self.client.create_collection(
                collection_name=name,
                schema=schema,
                index_params=index_params
            )

            logger.info(f"Collection {name} 创建成功")
            return True

        except Exception as e:
            logger.error(f"创建 Collection {name} 失败: {e}")
            return False

    def create_sentence_collection(
        self,
        collection_name: str = None,
        dimensions: int = None
    ) -> bool:
        """
        创建句子向量 Collection

        Schema:
        - id: 主键
        - result_id: 论文结果 ID
        - sentence_text: 句子文本
        - embedding: 句子向量
        - section_idx: 章节索引
        - group_idx: 组索引

        Args:
            collection_name: Collection 名称
            dimensions: 向量维度

        Returns:
            是否成功
        """
        name = collection_name or settings.MILVUS_COLLECTION_SENTENCE
        dims = dimensions or self.dimensions

        try:
            if self.client.has_collection(name):
                logger.info(f"Collection {name} 已存在")
                return True

            schema = self.client.create_schema(
                auto_id=True,
                enable_dynamic_field=True
            )

            schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
            schema.add_field("result_id", DataType.VARCHAR, max_length=256)
            schema.add_field("sentence_text", DataType.VARCHAR, max_length=4096)
            schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=dims)
            schema.add_field("section_idx", DataType.INT64)
            schema.add_field("group_idx", DataType.INT64)
            schema.add_field("heading", DataType.VARCHAR, max_length=256)
            schema.add_field("embedding_time", DataType.INT64)

            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                metric_type="COSINE",
                index_type="AUTOINDEX"
            )

            self.client.create_collection(
                collection_name=name,
                schema=schema,
                index_params=index_params
            )

            logger.info(f"Collection {name} 创建成功")
            return True

        except Exception as e:
            logger.error(f"创建 Collection {name} 失败: {e}")
            return False

    def init_all_collections(self) -> bool:
        """初始化所有 Collection"""
        results = []
        results.append(self.create_paper_collection())
        results.append(self.create_entity_collection())
        results.append(self.create_sentence_collection())

        if all(results):
            logger.info("所有 Collection 初始化成功")
            return True
        else:
            logger.warning("部分 Collection 初始化失败")
            return False

    def insert_paper_embedding(
        self,
        result_id: str,
        collection_name: str = None,
        doi: str = None,
        title_embedding: List[float] = None,
        abstract_embedding: List[float] = None
    ) -> Dict[str, Any]:
        """
        插入论文向量

        Args:
            collection_name: Collection 名称
            result_id: 论文结果 ID
            doi: DOI
            title_embedding: 标题向量
            abstract_embedding: 摘要向量

        Returns:
            插入结果
        """
        name = collection_name or settings.MILVUS_COLLECTION_PAPER

        import time
        data = {
            "result_id": result_id,
            "doi": doi or "",
            "title_embedding": title_embedding or [0.0] * self.dimensions,
            "abstract_embedding": abstract_embedding or [0.0] * self.dimensions,
            "embedding_time": int(time.time())
        }

        try:
            result = self.client.insert(
                collection_name=name,
                data=[data]
            )
            logger.info(f"论文向量插入成功: {result_id}")
            return {"success": True, "insert_count": result.get("insert_count", 0)}
        except Exception as e:
            logger.error(f"论文向量插入失败: {e}")
            return {"success": False, "error": str(e)}

    def insert_entity_embeddings(
        self,
        ner_id: str,
        result_id: str,
        entities: List[Dict[str, Any]],
        embeddings: List[List[float]],
        collection_name: str = None
    ) -> Dict[str, Any]:
        """
        批量插入实体向量

        Args:
            collection_name: Collection 名称
            ner_id: NER 结果 ID
            result_id: 论文结果 ID
            entities: 实体列表（包含 entity_type, entity_text, section_idx, group_idx）
            embeddings: 向量列表

        Returns:
            插入结果
        """
        name = collection_name or settings.MILVUS_COLLECTION_ENTITY

        import time
        current_time = int(time.time())

        data = []
        for i, entity in enumerate(entities):
            item = {
                "ner_id": ner_id,
                "result_id": result_id,
                "entity_type": entity.get("entity_type", ""),
                "entity_text": entity.get("entity_text", ""),
                "embedding": embeddings[i] if i < len(embeddings) else [0.0] * self.dimensions,
                "section_idx": entity.get("section_idx", 0),
                "group_idx": entity.get("group_idx", 0),
                "embedding_time": current_time
            }
            data.append(item)

        try:
            result = self.client.insert(
                collection_name=name,
                data=data
            )
            logger.info(f"实体向量批量插入成功: {ner_id}, 数量: {len(data)}")
            return {"success": True, "insert_count": result.get("insert_count", 0)}
        except Exception as e:
            logger.error(f"实体向量插入失败: {e}")
            return {"success": False, "error": str(e)}

    def insert_sentence_embeddings(
        self,
        result_id: str,
        sentences: List[Dict[str, Any]],
        embeddings: List[List[float]],
        collection_name: str = None
    ) -> Dict[str, Any]:
        """
        批量插入句子向量

        Args:
            collection_name: Collection 名称
            result_id: 论文结果 ID
            sentences: 句子列表（包含 sentence_text, section_idx, group_idx, heading）
            embeddings: 向量列表

        Returns:
            插入结果
        """
        name = collection_name or settings.MILVUS_COLLECTION_SENTENCE

        import time
        current_time = int(time.time())

        data = []
        for i, sentence in enumerate(sentences):
            item = {
                "result_id": result_id,
                "sentence_text": sentence.get("sentence_text", ""),
                "embedding": embeddings[i] if i < len(embeddings) else [0.0] * self.dimensions,
                "section_idx": sentence.get("section_idx", 0),
                "group_idx": sentence.get("group_idx", 0),
                "heading": sentence.get("heading", ""),
                "embedding_time": current_time
            }
            data.append(item)

        try:
            result = self.client.insert(
                collection_name=name,
                data=data
            )
            logger.info(f"句子向量批量插入成功: {result_id}, 数量: {len(data)}")
            return {"success": True, "insert_count": result.get("insert_count", 0)}
        except Exception as e:
            logger.error(f"句子向量插入失败: {e}")
            return {"success": False, "error": str(e)}

    def search_similar(
        self,
        collection_name: str,
        query_vector: List[float],
        vector_field: str = "vector",
        top_k: int = 10,
        threshold: float = 0.0,
        filter_expr: str = None,
        output_fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        向量相似度搜索

        Args:
            collection_name: Collection 名称
            query_vector: 查询向量
            vector_field: 向量字段名
            top_k: 返回数量
            threshold: 相似度阈值
            filter_expr: 过滤表达式
            output_fields: 返回字段列表

        Returns:
            搜索结果列表
        """
        if output_fields is None:
            output_fields = ["*"]

        try:
            results = self.client.search(
                collection_name=collection_name,
                data=[query_vector],
                anns_field=vector_field,
                limit=top_k,
                filter=filter_expr,
                output_fields=output_fields
            )

            # 处理结果 — Milvus 2.x COSINE metric: distance 值即为 cosine_similarity
            similar_items = []
            for hits in results:
                for hit in hits:
                    distance = hit.get("distance", 0)
                    similarity = distance  # COSINE metric 直接返回相似度值
                    if similarity >= threshold:
                        item = hit.get("entity", {})
                        item["score"] = similarity
                        similar_items.append(item)

            logger.info(f"搜索完成，返回 {len(similar_items)} 条结果")
            return similar_items

        except Exception as e:
            logger.error(f"向量搜索失败: {e}")
            return []

    def search_papers_by_title(
        self,
        query_vector: List[float],
        top_k: int = 10,
        threshold: float = 0.5,
        result_id_filter: str = None
    ) -> List[Dict[str, Any]]:
        """按标题向量搜索论文"""
        filter_expr = None
        if result_id_filter:
            filter_expr = f"result_id == '{result_id_filter}'"

        return self.search_similar(
            collection_name=settings.MILVUS_COLLECTION_PAPER,
            query_vector=query_vector,
            vector_field="title_embedding",
            top_k=top_k,
            threshold=threshold,
            filter_expr=filter_expr,
            output_fields=["result_id", "doi", "embedding_time"]
        )

    def search_papers_by_abstract(
        self,
        query_vector: List[float],
        top_k: int = 10,
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """按摘要向量搜索论文"""
        return self.search_similar(
            collection_name=settings.MILVUS_COLLECTION_PAPER,
            query_vector=query_vector,
            vector_field="abstract_embedding",
            top_k=top_k,
            threshold=threshold,
            output_fields=["result_id", "doi", "embedding_time"]
        )

    def search_entities(
        self,
        query_vector: List[float],
        entity_type_filter: str = None,
        top_k: int = 10,
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """搜索相似实体"""
        filter_expr = None
        if entity_type_filter:
            filter_expr = f"entity_type == '{entity_type_filter}'"

        return self.search_similar(
            collection_name=settings.MILVUS_COLLECTION_ENTITY,
            query_vector=query_vector,
            vector_field="embedding",
            top_k=top_k,
            threshold=threshold,
            filter_expr=filter_expr,
            output_fields=["ner_id", "result_id", "entity_type", "entity_text", "section_idx", "group_idx"]
        )

    def search_sentences(
        self,
        query_vector: List[float],
        result_id_filter: str = None,
        top_k: int = 10,
        threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """搜索相似句子"""
        filter_expr = None
        if result_id_filter:
            filter_expr = f"result_id == '{result_id_filter}'"

        return self.search_similar(
            collection_name=settings.MILVUS_COLLECTION_SENTENCE,
            query_vector=query_vector,
            vector_field="embedding",
            top_k=top_k,
            threshold=threshold,
            filter_expr=filter_expr,
            output_fields=["result_id", "sentence_text", "section_idx", "group_idx", "heading"]
        )

    def delete_by_result_id(
        self,
        collection_name: str,
        result_id: str
    ) -> bool:
        """按 result_id 删除向量"""
        try:
            self.client.delete(
                collection_name=collection_name,
                filter=f"result_id == '{result_id}'"
            )
            logger.info(f"删除 {collection_name} 中 result_id={result_id} 的向量")
            return True
        except Exception as e:
            logger.error(f"删除向量失败: {e}")
            return False

    def delete_by_ner_id(
        self,
        collection_name: str,
        ner_id: str
    ) -> bool:
        """按 ner_id 删除向量"""
        try:
            self.client.delete(
                collection_name=collection_name,
                filter=f"ner_id == '{ner_id}'"
            )
            logger.info(f"删除 {collection_name} 中 ner_id={ner_id} 的向量")
            return True
        except Exception as e:
            logger.error(f"删除向量失败: {e}")
            return False

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """获取 Collection 统计信息"""
        try:
            stats = self.client.get_collection_stats(collection_name)
            return stats
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}

    def list_collections(self) -> List[str]:
        """列出所有 Collection"""
        try:
            return self.client.list_collections()
        except Exception as e:
            logger.error(f"列出 Collection 失败: {e}")
            return []

    def close(self):
        """关闭连接"""
        try:
            self.client.close()
            logger.info("Milvus 连接已关闭")
        except Exception as e:
            logger.warning(f"关闭连接警告: {e}")


# 全局 Milvus 服务实例（懒加载）
_milvus_service: Optional[MilvusService] = None


def get_milvus_service() -> MilvusService:
    """获取 Milvus 服务实例"""
    global _milvus_service
    if _milvus_service is None:
        _milvus_service = MilvusService()
    return _milvus_service


def init_milvus_collections() -> bool:
    """初始化所有 Milvus Collection"""
    service = get_milvus_service()
    return service.init_all_collections()