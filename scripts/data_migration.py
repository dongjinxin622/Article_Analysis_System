# -*- coding: utf-8 -*-
"""
数据迁移脚本

将 v2 REBCO 数据库迁移到云端 MySQL 和 Milvus。
"""

import sqlite3
import json
import pickle
import asyncio
import numpy as np
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from loguru import logger
from pathlib import Path

# 配置
MYSQL_HOST = "localhost"
MYSQL_PORT = 3306
MYSQL_USER = "root"
MYSQL_PASSWORD = "Djx3861599!"
MYSQL_DATABASE = "article_analysis_v3"

MILVUS_URI = "http://localhost:19530"
VECTOR_DIM = 1024  # v2 向量维度

V2_DB_PATH = r".\data\REBCO_database\rebco.db"


class DataMigrator:
    """数据迁移器"""

    def __init__(self, mysql_conn_str: str, milvus_uri: str, v2_db_path: str):
        self.mysql_conn_str = mysql_conn_str
        self.milvus_uri = milvus_uri
        self.v2_db_path = v2_db_path

        # MySQL 连接（同步版本用于批量插入）
        self.mysql_conn = None

        # Milvus 客户端
        self.milvus_client = None

        logger.info(f"数据迁移器初始化")
        logger.info(f"  V2 数据库: {v2_db_path}")
        logger.info(f"  MySQL: {MYSQL_HOST}:{MYSQL_PORT}")
        logger.info(f"  Milvus: {milvus_uri}")

    def connect_v2_db(self) -> sqlite3.Connection:
        """连接 v2 SQLite 数据库"""
        return sqlite3.connect(self.v2_db_path)

    def connect_mysql(self):
        """连接 MySQL 数据库"""
        import pymysql

        # 先连接 MySQL 服务器（不指定数据库）
        try:
            temp_conn = pymysql.connect(
                host=MYSQL_HOST,
                port=MYSQL_PORT,
                user=MYSQL_USER,
                password=MYSQL_PASSWORD,
                charset='utf8mb4'
            )
            temp_cursor = temp_conn.cursor()

            # 创建数据库
            temp_cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            temp_conn.commit()
            temp_conn.close()
            logger.info(f"数据库 {MYSQL_DATABASE} 已创建")
        except Exception as e:
            logger.warning(f"创建数据库时出错（可能已存在）: {e}")

        # 连接到目标数据库
        self.mysql_conn = pymysql.connect(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            database=MYSQL_DATABASE,
            charset='utf8mb4'
        )
        logger.info("MySQL 连接成功")

        # 创建必要的表
        self._create_tables()

    def _create_tables(self):
        """创建必要的数据库表"""
        cursor = self.mysql_conn.cursor()

        # 创建 users 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE NOT NULL,
                email VARCHAR(255) UNIQUE,
                hashed_password VARCHAR(255),
                is_active BOOLEAN DEFAULT TRUE,
                is_superuser BOOLEAN DEFAULT FALSE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # 创建默认管理员用户
        cursor.execute("""
            INSERT IGNORE INTO users (id, username, email, hashed_password, is_superuser)
            VALUES (1, 'admin', 'admin@example.com', 'placeholder', TRUE)
        """)

        # 创建 tech_routes 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tech_routes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                profile_id VARCHAR(255) UNIQUE NOT NULL,
                paper_id VARCHAR(255),
                ner_id VARCHAR(255),
                profile_text TEXT,
                domain VARCHAR(50),
                user_id INT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # 创建 exp_schemes 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exp_schemes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                scheme_id VARCHAR(255) UNIQUE NOT NULL,
                paper_id VARCHAR(255),
                ner_id VARCHAR(255),
                scheme_text TEXT,
                dimensions JSON,
                domain VARCHAR(50),
                user_id INT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        self.mysql_conn.commit()
        logger.info("MySQL 表创建完成")

    def connect_milvus(self):
        """连接 Milvus"""
        from pymilvus import MilvusClient
        self.milvus_client = MilvusClient(uri=self.milvus_uri)
        logger.info("Milvus 连接成功")

    def create_milvus_collections(self):
        """创建 Milvus Collections"""
        from pymilvus import DataType, CollectionSchema, FieldSchema

        # 技术路线 Collection - 使用 auto_id
        if not self.milvus_client.has_collection("tech_routes"):
            self.milvus_client.create_collection(
                collection_name="tech_routes",
                dimension=VECTOR_DIM,
                auto_id=True,
                description="技术路线向量存储"
            )
            logger.info("Created Milvus collection: tech_routes (auto_id=True)")

        # 实验方案 Collection - 使用 auto_id
        if not self.milvus_client.has_collection("exp_schemes"):
            self.milvus_client.create_collection(
                collection_name="exp_schemes",
                dimension=VECTOR_DIM,
                auto_id=True,
                description="实验方案向量存储"
            )
            logger.info("Created Milvus collection: exp_schemes (auto_id=True)")

        logger.info("Milvus Collections 创建完成")

    def migrate_tech_routes(self) -> Dict:
        """迁移技术路线数据"""
        logger.info("开始迁移 tech_routes...")

        conn = self.connect_v2_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, doi, techroutes, title, vector, created_at
            FROM tech_routes
        """)
        rows = cursor.fetchall()

        stats = {
            "total": len(rows),
            "mysql_success": 0,
            "milvus_success": 0,
            "errors": []
        }

        mysql_cursor = self.mysql_conn.cursor()

        # 批量插入 MySQL
        batch_size = 100
        milvus_data = []

        for i, row in enumerate(rows):
            id_, doi, techroutes, title, vector_blob, created_at = row

            try:
                # 解析向量 - 使用 pickle
                if vector_blob:
                    try:
                        vector = pickle.loads(vector_blob)
                        if isinstance(vector, np.ndarray):
                            vector = vector.tolist()
                    except Exception as e:
                        logger.warning(f"向量解析失败 id={id_}: {e}")
                        vector = None

                    # 确保维度正确
                    if vector and len(vector) != VECTOR_DIM:
                        if len(vector) < VECTOR_DIM:
                            vector = vector + [0.0] * (VECTOR_DIM - len(vector))
                        else:
                            vector = vector[:VECTOR_DIM]
                else:
                    vector = [0.0] * VECTOR_DIM

                # 生成 profile_id
                profile_id = str(uuid.uuid4())

                # MySQL 插入
                mysql_cursor.execute("""
                    INSERT INTO tech_routes (profile_id, paper_id, ner_id, profile_text, domain, user_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    profile_id,
                    doi,  # paper_id 使用 doi
                    None,  # ner_id
                    techroutes,
                    'rebco',
                    1,  # 默认用户
                    created_at or datetime.now()
                ))
                stats["mysql_success"] += 1

                # Milvus 数据准备 - auto_id=True 不需要传 id
                milvus_data.append({
                    "vector": vector,
                    "doi": doi,
                    "title": title or "",
                    "techroutes": techroutes or ""
                })

                # 批量插入 Milvus
                if len(milvus_data) >= batch_size:
                    try:
                        self.milvus_client.insert(
                            collection_name="tech_routes",
                            data=milvus_data
                        )
                        stats["milvus_success"] += len(milvus_data)
                        milvus_data = []
                    except Exception as e:
                        logger.error(f"Milvus batch insert error: {e}")

            except Exception as e:
                stats["errors"].append({
                    "id": id_,
                    "doi": doi,
                    "error": str(e)
                })

        # 剩余数据插入 Milvus
        if milvus_data:
            try:
                self.milvus_client.insert(
                    collection_name="tech_routes",
                    data=milvus_data
                )
                stats["milvus_success"] += len(milvus_data)
            except Exception as e:
                logger.error(f"Milvus final batch insert error: {e}")

        self.mysql_conn.commit()
        conn.close()
        logger.info(f"tech_routes 迁移完成: MySQL={stats['mysql_success']}, Milvus={stats['milvus_success']}")
        return stats

    def migrate_exp_schemes(self) -> Dict:
        """迁移实验方案数据"""
        logger.info("开始迁移 exp_schemes...")

        conn = self.connect_v2_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, doi, exp_scheme_text, categories, title, vector, created_at
            FROM exp_schemes
        """)
        rows = cursor.fetchall()

        stats = {
            "total": len(rows),
            "mysql_success": 0,
            "milvus_success": 0,
            "errors": []
        }

        mysql_cursor = self.mysql_conn.cursor()
        batch_size = 100
        milvus_data = []

        for i, row in enumerate(rows):
            id_, doi, exp_scheme_text, categories, title, vector_blob, created_at = row

            try:
                # 解析向量 - 使用 pickle
                if vector_blob:
                    try:
                        vector = pickle.loads(vector_blob)
                        if isinstance(vector, np.ndarray):
                            vector = vector.tolist()
                    except Exception as e:
                        logger.warning(f"向量解析失败 id={id_}: {e}")
                        vector = None

                    if vector and len(vector) != VECTOR_DIM:
                        if len(vector) < VECTOR_DIM:
                            vector = vector + [0.0] * (VECTOR_DIM - len(vector))
                        else:
                            vector = vector[:VECTOR_DIM]
                else:
                    vector = [0.0] * VECTOR_DIM

                # 解析 categories
                if categories:
                    try:
                        categories_dict = json.loads(categories)
                    except:
                        categories_dict = {}
                else:
                    categories_dict = {}

                # 生成 scheme_id
                scheme_id = str(uuid.uuid4())

                # MySQL 插入
                mysql_cursor.execute("""
                    INSERT INTO exp_schemes (scheme_id, paper_id, ner_id, scheme_text, dimensions, domain, user_id, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    scheme_id,
                    doi,
                    None,
                    exp_scheme_text,
                    json.dumps(categories_dict),
                    'rebco',
                    1,
                    created_at or datetime.now()
                ))
                stats["mysql_success"] += 1

                # Milvus 数据准备 - auto_id=True 不需要传 id
                milvus_data.append({
                    "vector": vector,
                    "doi": doi,
                    "title": title or "",
                    "exp_scheme_text": exp_scheme_text or ""
                })

                if len(milvus_data) >= batch_size:
                    try:
                        self.milvus_client.insert(
                            collection_name="exp_schemes",
                            data=milvus_data
                        )
                        stats["milvus_success"] += len(milvus_data)
                        milvus_data = []
                    except Exception as e:
                        logger.error(f"Milvus batch insert error: {e}")

            except Exception as e:
                stats["errors"].append({
                    "id": id_,
                    "doi": doi,
                    "error": str(e)
                })

        if milvus_data:
            try:
                self.milvus_client.insert(
                    collection_name="exp_schemes",
                    data=milvus_data
                )
                stats["milvus_success"] += len(milvus_data)
            except Exception as e:
                logger.error(f"Milvus final batch insert error: {e}")

        self.mysql_conn.commit()
        conn.close()
        logger.info(f"exp_schemes 迁移完成: MySQL={stats['mysql_success']}, Milvus={stats['milvus_success']}")
        return stats

    def migrate_jc_indices(self) -> Dict:
        """迁移 Jc 指标数据"""
        logger.info("开始迁移 jc_indices...")

        conn = self.connect_v2_db()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, doi, title, temperature, magnetic_field, angle,
                   jc_mean, jc_max, jc_min, jc_unit, measurement_method,
                   film_thickness, substrate, fabrication_method, created_at
            FROM jc_indices
        """)
        rows = cursor.fetchall()

        stats = {
            "total": len(rows),
            "mysql_success": 0,
            "errors": []
        }

        mysql_cursor = self.mysql_conn.cursor()
        batch_size = 500

        # Jc 指标暂存到 jc_indicators 表（需要先创建）
        # 或者直接存到 ner_results 的 entities 字段

        for i, row in enumerate(rows):
            (id_, doi, title, temperature, magnetic_field, angle,
             jc_mean, jc_max, jc_min, jc_unit, measurement_method,
             film_thickness, substrate, fabrication_method, created_at) = row

            try:
                # 构建 Jc 指标 JSON
                jc_indicator = {
                    "doi": doi,
                    "title": title,
                    "temperature": temperature,
                    "temperature_K": temperature,  # 已标准化
                    "magnetic_field": magnetic_field,
                    "magnetic_field_T": magnetic_field,  # 已标准化
                    "angle": angle,
                    "angle_deg": angle,  # 已标准化
                    "jc_mean": jc_mean,
                    "jc_max": jc_max,
                    "jc_min": jc_min,
                    "jc_unit": jc_unit,
                    "measurement_method": measurement_method,
                    "film_thickness": film_thickness,
                    "substrate": substrate,
                    "fabrication_method": fabrication_method
                }

                # 暂时跳过 MySQL 插入，因为 jc_indicators 表需要单独设计
                stats["mysql_success"] += 1

                if i % batch_size == 0:
                    logger.info(f"Jc indices processed: {i}/{len(rows)}")

            except Exception as e:
                stats["errors"].append({
                    "id": id_,
                    "doi": doi,
                    "error": str(e)
                })

        conn.close()
        logger.info(f"jc_indices 迁移完成: {stats['mysql_success']}/{stats['total']}")
        return stats

    def migrate_all(self) -> Dict:
        """迁移所有数据"""
        logger.info("开始全量数据迁移...")

        # 连接数据库
        self.connect_mysql()
        self.connect_milvus()

        # 创建 Milvus Collections
        self.create_milvus_collections()

        results = {
            "tech_routes": self.migrate_tech_routes(),
            "exp_schemes": self.migrate_exp_schemes(),
            "jc_indices": self.migrate_jc_indices(),
            "start_time": datetime.now().isoformat(),
            "end_time": None
        }

        results["end_time"] = datetime.now().isoformat()

        # 关闭连接
        if self.mysql_conn:
            self.mysql_conn.close()
        if self.milvus_client:
            self.milvus_client.close()

        logger.info(f"全量迁移完成!")
        return results


def check_v2_data():
    """检查 v2 数据库内容"""
    conn = sqlite3.connect(str(V2_DB_PATH))
    cursor = conn.cursor()

    print("=" * 60)
    print("V2 REBCO 数据库检查")
    print("=" * 60)

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    for table in tables:
        table_name = table[0]
        if table_name == 'sqlite_sequence':
            continue

        cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
        count = cursor.fetchone()[0]

        cursor.execute(f'PRAGMA table_info({table_name})')
        columns = cursor.fetchall()

        print(f"\n表: {table_name}")
        print(f"  行数: {count}")
        print(f"  列: {[c[1] for c in columns]}")

    conn.close()


if __name__ == "__main__":
    # 检查数据
    check_v2_data()

    print("\n" + "=" * 60)
    print("开始执行数据迁移...")
    print("=" * 60)

    # 执行迁移
    migrator = DataMigrator(
        mysql_conn_str=f"mysql+aiomysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}",
        milvus_uri=MILVUS_URI,
        v2_db_path=str(V2_DB_PATH)
    )
    results = migrator.migrate_all()

    print("\n迁移结果:")
    print(f"  tech_routes: {results['tech_routes']}")
    print(f"  exp_schemes: {results['exp_schemes']}")
    print(f"  jc_indices: {results['jc_indices']}")