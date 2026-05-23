"""
Deep Reasoning 数据迁移脚本

从 v2 SQLite 数据库迁移到 v3 云端：
- tech_routes/exp_schemes 向量 → Milvus
- jc_indices → MySQL
"""
import os
import sys
import pickle
import sqlite3
import json
import time
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 项目路径
V3_ROOT = Path(__file__).resolve().parent.parent.parent
V2_ROOT = V3_ROOT.parent / "Article_Analysis_System_v2"

# 数据库路径
V2_SQLITE_PATH = V2_ROOT / "data" / "REBCO_database" / "rebco.db"

# 云端配置
MILVUS_URI = "http://8.147.69.101:19530"
MILVUS_DATABASE = "scipdf"
MYSQL_HOST = "8.147.69.101"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "Djx3861599!"
MYSQL_DATABASE = "article_analysis_v3"

# 向量维度
EMBEDDING_DIM = 1024


def connect_v2_sqlite() -> sqlite3.Connection:
    """连接 v2 SQLite 数据库"""
    logger.info(f"连接 v2 SQLite: {V2_SQLITE_PATH}")
    conn = sqlite3.connect(str(V2_SQLITE_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def connect_milvus():
    """连接云端 Milvus"""
    from pymilvus import MilvusClient, DataType
    logger.info(f"连接 Milvus: {MILVUS_URI}")
    client = MilvusClient(uri=MILVUS_URI)
    client.use_database(MILVUS_DATABASE)
    return client, DataType


def connect_mysql():
    """连接云端 MySQL"""
    import pymysql
    logger.info(f"连接 MySQL: {MYSQL_HOST}")
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4'
    )
    return conn


def create_tech_routes_collection(client, DataType):
    """创建 tech_routes Collection"""
    collection_name = "tech_routes"

    if client.has_collection(collection_name):
        logger.info(f"Collection {collection_name} 已存在")
        return True

    logger.info(f"创建 Collection {collection_name}")

    try:
        schema = client.create_schema(
            auto_id=True,
            enable_dynamic_field=True
        )

        schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field("doi", DataType.VARCHAR, max_length=256)
        schema.add_field("title", DataType.VARCHAR, max_length=512)
        schema.add_field("techroute_text", DataType.VARCHAR, max_length=4096)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        schema.add_field("embedding_time", DataType.INT64)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            metric_type="COSINE",
            index_type="AUTOINDEX"
        )

        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params
        )

        logger.info(f"Collection {collection_name} 创建成功")
        return True

    except Exception as e:
        logger.error(f"创建 Collection {collection_name} 失败: {e}")
        return False


def create_exp_schemes_collection(client, DataType):
    """创建 exp_schemes Collection"""
    collection_name = "exp_schemes"

    if client.has_collection(collection_name):
        logger.info(f"Collection {collection_name} 已存在")
        return True

    logger.info(f"创建 Collection {collection_name}")

    try:
        schema = client.create_schema(
            auto_id=True,
            enable_dynamic_field=True
        )

        schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field("doi", DataType.VARCHAR, max_length=256)
        schema.add_field("title", DataType.VARCHAR, max_length=512)
        schema.add_field("expscheme_text", DataType.VARCHAR, max_length=4096)
        schema.add_field("categories_json", DataType.VARCHAR, max_length=1024)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM)
        schema.add_field("embedding_time", DataType.INT64)

        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            metric_type="COSINE",
            index_type="AUTOINDEX"
        )

        client.create_collection(
            collection_name=collection_name,
            schema=schema,
            index_params=index_params
        )

        logger.info(f"Collection {collection_name} 创建成功")
        return True

    except Exception as e:
        logger.error(f"创建 Collection {collection_name} 失败: {e}")
        return False


def migrate_tech_routes(conn_sqlite, client_milvus) -> Tuple[int, int]:
    """
    迁移 tech_routes 向量数据到 Milvus

    Returns:
        (成功数量, 失败数量)
    """
    collection_name = "tech_routes"

    logger.info("开始迁移 tech_routes 数据...")

    cursor = conn_sqlite.cursor()
    cursor.execute('SELECT doi, title, techroutes, vector FROM tech_routes')
    rows = cursor.fetchall()

    total = len(rows)
    logger.info(f"读取 {total} 条 tech_routes 记录")

    success_count = 0
    fail_count = 0
    batch_data = []
    batch_size = 100

    current_time = int(time.time())

    for i, row in enumerate(rows):
        doi = row['doi'] or ''
        title = row['title'] or ''
        techroutes = row['techroutes'] or ''

        # 解析pickle向量
        try:
            if row['vector']:
                vector = pickle.loads(row['vector'])
                if isinstance(vector, list):
                    if len(vector) == EMBEDDING_DIM:
                        # 向量正常，直接使用
                        pass
                    elif len(vector) < EMBEDDING_DIM:
                        # 补零
                        vector = vector + [0.0] * (EMBEDDING_DIM - len(vector))
                    elif len(vector) > EMBEDDING_DIM:
                        # 截断
                        vector = vector[:EMBEDDING_DIM]
                else:
                    vector = [0.0] * EMBEDDING_DIM
            else:
                vector = [0.0] * EMBEDDING_DIM
        except Exception as e:
            logger.warning(f"[{i}] 向量解析失败: {e}")
            vector = [0.0] * EMBEDDING_DIM
            fail_count += 1

        # 确保字符串类型并按字节截断（Milvus VARCHAR按字节计数）
        techroute_str = str(techroutes) if techroutes else ""
        techroute_bytes = techroute_str.encode('utf-8')
        if len(techroute_bytes) > 4096:
            techroute_str = techroute_bytes[:4096].decode('utf-8', errors='ignore')

        batch_data.append({
            "doi": str(doi)[:256] if doi else "",
            "title": str(title)[:512] if title else "",
            "techroute_text": techroute_str,
            "embedding": vector,
            "embedding_time": current_time
        })

        # 批量插入
        if len(batch_data) >= batch_size:
            try:
                result = client_milvus.insert(
                    collection_name=collection_name,
                    data=batch_data
                )
                success_count += len(batch_data)
                logger.info(f"[{i}/{total}] 批量插入 {len(batch_data)} 条")
            except Exception as e:
                logger.error(f"[{i}/{total}] 批量插入失败: {e}")
                fail_count += len(batch_data)

            batch_data = []

    # 插入剩余数据
    if batch_data:
        try:
            result = client_milvus.insert(
                collection_name=collection_name,
                data=batch_data
            )
            success_count += len(batch_data)
            logger.info(f"最后批量插入 {len(batch_data)} 条")
        except Exception as e:
            logger.error(f"最后批量插入失败: {e}")
            fail_count += len(batch_data)

    logger.info(f"tech_routes 迁移完成: 成功 {success_count}, 失败 {fail_count}")
    return success_count, fail_count


def migrate_exp_schemes(conn_sqlite, client_milvus) -> Tuple[int, int]:
    """
    迁移 exp_schemes 向量数据到 Milvus

    Returns:
        (成功数量, 失败数量)
    """
    collection_name = "exp_schemes"

    logger.info("开始迁移 exp_schemes 数据...")

    cursor = conn_sqlite.cursor()
    cursor.execute('SELECT doi, title, exp_scheme_text, categories, vector FROM exp_schemes')
    rows = cursor.fetchall()

    total = len(rows)
    logger.info(f"读取 {total} 条 exp_schemes 记录")

    success_count = 0
    fail_count = 0
    batch_data = []
    batch_size = 100

    current_time = int(time.time())

    for i, row in enumerate(rows):
        doi = row['doi'] or ''
        title = row['title'] or ''
        expscheme_text = row['exp_scheme_text'] or ''

        # 解析categories
        try:
            if row['categories']:
                categories = pickle.loads(row['categories'])
                categories_json = json.dumps(categories) if categories else "[]"
            else:
                categories_json = "[]"
        except:
            categories_json = "[]"

        # 解析pickle向量
        try:
            if row['vector']:
                vector = pickle.loads(row['vector'])
                if isinstance(vector, list):
                    if len(vector) < EMBEDDING_DIM:
                        vector = vector + [0.0] * (EMBEDDING_DIM - len(vector))
                    elif len(vector) > EMBEDDING_DIM:
                        vector = vector[:EMBEDDING_DIM]
                else:
                    vector = [0.0] * EMBEDDING_DIM
            else:
                vector = [0.0] * EMBEDDING_DIM
        except Exception as e:
            logger.warning(f"[{i}] 向量解析失败: {e}")
            vector = [0.0] * EMBEDDING_DIM

        # 确保字符串类型并按字节截断（Milvus VARCHAR按字节计数）
        expscheme_str = str(expscheme_text) if expscheme_text else ""
        expscheme_bytes = expscheme_str.encode('utf-8')
        if len(expscheme_bytes) > 4096:
            expscheme_str = expscheme_bytes[:4096].decode('utf-8', errors='ignore')
        categories_str = categories_json
        categories_bytes = categories_str.encode('utf-8')
        if len(categories_bytes) > 1024:
            categories_str = categories_bytes[:1024].decode('utf-8', errors='ignore')

        batch_data.append({
            "doi": str(doi)[:256] if doi else "",
            "title": str(title)[:512] if title else "",
            "expscheme_text": expscheme_str,
            "categories_json": categories_str,
            "embedding": vector,
            "embedding_time": current_time
        })

        # 批量插入
        if len(batch_data) >= batch_size:
            try:
                result = client_milvus.insert(
                    collection_name=collection_name,
                    data=batch_data
                )
                success_count += len(batch_data)
                logger.info(f"[{i}/{total}] 批量插入 {len(batch_data)} 条")
            except Exception as e:
                logger.error(f"[{i}/{total}] 批量插入失败: {e}")
                fail_count += len(batch_data)

            batch_data = []

    # 插入剩余数据
    if batch_data:
        try:
            client_milvus.insert(
                collection_name=collection_name,
                data=batch_data
            )
            success_count += len(batch_data)
            logger.info(f"最后批量插入 {len(batch_data)} 条")
        except Exception as e:
            logger.error(f"最后批量插入失败: {e}")
            fail_count += len(batch_data)

    logger.info(f"exp_schemes 迁移完成: 成功 {success_count}, 失败 {fail_count}")
    return success_count, fail_count


def create_jc_tables(conn_mysql):
    """创建 Jc 相关 MySQL 表"""
    cursor = conn_mysql.cursor()

    # jc_indices 表
    logger.info("创建 jc_indices 表...")
    create_jc_indices_sql = """
    CREATE TABLE IF NOT EXISTS jc_indices (
        id INT AUTO_INCREMENT PRIMARY KEY,
        doi VARCHAR(255),
        Jc TEXT,
        Jc_unit VARCHAR(50),
        temperature FLOAT,
        temperature_unit VARCHAR(20),
        magneticfield FLOAT,
        magnetic_field_unit VARCHAR(20),
        angle FLOAT,
        angle_unit VARCHAR(20),
        error_bar TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_doi (doi),
        INDEX idx_temp (temperature),
        INDEX idx_field (magneticfield)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    cursor.execute(create_jc_indices_sql)

    # jc_indices_raw 表
    logger.info("创建 jc_indices_raw 表...")
    create_jc_raw_sql = """
    CREATE TABLE IF NOT EXISTS jc_indices_raw (
        id INT AUTO_INCREMENT PRIMARY KEY,
        doi VARCHAR(255),
        raw_text TEXT,
        source_section VARCHAR(255),
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_doi (doi)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    cursor.execute(create_jc_raw_sql)

    conn_mysql.commit()
    logger.info("Jc 表创建完成")


def migrate_jc_indices(conn_sqlite, conn_mysql) -> int:
    """迁移 jc_indices 数据到 MySQL"""
    logger.info("开始迁移 jc_indices 数据...")

    cursor_sqlite = conn_sqlite.cursor()
    cursor_sqlite.execute('SELECT * FROM jc_indices')

    # 获取列名
    col_names = [desc[0] for desc in cursor_sqlite.description]
    logger.info(f"jc_indices 列: {col_names}")

    rows = cursor_sqlite.fetchall()
    total = len(rows)
    logger.info(f"读取 {total} 条 jc_indices 记录")

    cursor_mysql = conn_mysql.cursor()

    insert_sql = """
    INSERT INTO jc_indices (doi, Jc, Jc_unit, temperature, temperature_unit,
                           magneticfield, magnetic_field_unit, angle, angle_unit, error_bar)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    success_count = 0
    batch_size = 500
    batch_data = []

    for i, row in enumerate(rows):
        row_dict = dict(zip(col_names, row))

        batch_data.append((
            row_dict.get('doi', '')[:255],
            str(row_dict.get('Jc', '') or ''),
            str(row_dict.get('Jc_unit', '') or '')[:50],
            row_dict.get('temperature'),
            str(row_dict.get('temperature_unit', '') or '')[:20],
            row_dict.get('magneticfield'),
            str(row_dict.get('magnetic_field_unit', '') or '')[:20],
            row_dict.get('angle'),
            str(row_dict.get('angle_unit', '') or '')[:20],
            str(row_dict.get('error_bar', '') or '')
        ))

        if len(batch_data) >= batch_size:
            try:
                cursor_mysql.executemany(insert_sql, batch_data)
                conn_mysql.commit()
                success_count += len(batch_data)
                logger.info(f"[{i}/{total}] 批量插入 {len(batch_data)} 条")
            except Exception as e:
                logger.error(f"[{i}/{total}] 批量插入失败: {e}")
                conn_mysql.rollback()

            batch_data = []

    # 插入剩余
    if batch_data:
        try:
            cursor_mysql.executemany(insert_sql, batch_data)
            conn_mysql.commit()
            success_count += len(batch_data)
            logger.info(f"最后批量插入 {len(batch_data)} 条")
        except Exception as e:
            logger.error(f"最后批量插入失败: {e}")
            conn_mysql.rollback()

    logger.info(f"jc_indices 迁移完成: {success_count} 条")
    return success_count


def migrate_jc_indices_raw(conn_sqlite, conn_mysql) -> int:
    """迁移 jc_indices_raw 数据到 MySQL"""
    logger.info("开始迁移 jc_indices_raw 数据...")

    cursor_sqlite = conn_sqlite.cursor()
    cursor_sqlite.execute('SELECT * FROM jc_indices_raw')  # 迁移全部数据

    col_names = [desc[0] for desc in cursor_sqlite.description]
    logger.info(f"jc_indices_raw 列: {col_names}")

    rows = cursor_sqlite.fetchall()
    total = len(rows)
    logger.info(f"读取 {total} 条 jc_indices_raw 记录")

    cursor_mysql = conn_mysql.cursor()

    insert_sql = """
    INSERT INTO jc_indices_raw (doi, raw_text, source_section)
    VALUES (%s, %s, %s)
    """

    success_count = 0
    batch_size = 500
    batch_data = []

    for i, row in enumerate(rows):
        row_dict = dict(zip(col_names, row))

        raw_text = row_dict.get('raw_text', '')
        if raw_text and isinstance(raw_text, str) and len(raw_text) > 65535:
            raw_text = raw_text[:65535]

        batch_data.append((
            row_dict.get('doi', '')[:255],
            raw_text or '',
            str(row_dict.get('source_section', '') or '')[:255]
        ))

        if len(batch_data) >= batch_size:
            try:
                cursor_mysql.executemany(insert_sql, batch_data)
                conn_mysql.commit()
                success_count += len(batch_data)
                logger.info(f"[{i}/{total}] 批量插入 {len(batch_data)} 条")
            except Exception as e:
                logger.error(f"[{i}/{total}] 批量插入失败: {e}")
                conn_mysql.rollback()

            batch_data = []

    if batch_data:
        try:
            cursor_mysql.executemany(insert_sql, batch_data)
            conn_mysql.commit()
            success_count += len(batch_data)
            logger.info(f"最后批量插入 {len(batch_data)} 条")
        except Exception as e:
            logger.error(f"最后批量插入失败: {e}")
            conn_mysql.rollback()

    logger.info(f"jc_indices_raw 迁移完成: {success_count} 条")
    return success_count


def verify_migration(client_milvus, conn_mysql):
    """验证迁移结果"""
    logger.info("========== 验证迁移结果 ==========")

    # Milvus统计
    logger.info("\n--- Milvus Collection 统计 ---")
    for col in ['tech_routes', 'exp_schemes']:
        try:
            stats = client_milvus.get_collection_stats(col)
            logger.info(f"{col}: {stats.get('row_count', 0)} 条")
        except Exception as e:
            logger.warning(f"{col}: 获取统计失败 - {e}")

    # MySQL统计
    logger.info("\n--- MySQL 表统计 ---")
    cursor = conn_mysql.cursor()
    for table in ['jc_indices', 'jc_indices_raw']:
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table}')
            count = cursor.fetchone()[0]
            logger.info(f"{table}: {count} 条")
        except Exception as e:
            logger.warning(f"{table}: 查询失败 - {e}")

    logger.info("========== 验证完成 ==========")


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("Deep Reasoning 数据迁移脚本")
    logger.info("=" * 60)

    # 检查v2 SQLite是否存在
    if not V2_SQLITE_PATH.exists():
        logger.error(f"v2 SQLite 数据库不存在: {V2_SQLITE_PATH}")
        return False

    logger.info(f"v2 SQLite 路径: {V2_SQLITE_PATH}")

    # 连接数据库
    conn_sqlite = connect_v2_sqlite()
    client_milvus, DataType = connect_milvus()
    conn_mysql = connect_mysql()

    try:
        # Step 1: 创建 Milvus Collections
        logger.info("\n" + "=" * 40)
        logger.info("Step 1: 创建 Milvus Collections")
        logger.info("=" * 40)
        create_tech_routes_collection(client_milvus, DataType)
        create_exp_schemes_collection(client_milvus, DataType)

        # Step 2: 迁移向量数据到 Milvus
        logger.info("\n" + "=" * 40)
        logger.info("Step 2: 迁移向量数据到 Milvus")
        logger.info("=" * 40)
        tech_success, tech_fail = migrate_tech_routes(conn_sqlite, client_milvus)
        exp_success, exp_fail = migrate_exp_schemes(conn_sqlite, client_milvus)

        # Step 3: 创建 MySQL Jc 表
        logger.info("\n" + "=" * 40)
        logger.info("Step 3: 创建 MySQL Jc 表")
        logger.info("=" * 40)
        create_jc_tables(conn_mysql)

        # Step 4: 迁移 Jc 数据到 MySQL
        logger.info("\n" + "=" * 40)
        logger.info("Step 4: 迁移 Jc 数据到 MySQL")
        logger.info("=" * 40)
        jc_count = migrate_jc_indices(conn_sqlite, conn_mysql)
        jc_raw_count = migrate_jc_indices_raw(conn_sqlite, conn_mysql)

        # Step 5: 验证迁移结果
        logger.info("\n" + "=" * 40)
        logger.info("Step 5: 验证迁移结果")
        logger.info("=" * 40)
        verify_migration(client_milvus, conn_mysql)

        logger.info("\n" + "=" * 60)
        logger.info("迁移完成!")
        logger.info(f"tech_routes: {tech_success} 成功, {tech_fail} 失败")
        logger.info(f"exp_schemes: {exp_success} 成功, {exp_fail} 失败")
        logger.info(f"jc_indices: {jc_count} 条")
        logger.info(f"jc_indices_raw: {jc_raw_count} 条")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.exception(f"迁移过程发生错误: {e}")
        return False

    finally:
        conn_sqlite.close()
        conn_mysql.close()
        client_milvus.close()
        logger.info("数据库连接已关闭")


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)