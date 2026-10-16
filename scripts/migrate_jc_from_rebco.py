"""
从 rebco.db (SQLite) 迁移 Jc 数据到 MySQL jc_indices 表
基于 jc_indices_raw 表的完整数据
"""
import sqlite3
import pymysql
import logging
from typing import List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# SQLite 数据库路径
REBCO_DB_PATH = r'.\data\REBCO_database\rebco.db'

# MySQL 连接配置
MYSQL_HOST = 'localhost'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'Djx3861599!'
MYSQL_DATABASE = 'article_analysis_v3'


def migrate_jc_data():
    """从 rebco.db 迁移 Jc 数据到 MySQL"""

    # 连接 SQLite
    sqlite_conn = sqlite3.connect(REBCO_DB_PATH)
    sqlite_cursor = sqlite_conn.cursor()

    # 连接 MySQL
    mysql_conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4'
    )
    mysql_cursor = mysql_conn.cursor()

    # 获取 SQLite jc_indices_raw 数据统计
    sqlite_cursor.execute('SELECT COUNT(*) FROM jc_indices_raw WHERE jc_value IS NOT NULL')
    total_records = sqlite_cursor.fetchone()[0]
    logger.info(f"rebco.db jc_indices_raw 有 {total_records} 条有效 Jc 记录")

    # 清空 MySQL jc_indices 表
    logger.info("清空 MySQL jc_indices 表...")
    mysql_cursor.execute("DELETE FROM jc_indices")
    mysql_conn.commit()

    # 读取所有数据
    logger.info("从 SQLite 读取数据...")
    sqlite_cursor.execute("""
        SELECT
            DOI,
            Title,
            temperature_K,
            magnetic_field_T,
            angle_deg,
            jc_value,
            jc_unit,
            method,
            thickness,
            substrate,
            class1_temp_field
        FROM jc_indices_raw
        WHERE jc_value IS NOT NULL
    """)
    rows = sqlite_cursor.fetchall()

    logger.info(f"读取了 {len(rows)} 条记录，开始插入 MySQL...")

    # 批量插入
    batch_size = 5000
    total_inserted = 0

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        values_list = []

        for row in batch:
            doi = row[0] or ''
            title = row[1] or ''
            temperature_k = row[2]
            magnetic_field_t = row[3]
            angle_deg = row[4]
            jc_value = row[5]
            jc_unit = row[6] or 'A/cm²'
            method = row[7] or ''
            thickness = row[8]
            substrate = row[9] or ''
            class1_temp_field = row[10] or ''

            # 转换 jc_value 为字符串
            jc_str = str(jc_value) if jc_value is not None else None

            values_list.append((
                doi,
                jc_str,
                jc_unit,
                temperature_k,
                'K',
                magnetic_field_t,
                'T',
                angle_deg,
                'deg'
            ))

        # 批量插入
        sql = """
            INSERT INTO jc_indices
            (doi, Jc, Jc_unit, temperature, temperature_unit, magneticfield, magnetic_field_unit, angle, angle_unit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        mysql_cursor.executemany(sql, values_list)
        mysql_conn.commit()
        total_inserted += len(values_list)
        logger.info(f"已插入 {total_inserted}/{len(rows)} 条记录 ({total_inserted*100//len(rows)}%)")

    # 验证
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices WHERE Jc IS NOT NULL AND Jc != ""')
    mysql_jc_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices WHERE temperature IS NOT NULL')
    mysql_temp_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices WHERE magneticfield IS NOT NULL')
    mysql_field_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices WHERE angle IS NOT NULL')
    mysql_angle_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(DISTINCT doi) FROM jc_indices')
    mysql_doi_count = mysql_cursor.fetchone()[0]

    logger.info("=" * 60)
    logger.info("迁移完成! MySQL jc_indices 表统计:")
    logger.info(f"  总记录: {mysql_jc_count}")
    logger.info(f"  有温度值: {mysql_temp_count}")
    logger.info(f"  有磁场值: {mysql_field_count}")
    logger.info(f"  有角度值: {mysql_angle_count}")
    logger.info(f"  唯一 DOI: {mysql_doi_count}")
    logger.info("=" * 60)

    sqlite_conn.close()
    mysql_conn.close()


if __name__ == '__main__':
    migrate_jc_data()