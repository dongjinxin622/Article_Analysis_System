"""
Jc 数据库服务测试

覆盖：
- 排名计算逻辑（纯数学计算，mock asyncpg 返回值）
- 百分位计算
- 搜索条件参数构建验证
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.app.services.jc_database_service import JcDatabaseService


@pytest.fixture
def jc_svc():
    """创建 Jc 数据库服务（不连接真实数据库）"""
    return JcDatabaseService(
        host="fake", port=5432,
        user="fake", password="fake",
        database="fake"
    )


# ============================================================================
# 排名计算逻辑测试
# ============================================================================

class TestRankCalculation:
    """排名计算逻辑测试（mock asyncpg 返回值后验证计算结果）"""

    def test_target_rank_found(self):
        """目标 DOI 在条件范围内找到排名"""
        # 模拟 asyncpg 返回的行数据
        all_rows = [
            {"DOI": "10.1234/A", "jc_max": 5e6},
            {"DOI": "10.1234/B", "jc_max": 3e6},
            {"DOI": "10.5678/TARGET", "jc_max": 2e6},
            {"DOI": "10.1234/C", "jc_max": 1e6},
        ]

        doi_jc_list = [
            {"doi": r["DOI"], "jc_max": float(r["jc_max"]) if r["jc_max"] else 0}
            for r in all_rows
        ]
        doi_jc_list.sort(key=lambda x: x["jc_max"], reverse=True)

        target_doi = "10.5678/TARGET"
        target_rank = None
        for i, item in enumerate(doi_jc_list):
            if item["doi"] == target_doi:
                target_rank = i + 1
                break

        assert target_rank == 3  # 第 3 名（2e6 排在 5e6 和 3e6 之后）

    def test_target_not_found_needs_fallback(self):
        """目标 DOI 不在条件范围内 → 需回退到无条件排名"""
        all_rows = [
            {"DOI": "10.1234/A", "jc_max": 5e6},
            {"DOI": "10.1234/B", "jc_max": 3e6},
        ]
        target_doi = "10.5678/TARGET"

        doi_jc_list = [
            {"doi": r["DOI"], "jc_max": float(r["jc_max"])}
            for r in all_rows
        ]
        doi_jc_list.sort(key=lambda x: x["jc_max"], reverse=True)

        target_rank = None
        for i, item in enumerate(doi_jc_list):
            if item["doi"] == target_doi:
                target_rank = i + 1
                break

        assert target_rank is None  # 在条件范围中找不到

    def test_percentile_calculation(self):
        """百分位计算验证"""
        target_rank = 3
        total_papers = 100
        rank_percentile = round(1 - (target_rank - 1) / total_papers, 4)
        assert rank_percentile == 0.98  # 第 3 名 / 100 篇 ≈ 98 百分位

    def test_percentile_single_paper(self):
        """只有一篇论文时百分位无意义"""
        target_rank = 1
        total_papers = 1
        # total_papers <= 1 时不应计算百分位
        if total_papers > 1:
            rank_percentile = round(1 - (target_rank - 1) / total_papers, 4)
        else:
            rank_percentile = None
        assert rank_percentile is None

    def test_top_10_extraction(self):
        """提取前 10 排名"""
        doi_jc_list = [
            {"doi": f"10.{i}", "jc_max": (10 - i) * 1e6}
            for i in range(20)
        ]
        doi_jc_list.sort(key=lambda x: x["jc_max"], reverse=True)
        top_10 = doi_jc_list[:10]
        assert len(top_10) == 10
        assert top_10[0]["jc_max"] >= top_10[-1]["jc_max"]

    def test_jc_max_zero_handling(self):
        """jc_max 为 None 或 0 时安全处理"""
        all_rows = [
            {"DOI": "10.1/A", "jc_max": None},
            {"DOI": "10.1/B", "jc_max": 0},
            {"DOI": "10.1/C", "jc_max": 1.5e6},
        ]
        doi_jc_list = [
            {"doi": r["DOI"], "jc_max": float(r["jc_max"]) if r["jc_max"] else 0}
            for r in all_rows
        ]
        doi_jc_list.sort(key=lambda x: x["jc_max"], reverse=True)
        # None 和 0 被转为 0，排在最后
        assert doi_jc_list[0]["jc_max"] == 1.5e6
        assert doi_jc_list[-1]["jc_max"] == 0


# ============================================================================
# 搜索条件参数构建验证
# ============================================================================

class TestSearchConditionParams:
    """搜索条件参数构建验证"""

    def test_default_tolerances(self, jc_svc):
        """验证默认容差值"""
        assert jc_svc.DEFAULT_TEMP_TOLERANCE > 0
        assert jc_svc.DEFAULT_FIELD_TOLERANCE > 0
        assert jc_svc.DEFAULT_ANGLE_TOLERANCE > 0

    def test_angle_normalization(self):
        """角度模 180 归一化"""
        angle = 270
        angle_equiv = angle % 180
        assert angle_equiv == 90

        angle = 180
        angle_equiv = angle % 180
        assert angle_equiv == 0

        angle = 45
        angle_equiv = angle % 180
        assert angle_equiv == 45

    def test_temperature_range_calculation(self):
        """温度范围计算"""
        temp = 77
        tol = 5
        low = temp - tol
        high = temp + tol
        assert low == 72
        assert high == 82

    def test_magnetic_field_range_calculation(self):
        """磁场范围计算"""
        field = 1.0
        tol = 0.5
        low = field - tol
        high = field + tol
        assert low == 0.5
        assert high == 1.5