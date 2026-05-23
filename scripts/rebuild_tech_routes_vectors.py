"""
重建 tech_routes 向量数据
使用 text-embedding-v4 模型重新生成所有有文本记录的向量
"""
import sys
import os
import pickle
import time
import asyncio
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pymilvus import MilvusClient
from backend.app.core.config import settings
from backend.app.services.embedding_service import EmbeddingService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MILVUS_URI = settings.MILVUS_URI
MILVUS_DATABASE = settings.MILVUS_DATABASE
EMBEDDING_DIM = settings.EMBEDDING_DIM

BASE_DIR = r"E:\武汉工作\00.高温超导\深度推理方法"
TR_PKL = os.path.join(BASE_DIR, "technical_route.pkl")


async def rebuild_tech_routes():
    """重建 tech_routes 的向量数据"""
    logger.info("=" * 60)
    logger.info("tech_routes 向量重建脚本")
    logger.info(f"嵌入模型: {settings.EMBEDDING_MODEL}, 维度: {EMBEDDING_DIM}")
    logger.info("=" * 60)

    # 加载 pkl 数据
    with open(TR_PKL, "rb") as f:
        pkl_data = pickle.load(f)
    logger.info(f"pkl 记录数: {len(pkl_data)}")

    # 分离有文本和无文本的记录
    has_text_records = [r for r in pkl_data if r.get("techroutes", "")]
    no_text_records = [r for r in pkl_data if not r.get("techroutes", "")]
    logger.info(f"有文本: {len(has_text_records)}, 无文本: {len(no_text_records)}")

    # 初始化 EmbeddingService
    embedding_service = EmbeddingService()
    logger.info(f"EmbeddingService 初始化完成，模型: {embedding_service.embedding_model}")

    # 连接 Milvus
    client = MilvusClient(uri=MILVUS_URI)
    client.use_database(MILVUS_DATABASE)
    logger.info(f"已连接 Milvus: {MILVUS_URI}/{MILVUS_DATABASE}")

    # 删除全部现有记录
    logger.info("删除 tech_routes 中全部记录...")
    try:
        client.delete(collection_name="tech_routes", filter="id >= 0")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"删除警告: {e}")

    # 为有文本的记录重新生成向量
    logger.info(f"开始为 {len(has_text_records)} 条记录生成向量...")
    texts = [r.get("techroutes", "") for r in has_text_records]
    vectors = await embedding_service.batch_text_to_vectors(texts, batch_size=6)
    logger.info(f"向量生成完成，共 {len(vectors)} 条")

    # 批量插入有文本的记录（带新向量）
    batch_size = 100
    current_time = int(time.time())
    inserted = 0

    for i in range(0, len(has_text_records), batch_size):
        batch = has_text_records[i:i + batch_size]
        batch_vectors = vectors[i:i + batch_size]
        batch_records = []

        for j, record in enumerate(batch):
            doi = str(record.get("doi", ""))[:256]
            text = record.get("techroutes", "")
            text_bytes = text.encode("utf-8")
            if len(text_bytes) > 4096:
                text = text_bytes[:4096].decode("utf-8", errors="ignore")

            batch_records.append({
                "doi": doi,
                "title": "",
                "techroute_text": text,
                "embedding": batch_vectors[j],
                "embedding_time": current_time,
            })

        try:
            result = client.insert(
                collection_name="tech_routes",
                data=batch_records,
            )
            count = result.get("insert_count", len(batch_records))
            inserted += max(count, len(batch_records))
            logger.info(f"  [{min(i + batch_size, len(has_text_records))}/{len(has_text_records)}] 插入 {len(batch_records)} 条")
        except Exception as e:
            logger.error(f"  [{i}-{i + batch_size}] 插入失败: {e}")

    # 批量插入无文本的记录（零向量）
    logger.info(f"开始插入 {len(no_text_records)} 条无文本记录...")
    for i in range(0, len(no_text_records), batch_size):
        batch = no_text_records[i:i + batch_size]
        batch_records = []

        for record in batch:
            doi = str(record.get("doi", ""))[:256]
            batch_records.append({
                "doi": doi,
                "title": "",
                "techroute_text": "",
                "embedding": [0.0] * EMBEDDING_DIM,
                "embedding_time": current_time,
            })

        try:
            result = client.insert(
                collection_name="tech_routes",
                data=batch_records,
            )
            count = result.get("insert_count", len(batch_records))
            inserted += max(count, len(batch_records))
            logger.info(f"  [{min(i + batch_size, len(no_text_records))}/{len(no_text_records)}] 插入 {len(batch_records)} 条")
        except Exception as e:
            logger.error(f"  [{i}-{i + batch_size}] 插入失败: {e}")

    logger.info(f"总插入: {inserted} 条")

    # 验证
    logger.info("\n验证结果:")
    stats = client.get_collection_stats("tech_routes")
    non_empty = client.query(
        collection_name="tech_routes",
        filter="techroute_text != \"\"",
        limit=10000,
        output_fields=["id"],
    )
    logger.info(f"  tech_routes: 总数={stats.get('row_count', 0)}, 文本非空={len(non_empty)}")

    await embedding_service.close()
    client.close()
    logger.info("=" * 60)
    logger.info("tech_routes 向量重建完成！")


if __name__ == "__main__":
    asyncio.run(rebuild_tech_routes())