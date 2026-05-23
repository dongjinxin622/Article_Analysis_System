"""
从 rebco.db (SQLite) 迁移 Jc 数据到 MySQL jc_indices_raw 表
重建表结构，导入数据并去重
"""
import sqlite3
import pymysql
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# SQLite 数据库路径
REBCO_DB_PATH = r'E:\武汉工作\00. 研究课题\Article_Analysis_System_v2\data\REBCO_database\rebco.db'

# MySQL 连接配置
MYSQL_HOST = '8.147.69.101'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'Djx3861599!'
MYSQL_DATABASE = 'article_analysis_v3'


def migrate_and_deduplicate():
    """从 rebco.db 迁移 Jc 数据到 MySQL jc_indices_raw 表"""

    # 连接 SQLite
    logger.info("连接 rebco.db...")
    sqlite_conn = sqlite3.connect(REBCO_DB_PATH)
    sqlite_cursor = sqlite_conn.cursor()

    # 连接 MySQL
    logger.info("连接 MySQL...")
    mysql_conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4'
    )
    mysql_cursor = mysql_conn.cursor()

    # 1. 删除旧的 jc_indices 表（用户要求去掉）
    logger.info("删除 MySQL jc_indices 表...")
    mysql_cursor.execute("DROP TABLE IF EXISTS jc_indices")
    mysql_conn.commit()

    # 2. 重建 jc_indices_raw 表结构（与 rebco.db 一致）
    logger.info("重建 MySQL jc_indices_raw 表结构...")
    mysql_cursor.execute("DROP TABLE IF EXISTS jc_indices_raw")
    mysql_conn.commit()

    create_table_sql = """
    CREATE TABLE jc_indices_raw (
        id INT AUTO_INCREMENT PRIMARY KEY,
        DOI VARCHAR(255),
        DOI_mod VARCHAR(255),
        Title TEXT,
        temperature TEXT,
        magnetic_field TEXT,
        angle TEXT,
        X_value FLOAT,
        X_lable VARCHAR(100),
        x_type VARCHAR(50),
        x_label_unified VARCHAR(100),
        unit VARCHAR(50),
        Y_value FLOAT,
        Y_value_new FLOAT,
        Y_lable VARCHAR(100),
        Y_lable_new VARCHAR(100),
        class1_temp_field VARCHAR(100),
        method TEXT,
        thickness FLOAT,
        substrate TEXT,
        material TEXT,
        temperature_K FLOAT,
        magnetic_field_T FLOAT,
        angle_deg FLOAT,
        jc_value FLOAT,
        jc_unit VARCHAR(50),
        temperature_source TEXT,
        magnetic_field_source TEXT,
        angle_source TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_doi (DOI),
        INDEX idx_temp (temperature_K),
        INDEX idx_field (magnetic_field_T),
        INDEX idx_jc (jc_value)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    mysql_cursor.execute(create_table_sql)
    mysql_conn.commit()
    logger.info("表结构创建完成")

    # 3. 从 SQLite 读取去重后的数据
    logger.info("从 rebco.db 读取去重后的数据...")
    sqlite_cursor.execute("""
        SELECT DISTINCT
            DOI, DOI_mod, Title, temperature, magnetic_field, angle,
            X_value, X_lable, x_type, x_label_unified, unit,
            Y_value, Y_value_new, Y_lable, Y_lable_new,
            class1_temp_field, method, thickness, substrate, material,
            temperature_K, magnetic_field_T, angle_deg, jc_value, jc_unit,
            temperature_source, magnetic_field_source, angle_source
        FROM jc_indices_raw
        WHERE jc_value IS NOT NULL
    """)
    rows = sqlite_cursor.fetchall()
    logger.info(f"去重后有 {len(rows)} 条有效记录")

    # 4. 批量插入 MySQL
    logger.info("开始批量插入 MySQL...")
    batch_size = 5000
    total_inserted = 0

    insert_sql = """
        INSERT INTO jc_indices_raw (
            DOI, DOI_mod, Title, temperature, magnetic_field, angle,
            X_value, X_lable, x_type, x_label_unified, unit,
            Y_value, Y_value_new, Y_lable, Y_lable_new,
            class1_temp_field, method, thickness, substrate, material,
            temperature_K, magnetic_field_T, angle_deg, jc_value, jc_unit,
            temperature_source, magnetic_field_source, angle_source
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """

    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        mysql_cursor.executemany(insert_sql, batch)
        mysql_conn.commit()
        total_inserted += len(batch)
        logger.info(f"已插入 {total_inserted}/{len(rows)} 条记录 ({total_inserted*100//len(rows)}%)")

    # 5. 验证迁移结果
    logger.info("=" * 60)
    logger.info("验证迁移结果...")
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices_raw')
    mysql_total = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices_raw WHERE jc_value IS NOT NULL')
    mysql_jc_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices_raw WHERE temperature_K IS NOT NULL')
    mysql_temp_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices_raw WHERE magnetic_field_T IS NOT NULL')
    mysql_field_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(*) FROM jc_indices_raw WHERE angle_deg IS NOT NULL')
    mysql_angle_count = mysql_cursor.fetchone()[0]
    mysql_cursor.execute('SELECT COUNT(DISTINCT DOI) FROM jc_indices_raw')
    mysql_doi_count = mysql_cursor.fetchone()[0]

    logger.info("=" * 60)
    logger.info("MySQL jc_indices_raw 表统计:")
    logger.info(f"  总记录: {mysql_total}")
    logger.info(f"  有 jc_value: {mysql_jc_count}")
    logger.info(f"  有 temperature_K: {mysql_temp_count}")
    logger.info(f"  有 magnetic_field_T: {mysql_field_count}")
    logger.info(f"  有 angle_deg: {mysql_angle_count}")
    logger.info(f"  唯一 DOI: {mysql_doi_count}")
    logger.info("=" * 60)

    # 6. 显示样本数据
    logger.info("样本数据:")
    mysql_cursor.execute('SELECT DOI, temperature_K, magnetic_field_T, angle_deg, jc_value, jc_unit FROM jc_indices_raw WHERE jc_value IS NOT NULL LIMIT 5')
    samples = mysql_cursor.fetchall()
    for s in samples:
        logger.info(f"  DOI: {s[0][:40]}..., Temp: {s[1]}K, Field: {s[2]}T, Angle: {s[3]}, Jc: {s[4]} {s[5]}")

    sqlite_conn.close()
    mysql_conn.close()
    logger.info("迁移完成!")


if __name__ == '__main__':
    migrate_and_deduplicate()