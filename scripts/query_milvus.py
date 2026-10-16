"""
Milvus 数据库数据查询脚本
用于查询 Milvus 向量数据库中各 Collection 的数据统计和内容
"""
import sys
import os

# 添加 backend 到路径，以便使用项目配置
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pymilvus import MilvusClient

# Milvus 连接配置
MILVUS_URI = "http://localhost:19530"
MILVUS_DB = "scipdf"

# 已知的 Collection 名称
KNOWN_COLLECTIONS = [
    "paper_embeddings",
    "entity_embeddings",
    "sentence_embeddings",
    "tech_routes",
    "exp_schemes",
]


def connect_milvus():
    """连接 Milvus 数据库"""
    client = MilvusClient(uri=MILVUS_URI)
    print(f"[成功] 已连接到 Milvus: {MILVUS_URI}")

    # 列出所有数据库
    databases = client.list_databases()
    print(f"[信息] 数据库列表: {databases}")

    # 切换到目标数据库
    if MILVUS_DB in databases:
        client.use_database(MILVUS_DB)
        print(f"[成功] 已切换到数据库: {MILVUS_DB}")
    else:
        print(f"[警告] 数据库 {MILVUS_DB} 不存在，使用默认数据库")

    return client


def list_all_collections(client: MilvusClient):
    """列出所有 Collection"""
    collections = client.list_collections()
    print(f"\n{'='*60}")
    print(f"[信息] 共有 {len(collections)} 个 Collection:")
    for c in collections:
        print(f"  - {c}")
    return collections


def get_collection_stats(client: MilvusClient, collection_name: str):
    """获取 Collection 统计信息"""
    try:
        stats = client.get_collection_stats(collection_name)
        row_count = stats.get("row_count", 0)
        print(f"\n  Collection: {collection_name}")
        print(f"  数据行数: {row_count}")
        return row_count
    except Exception as e:
        print(f"\n  Collection: {collection_name}")
        print(f"  [错误] 获取统计失败: {e}")
        return 0


def query_sample_data(client: MilvusClient, collection_name: str, limit: int = 5):
    """查询 Collection 中的样本数据（非向量字段）"""
    print(f"\n  --- {collection_name} 样本数据 (最多{limit}条) ---")
    try:
        # 使用 Query API 获取数据（不含向量字段）
        results = client.query(
            collection_name=collection_name,
            filter="",  # 空过滤表示获取所有数据
            limit=limit,
            output_fields=["*"],
        )
        if results:
            for i, row in enumerate(results):
                # 过滤掉向量字段（太长不显示）
                display_row = {}
                for k, v in row.items():
                    if isinstance(v, list) and len(v) > 10:
                        display_row[k] = f"<向量: 维度{len(v)}>"
                    else:
                        display_row[k] = v
                print(f"  记录 {i+1}: {display_row}")
        else:
            print("  无数据")
    except Exception as e:
        print(f"  查询失败: {e}")


def query_with_filter(client: MilvusClient, collection_name: str, filter_expr: str, limit: int = 10):
    """使用过滤条件查询数据"""
    print(f"\n  过滤条件: {filter_expr}")
    try:
        results = client.query(
            collection_name=collection_name,
            filter=filter_expr,
            limit=limit,
            output_fields=["*"],
        )
        if results:
            for i, row in enumerate(results):
                display_row = {}
                for k, v in row.items():
                    if isinstance(v, list) and len(v) > 10:
                        display_row[k] = f"<向量: 维度{len(v)}>"
                    else:
                        display_row[k] = v
                print(f"  记录 {i+1}: {display_row}")
        else:
            print("  无匹配数据")
    except Exception as e:
        print(f"  查询失败: {e}")


def query_by_id(client: MilvusClient, collection_name: str, ids: list):
    """按主键 ID 查询"""
    print(f"\n  按ID查询 {collection_name}: {ids}")
    try:
        results = client.query(
            collection_name=collection_name,
            filter="",
            limit=len(ids),
            output_fields=["*"],
        )
        # 手动过滤 ID
        matched = [r for r in results if r.get("id") in ids]
        if matched:
            for row in matched:
                display_row = {}
                for k, v in row.items():
                    if isinstance(v, list) and len(v) > 10:
                        display_row[k] = f"<向量: 维度{len(v)}>"
                    else:
                        display_row[k] = v
                print(f"  {display_row}")
        else:
            print("  未找到匹配记录")
    except Exception as e:
        print(f"  查询失败: {e}")


def main():
    print("=" * 60)
    print("Milvus 数据库数据查询工具")
    print("=" * 60)

    # 连接
    client = connect_milvus()

    # 列出所有 Collection
    collections = list_all_collections(client)

    if not collections:
        print("\n[结果] 没有找到任何 Collection")
        return

    # 获取每个 Collection 的统计信息和样本数据
    for coll_name in collections:
        row_count = get_collection_stats(client, coll_name)
        if row_count > 0:
            query_sample_data(client, coll_name, limit=3)

    print("\n" + "=" * 60)
    print("[完成] 数据查询结束")
    print("[提示] 如需按条件查询，请在脚本中修改过滤条件后重新运行")
    print("=" * 60)

    return client


if __name__ == "__main__":
    client = main()
