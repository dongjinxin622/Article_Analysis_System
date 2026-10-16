"""
导入 Jc Excel 数据到 MySQL jc_indices 表
从 Jc_final_part1.xlsx 和 Jc_final_part2.xlsx 导入数据
"""
import pandas as pd
import pymysql
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Excel 文件路径
EXCEL_PATH_1 = r'data\图表数据_完成处理\results\Jc_final_part1.xlsx'
EXCEL_PATH_2 = r'data\图表数据_完成处理\results\Jc_final_part2.xlsx'

# MySQL 连接配置
MYSQL_HOST = 'localhost'
MYSQL_PORT = 3306
MYSQL_USER = 'root'
MYSQL_PASSWORD = 'Djx3861599!'
MYSQL_DATABASE = 'article_analysis_v3'


def import_jc_data():
    """导入 Jc 数据到 MySQL"""
    # 读取 Excel 文件
    logger.info("读取 Excel 文件...")
    df1 = pd.read_excel(EXCEL_PATH_1, sheet_name='Sheet1')
    df2 = pd.read_excel(EXCEL_PATH_2, sheet_name='Sheet1')

    # 合并数据
    df_all = pd.concat([df1, df2], ignore_index=True)
    logger.info(f"总共 {len(df_all)} 条记录")

    # 连接 MySQL
    conn = pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset='utf8mb4'
    )
    cursor = conn.cursor()

    # 清空现有数据
    logger.info("清空现有 jc_indices 表数据...")
    cursor.execute("DELETE FROM jc_indices")
    conn.commit()

    # 插入数据
    logger.info("开始插入数据...")

    # 只保留有 Jc 值的记录
    df_jc = df_all[df_all['Y-value-new'].notna()].copy()
    logger.info(f"有 Jc 值的记录: {len(df_jc)} 条")

    batch_size = 5000
    total_inserted = 0

    for i in range(0, len(df_jc), batch_size):
        batch = df_jc.iloc[i:i+batch_size]
        values_list = []

        for _, row in batch.iterrows():
            try:
                doi = str(row.get('DOI', '')).strip()
                jc_value = str(row.get('Y-value-new', '')).strip()
                jc_unit = str(row.get('Y-lable-new', 'A/cm²')).strip()
                temperature = row.get('temperature')
                magnetic_field = row.get('magnetic_field')
                angle = row.get('angle')

                values_list.append((
                    doi,
                    jc_value,
                    jc_unit,
                    float(temperature) if pd.notna(temperature) else None,
                    'K',
                    float(magnetic_field) if pd.notna(magnetic_field) else None,
                    'T',
                    float(angle) if pd.notna(angle) else None,
                    'deg'
                ))

            except Exception as e:
                logger.error(f"处理失败: {e}, DOI: {row.get('DOI')}")

        # 批量插入
        sql = """
            INSERT INTO jc_indices
            (doi, Jc, Jc_unit, temperature, temperature_unit, magneticfield, magnetic_field_unit, angle, angle_unit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        cursor.executemany(sql, values_list)
        conn.commit()
        total_inserted += len(values_list)
        logger.info(f"已插入 {total_inserted} 条记录...")

    conn.close()
    logger.info(f"导入完成! 共插入 {total_inserted} 条记录")


if __name__ == '__main__':
    import_jc_data()