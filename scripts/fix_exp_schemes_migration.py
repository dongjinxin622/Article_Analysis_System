"""
修复 exp_schemes Collection 中的文本数据
从 experimemtal_scheme.pkl 重新迁移 expscheme_text 到 Milvus
"""
import sys
import os
import pickle
import time
import logging

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pymilvus import MilvusClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 配置
MILVUS_URI = "http://localhost:19530"
MILVUS_DATABASE = "scipdf"
COLLECTION_NAME = "exp_schemes"
EMBEDDING_DIM = 1024

# .pkl 文件路径
PKL_PATH = r"data\深度推理方法\experimemtal_scheme.pkl"


def connect_milvus():
    """连接 Milvus 数据库"""
    client = MilvusClient(uri=MILVUS_URI)
    client.use_database(MILVUS_DATABASE)
    logger.info(f"已连接 Milvus: {MILVUS_URI}, 数据库: {MILVUS_DATABASE}")
    return client


def load_pkl_data(pkl_path):
    """加载 .pkl 文件中的实验方案数据"""
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)
    logger.info(f"从 .pkl 加载了 {len(data)} 条记录")
    return data


def prepare_batch_data(pkl_records, batch_start, batch_end):
    """准备一批插入数据"""
    batch_data = []
    current_time = int(time.time())

    for record in pkl_records[batch_start:batch_end]:
        doi = str(record.get("doi", ""))[:256]
        expscheme_text = str(record.get("expscheme", ""))
        vector = record.get("vector", [])

        # 文本按字节截断到 4096（Milvus VARCHAR 限制）
        if expscheme_text:
            text_bytes = expscheme_text.encode("utf-8")
            if len(text_bytes) > 4096:
                expscheme_text = text_bytes[:4096].decode("utf-8", errors="ignore")

        # 向量处理
        if not isinstance(vector, list) or len(vector) == 0:
            vector = [0.0] * EMBEDDING_DIM
        elif len(vector) < EMBEDDING_DIM:
            vector = vector + [0.0] * (EMBEDDING_DIM - len(vector))
        elif len(vector) > EMBEDDING_DIM:
            vector = vector[:EMBEDDING_DIM]

        batch_data.append({
            "doi": doi if doi else "",
            "title": "",
            "expscheme_text": expscheme_text,
            "categories_json": "[]",
            "embedding": vector,
            "embedding_time": current_time,
        })

    return batch_data


def main():
    logger.info("=" * 60)
    logger.info("exp_schemes 文本数据修复脚本")
    logger.info("=" * 60)

    # 1. 连接 Milvus
    client = connect_milvus()

    # 2. 检查当前状态
    stats_before = client.get_collection_stats(COLLECTION_NAME)
    logger.info(f"修复前记录数: {stats_before.get('row_count', 0)}")

    # 3. 加载 .pkl 数据
    pkl_data = load_pkl_data(PKL_PATH)
    total = len(pkl_data)

    # 统计 .pkl 中文本非空数量
    non_empty_count = sum(1 for r in pkl_data if r.get("expscheme", "").strip())
    logger.info(f".pkl 中文本非空记录: {non_empty_count}/{total}")

    # 4. 删除全部现有记录
    logger.info("删除 exp_schemes 中全部现有记录...")
    try:
        client.delete(collection_name=COLLECTION_NAME, filter="id >= 0")
        logger.info("删除完成，等待清理...")
        time.sleep(2)
    except Exception as e:
        logger.warning(f"删除操作警告: {e}")

    # 验证删除
    stats_after_delete = client.get_collection_stats(COLLECTION_NAME)
    logger.info(f"删除后记录数: {stats_after_delete.get('row_count', 0)}")

    # 5. 批量重新插入
    batch_size = 100
    success_count = 0
    fail_count = 0

    for i in range(0, total, batch_size):
        batch_end = min(i + batch_size, total)
        batch_data = prepare_batch_data(pkl_data, i, batch_end)

        try:
            result = client.insert(
                collection_name=COLLECTION_NAME,
                data=batch_data,
            )
            inserted = result.get("insert_count", len(batch_data))
            success_count += inserted
            logger.info(f"[{batch_end}/{total}] 插入 {inserted} 条")
        except Exception as e:
            logger.error(f"[{i}-{batch_end}] 批量插入失败: {e}")
            fail_count += len(batch_data)

    # 6. 验证最终状态
    logger.info("\n" + "=" * 60)
    logger.info("验证修复结果")
    stats_after = client.get_collection_stats(COLLECTION_NAME)
    logger.info(f"修复后总记录数: {stats_after.get('row_count', 0)}")

    # 查询非空文本数量
    try:
        non_empty_results = client.query(
            collection_name=COLLECTION_NAME,
            filter='expscheme_text != ""',
            limit=10000,
            output_fields=["id"],
        )
        logger.info(f"expscheme_text 非空记录数: {len(non_empty_results)}")
    except Exception as e:
        logger.warning(f"非空验证查询失败: {e}")

    # 抽样展示
    logger.info("\n抽样展示（前3条）：")
    samples = client.query(
        collection_name=COLLECTION_NAME,
        filter='expscheme_text != ""',
        limit=3,
        output_fields=["doi", "expscheme_text"],
    )
    for i, s in enumerate(samples):
        text = s.get("expscheme_text", "")
        doi = s.get("doi", "")
        if len(text) > 200:
            text = text[:200] + "..."
        logger.info(f"  [{i+1}] DOI={doi}")
        logger.info(f"      文本={text}")

    # 7. 总结
    logger.info("\n" + "=" * 60)
    logger.info("修复完成！")
    logger.info(f"成功插入: {success_count}")
    logger.info(f"失败: {fail_count}")
    logger.info("=" * 60)

    client.close()
    return success_count > 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
