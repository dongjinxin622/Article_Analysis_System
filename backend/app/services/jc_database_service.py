"""
Jc 数据库搜索服务
负责从云端 MySQL 搜索历史 Jc 数据，进行排名对比
使用 jc_indices_raw 表
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import pymysql
from loguru import logger

from backend.app.core.config import settings


class JcDatabaseService:
    """Jc 数据库搜索服务"""

    # 默认容差值
    DEFAULT_TEMP_TOLERANCE = 5.0  # K
    DEFAULT_FIELD_TOLERANCE = 1.0  # T
    DEFAULT_ANGLE_TOLERANCE = 10.0  # deg

    def __init__(
        self,
        host: str = None,
        port: int = None,
        user: str = None,
        password: str = None,
        database: str = None
    ):
        self.host = host or settings.MYSQL_HOST
        self.port = port or settings.MYSQL_PORT
        self.user = user or settings.MYSQL_USER
        self.password = password or settings.MYSQL_PASSWORD
        self.database = database or settings.MYSQL_DATABASE

    def _get_connection(self):
        """获取 MySQL 连接"""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset='utf8mb4',
            cursorclass=pymysql.cursors.DictCursor
        )

    async def search_by_conditions(
        self,
        temperature: Optional[float] = None,
        magnetic_field: Optional[float] = None,
        angle: Optional[float] = None,
        top_k: int = 50,
        min_jc: float = None,
        temp_tolerance: float = None,
        field_tolerance: float = None,
        angle_tolerance: float = None
    ) -> Dict[str, Any]:
        """
        按实验条件搜索 Jc 数据
        使用 jc_indices_raw 表，列名：jc_value, temperature_K, magnetic_field_T, angle_deg
        """
        temp_tol = temp_tolerance or self.DEFAULT_TEMP_TOLERANCE
        field_tol = field_tolerance or self.DEFAULT_FIELD_TOLERANCE
        angle_tol = angle_tolerance or self.DEFAULT_ANGLE_TOLERANCE

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 构建查询条件 - 使用 jc_indices_raw 表
            conditions = ["jc_value IS NOT NULL"]

            # 温度条件
            if temperature is not None:
                conditions.append(
                    f"temperature_K IS NOT NULL AND "
                    f"temperature_K >= {temperature - temp_tol} AND "
                    f"temperature_K <= {temperature + temp_tol}"
                )

            # 磁场条件
            if magnetic_field is not None:
                conditions.append(
                    f"magnetic_field_T IS NOT NULL AND "
                    f"magnetic_field_T >= {magnetic_field - field_tol} AND "
                    f"magnetic_field_T <= {magnetic_field + field_tol}"
                )

            # 角度条件：NULL可接受，非NULL需满足（180度等效）
            if angle is not None:
                angle_equiv = angle % 180
                conditions.append(
                    f"(angle_deg IS NULL OR "
                    f"ABS(((angle_deg % 180) + 180) % 180 - {angle_equiv}) <= {angle_tol})"
                )

            # 最小 Jc 筛选
            if min_jc is not None:
                conditions.append(f"jc_value >= {min_jc}")

            where_clause = " AND ".join(conditions)

            sql = f"""
                SELECT DOI, jc_value, jc_unit, temperature_K, magnetic_field_T, angle_deg
                FROM jc_indices_raw
                WHERE {where_clause}
                ORDER BY jc_value DESC
                LIMIT {top_k}
            """

            logger.info(f"执行 Jc 搜索: 温度={temperature}, 磁场={magnetic_field}, 角度={angle}")
            cursor.execute(sql)

            rows = cursor.fetchall()
            conn.close()

            # 处理结果
            results = []
            for row in rows:
                results.append({
                    "doi": row.get("DOI", ""),
                    "jc_value": row.get("jc_value"),
                    "jc_unit": row.get("jc_unit", "A/cm²"),
                    "temperature_K": row.get("temperature_K"),
                    "magnetic_field_T": row.get("magnetic_field_T"),
                    "angle_deg": row.get("angle_deg")
                })

            return {
                "success": True,
                "message": f"搜索完成，找到 {len(results)} 条记录",
                "search_conditions": {
                    "temperature": temperature,
                    "magnetic_field": magnetic_field,
                    "angle": angle,
                    "temp_tolerance": temp_tol,
                    "field_tolerance": field_tol,
                    "angle_tolerance": angle_tol
                },
                "results": results,
                "count": len(results)
            }

        except Exception as e:
            logger.error(f"Jc 搜索失败: {e}")
            return {
                "success": False,
                "message": str(e),
                "results": [],
                "count": 0
            }

    async def rank_by_doi(
        self,
        target_doi: str,
        temperature: Optional[float] = None,
        magnetic_field: Optional[float] = None,
        angle: Optional[float] = None,
        temp_tolerance: float = None,
        field_tolerance: float = None,
        angle_tolerance: float = None
    ) -> Dict[str, Any]:
        """
        按DOI进行Jc排名对比
        """
        temp_tol = temp_tolerance or self.DEFAULT_TEMP_TOLERANCE
        field_tol = field_tolerance or self.DEFAULT_FIELD_TOLERANCE
        angle_tol = angle_tolerance or self.DEFAULT_ANGLE_TOLERANCE

        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 1. 获取目标论文的 Jc 数据
            target_sql = """
                SELECT DOI, jc_value, temperature_K, magnetic_field_T, angle_deg
                FROM jc_indices_raw
                WHERE DOI = %s
            """
            cursor.execute(target_sql, (target_doi,))
            target_rows = cursor.fetchall()

            if not target_rows:
                conn.close()
                return {
                    "success": False,
                    "message": f"未找到 DOI: {target_doi} 的 Jc 数据",
                    "target_doi": target_doi
                }

            # 计算目标论文最大 Jc
            target_jc_values = [r.get("jc_value", 0) for r in target_rows if r.get("jc_value")]
            target_jc_max = max(target_jc_values) if target_jc_values else 0

            # 2. 搜索相同条件的所有记录
            conditions = ["jc_value IS NOT NULL"]
            if temperature is not None:
                conditions.append(
                    f"temperature_K IS NOT NULL AND "
                    f"temperature_K >= {temperature - temp_tol} AND "
                    f"temperature_K <= {temperature + temp_tol}"
                )
            if magnetic_field is not None:
                conditions.append(
                    f"magnetic_field_T IS NOT NULL AND "
                    f"magnetic_field_T >= {magnetic_field - field_tol} AND "
                    f"magnetic_field_T <= {magnetic_field + field_tol}"
                )
            if angle is not None:
                angle_equiv = angle % 180
                conditions.append(
                    f"(angle_deg IS NULL OR "
                    f"ABS(((angle_deg % 180) + 180) % 180 - {angle_equiv}) <= {angle_tol})"
                )

            where_clause = " AND ".join(conditions)

            search_sql = f"""
                SELECT DOI, MAX(jc_value) as jc_max
                FROM jc_indices_raw
                WHERE {where_clause}
                GROUP BY DOI
                ORDER BY jc_max DESC
            """

            cursor.execute(search_sql)
            all_rows = cursor.fetchall()

            # 3. 计算排名
            doi_jc_list = [
                {"doi": r.get("DOI", ""), "jc_max": float(r.get("jc_max", 0)) if r.get("jc_max") else 0}
                for r in all_rows
            ]

            # 排序
            doi_jc_list.sort(key=lambda x: x["jc_max"], reverse=True)

            # 找到目标排名
            target_rank = None
            for i, item in enumerate(doi_jc_list):
                if item["doi"] == target_doi:
                    target_rank = i + 1
                    break

            # 如果在条件范围内找不到目标DOI，回退到无条件排名
            if target_rank is None:
                fallback_sql = """
                    SELECT DOI, MAX(jc_value) as jc_max
                    FROM jc_indices_raw
                    WHERE jc_value IS NOT NULL
                    GROUP BY DOI
                    ORDER BY jc_max DESC
                """
                cursor.execute(fallback_sql)
                fallback_rows = cursor.fetchall()
                fallback_list = [
                    {"doi": r.get("DOI", ""), "jc_max": float(r.get("jc_max", 0)) if r.get("jc_max") else 0}
                    for r in fallback_rows
                ]
                fallback_list.sort(key=lambda x: x["jc_max"], reverse=True)
                for i, item in enumerate(fallback_list):
                    if item["doi"] == target_doi:
                        target_rank = i + 1
                        break
                total_papers = len(fallback_list)
                best_jc_max = fallback_list[0]["jc_max"] if fallback_list else 0
                top_10 = fallback_list[:10]
            else:
                total_papers = len(doi_jc_list)
                best_jc_max = doi_jc_list[0]["jc_max"] if doi_jc_list else 0
                top_10 = doi_jc_list[:10]

            conn.close()

            # 百分位排名
            rank_percentile = None
            if target_rank and total_papers > 1:
                rank_percentile = round(1 - (target_rank - 1) / total_papers, 4)

            return {
                "success": True,
                "message": "排名计算完成",
                "target_doi": target_doi,
                "target_jc_max": target_jc_max,
                "target_rank": target_rank,
                "total_papers": total_papers,
                "best_jc_max": best_jc_max,
                "rank_percentile": rank_percentile,
                "top_10": top_10,
                "search_conditions": {
                    "temperature": temperature,
                    "magnetic_field": magnetic_field,
                    "angle": angle,
                    "temp_tolerance": temp_tol,
                    "field_tolerance": field_tol,
                    "angle_tolerance": angle_tol
                }
            }

        except Exception as e:
            logger.error(f"排名计算失败: {e}")
            return {
                "success": False,
                "message": str(e),
                "target_doi": target_doi
            }

    async def get_jc_statistics(self) -> Dict[str, Any]:
        """
        获取 Jc 数据库统计信息
        只返回总记录数和唯一DOI数
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # 统计总数
            cursor.execute("SELECT COUNT(*) as total FROM jc_indices_raw WHERE jc_value IS NOT NULL")
            total = cursor.fetchone().get("total", 0)

            # 统计唯一 DOI 数
            cursor.execute("SELECT COUNT(DISTINCT DOI) as doi_count FROM jc_indices_raw")
            doi_count = cursor.fetchone().get("doi_count", 0)

            conn.close()

            return {
                "success": True,
                "message": "统计信息获取成功",
                "statistics": {
                    "total_records": total,
                    "unique_dois": doi_count
                }
            }

        except Exception as e:
            logger.error(f"统计信息获取失败: {e}")
            return {
                "success": False,
                "message": str(e)
            }

    async def get_dois_by_jc_rank(
        self,
        top_k: int = 20,
        temperature: Optional[float] = None,
        magnetic_field: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        获取 Jc 排名靠前的 DOI 列表
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            conditions = ["jc_value IS NOT NULL"]
            if temperature is not None:
                conditions.append(
                    f"temperature_K >= {temperature - 10} AND temperature_K <= {temperature + 10}"
                )
            if magnetic_field is not None:
                conditions.append(
                    f"magnetic_field_T >= {magnetic_field - 2} AND magnetic_field_T <= {magnetic_field + 2}"
                )

            where_clause = " AND ".join(conditions)

            sql = f"""
                SELECT DOI, MAX(jc_value) as jc_max,
                       AVG(temperature_K) as avg_temp,
                       AVG(magnetic_field_T) as avg_field
                FROM jc_indices_raw
                WHERE {where_clause}
                GROUP BY DOI
                ORDER BY jc_max DESC
                LIMIT {top_k}
            """

            cursor.execute(sql)
            rows = cursor.fetchall()
            conn.close()

            results = []
            for i, row in enumerate(rows):
                results.append({
                    "rank": i + 1,
                    "doi": row.get("DOI", ""),
                    "jc_max": float(row.get("jc_max", 0)) if row.get("jc_max") else None,
                    "avg_temperature": row.get("avg_temp"),
                    "avg_magnetic_field": row.get("avg_field")
                })

            return results

        except Exception as e:
            logger.error(f"获取 Jc 排名失败: {e}")
            return []


# 全局服务实例
_jc_db_service: Optional[JcDatabaseService] = None


def get_jc_db_service() -> JcDatabaseService:
    """获取 Jc 数据库服务实例"""
    global _jc_db_service
    if _jc_db_service is None:
        _jc_db_service = JcDatabaseService()
    return _jc_db_service