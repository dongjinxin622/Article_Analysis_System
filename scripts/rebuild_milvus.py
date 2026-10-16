"""
综合清理并重建 Milvus exp_schemes 和 tech_routes
从已合并的本地 .pkl 文件全量重新导入
"""
import sys
import os
import pickle
import time
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from pymilvus import MilvusClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MILVUS_URI = "http://localhost:19530"
MILVUS_DATABASE = "scipdf"
EMBEDDING_DIM = 1024

BASE_DIR = r"data\深度推理方法"
EXP_PKL = os.path.join(BASE_DIR, "experimemtal_scheme.pkl")
TR_PKL = os.path.join(BASE_DIR, "technical_route.pkl")


def load_pkl(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def create_collection_if_needed(client, collection_name, data_type):
    """创建 Collection（如果不存在）"""
    from pymilvus import DataType

    if client.has_collection(collection_name):
        logger.info(f"  Collection {collection_name} 已存在")
        return

    logger.info(f"  创建 Collection {collection_name}...")
    schema = client.create_schema(auto_id=True, enable_dynamic_field=True)

    schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
    schema.add_field("doi", DataType.VARCHAR, max_length=256)
    schema.add_field("title", DataType.VARCHAR, max_length=512)

    if data_type == "exp_scheme":
        schema.add_field("expscheme_text", DataType.VARCHAR, max_length=4096)
        schema.add_field("categories_json", DataType.VARCHAR, max_length=1024)
    else:
        schema.add_field("techroute_text", DataType.VARCHAR, max_length=4096)

    schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
    schema.add_field("embedding_time", DataType.INT64)

    index_params = client.prepare_index_params()
    index_params.add_index(
        field_name="embedding",
        metric_type="COSINE",
        index_type="AUTOINDEX",
    )

    client.create_collection(
        collection_name=collection_name,
        schema=schema,
        index_params=index_params,
    )
    logger.info(f"  Collection {collection_name} 创建成功")


def rebuild_collection(client, collection_name, pkl_data, data_type):
    """删除全部记录并重新插入"""
    # 1. 删除全部
    logger.info(f"  删除 {collection_name} 中全部记录...")
    try:
        client.delete(collection_name=collection_name, filter="id >= 0")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"  删除警告: {e}")

    stats = client.get_collection_stats(collection_name)
    logger.info(f"  删除后: {stats.get('row_count', 0)} 条")

    # 2. 批量插入
    batch_size = 100
    total = len(pkl_data)
    inserted = 0
    current_time = int(time.time())

    for i in range(0, total, batch_size):
        batch = pkl_data[i : i + batch_size]
        batch_records = []

        for record in batch:
            doi = str(record.get("doi", ""))[:256]

            if data_type == "exp_scheme":
                text = str(record.get("expscheme", ""))
                text_field = "expscheme_text"
            else:
                text = str(record.get("techroutes", ""))
                text_field = "techroute_text"

            if text:
                text_bytes = text.encode("utf-8")
                if len(text_bytes) > 4096:
                    text = text_bytes[:4096].decode("utf-8", errors="ignore")

            vector = record.get("vector", [])
            if not isinstance(vector, list) or len(vector) == 0:
                vector = [0.0] * EMBEDDING_DIM
            elif len(vector) < EMBEDDING_DIM:
                vector = vector + [0.0] * (EMBEDDING_DIM - len(vector))
            elif len(vector) > EMBEDDING_DIM:
                vector = vector[:EMBEDDING_DIM]

            rec = {
                "doi": doi,
                "title": "",
                text_field: text,
                "embedding": vector,
                "embedding_time": current_time,
            }
            if data_type == "exp_scheme":
                rec["categories_json"] = "[]"

            batch_records.append(rec)

        try:
            result = client.insert(
                collection_name=collection_name,
                data=batch_records,
            )
            count = result.get("insert_count", len(batch_records))
            if count == 0:
                # 可能 insert_count 字段为 0，手动计入
                count = len(batch_records)
            inserted += count
            logger.info(f"  [{min(i+batch_size, total)}/{total}] 插入 {count} 条")
        except Exception as e:
            logger.error(f"  [{i}-{i+batch_size}] 插入失败: {e}")

    return inserted


def main():
    logger.info("=" * 60)
    logger.info("Milvus 全量重建脚本")
    logger.info("=" * 60)

    client = MilvusClient(uri=MILVUS_URI)
    client.use_database(MILVUS_DATABASE)
    logger.info(f"已连接 Milvus: {MILVUS_URI}/{MILVUS_DATABASE}")

    # 重建 exp_schemes
    logger.info("\n[1/2] 重建 exp_schemes...")
    create_collection_if_needed(client, "exp_schemes", "exp_scheme")
    exp_data = load_pkl(EXP_PKL)
    logger.info(f"  .pkl 记录数: {len(exp_data)}")
    n_exp = rebuild_collection(client, "exp_schemes", exp_data, "exp_scheme")
    logger.info(f"  exp_schemes 重建完成: {n_exp} 条")

    # 重建 tech_routes
    logger.info("\n[2/2] 重建 tech_routes...")
    create_collection_if_needed(client, "tech_routes", "tech_route")
    tr_data = load_pkl(TR_PKL)
    logger.info(f"  .pkl 记录数: {len(tr_data)}")
    n_tr = rebuild_collection(client, "tech_routes", tr_data, "tech_route")
    logger.info(f"  tech_routes 重建完成: {n_tr} 条")

    # 验证
    logger.info("\n" + "=" * 60)
    logger.info("验证结果:")
    for col in ["exp_schemes", "tech_routes"]:
        stats = client.get_collection_stats(col)
        text_field = "expscheme_text" if col == "exp_schemes" else "techroute_text"
        try:
            non_empty = client.query(
                collection_name=col,
                filter=f'{text_field} != ""',
                limit=10000,
                output_fields=["id"],
            )
            ne_count = len(non_empty)
        except:
            ne_count = "?"
        logger.info(f"  {col}: 总数={stats.get('row_count', 0)}, 文本非空={ne_count}")

    client.close()
    logger.info("=" * 60)
    logger.info("全量重建完成！")


if __name__ == "__main__":
    main()
