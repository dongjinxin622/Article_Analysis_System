"""
报告生成服务测试

覆盖：
- _create_summary_data 摘要数据构建
- DOI 提取逻辑（优先 pdf_info，回退 jc_analysis）
- Markdown 报告生成（临时目录）
"""
import pytest
import os
import tempfile

from backend.app.services.report_service import ReportService


@pytest.fixture
def report_svc():
    """使用临时目录创建 ReportService"""
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ReportService(output_dir=tmpdir)
        yield svc


# ============================================================================
# _create_summary_data 测试
# ============================================================================

class TestCreateSummaryData:
    """摘要数据构建测试"""

    def test_basic_summary_with_task_id(self, report_svc):
        """task_id 优先级高于 analysis_data 内部值"""
        data = {"task_id": "inner-id", "pdf_info": {"doi": "10.1234/test"}}
        summary = report_svc._create_summary_data(data, task_id="outer-id")
        assert summary["任务 ID"] == "outer-id"

    def test_task_id_fallback_to_analysis_data(self, report_svc):
        """task_id 为空时回退到 analysis_data"""
        data = {"task_id": "inner-id"}
        summary = report_svc._create_summary_data(data, task_id="")
        assert summary["任务 ID"] == "inner-id"

    def test_task_id_fallback_to_na(self, report_svc):
        """两者都缺失时为 N/A"""
        data = {}
        summary = report_svc._create_summary_data(data, task_id="")
        assert summary["任务 ID"] == "N/A"

    def test_doi_from_pdf_info(self, report_svc):
        """DOI 优先从 pdf_info 获取"""
        data = {"pdf_info": {"doi": "10.1234/primary"}}
        summary = report_svc._create_summary_data(data)
        assert summary["目标 DOI"] == "10.1234/primary"

    def test_doi_fallback_to_jc_ranking(self, report_svc):
        """pdf_info 无 DOI 时回退到 jc_analysis ranking"""
        data = {
            "pdf_info": {},
            "jc_analysis": {"ranking": {"target_doi": "10.5678/fallback"}}
        }
        summary = report_svc._create_summary_data(data)
        assert summary["目标 DOI"] == "10.5678/fallback"

    def test_doi_pdf_info_over_jc(self, report_svc):
        """pdf_info DOI 优先于 jc_analysis ranking"""
        data = {
            "pdf_info": {"doi": "10.1234/priority"},
            "jc_analysis": {"ranking": {"target_doi": "10.5678/fallback"}}
        }
        summary = report_svc._create_summary_data(data)
        assert summary["目标 DOI"] == "10.1234/priority"

    def test_doi_both_missing_returns_na(self, report_svc):
        """两个来源都没有 DOI 时返回 N/A"""
        data = {"pdf_info": {}, "jc_analysis": {}}
        summary = report_svc._create_summary_data(data)
        assert summary["目标 DOI"] == "N/A"

    def test_doi_null_pdf_info(self, report_svc):
        """pdf_info 为 None 时仍能回退"""
        data = {
            "pdf_info": None,
            "jc_analysis": {"ranking": {"target_doi": "10.5678/fallback"}}
        }
        summary = report_svc._create_summary_data(data)
        assert summary["目标 DOI"] == "10.5678/fallback"

    def test_tech_route_summary(self, report_svc):
        """技术路线相似论文数和最高相似度"""
        data = {
            "tech_route": {
                "similar_papers": [
                    {"score": 0.92, "title": "Paper A"},
                    {"score": 0.85, "title": "Paper B"},
                ]
            }
        }
        summary = report_svc._create_summary_data(data)
        assert summary["技术路线相似论文数"] == 2
        assert summary["最高技术路线相似度"] == "92.00%"

    def test_exp_scheme_dimensions(self, report_svc):
        """实验方案维度数和类别"""
        data = {
            "exp_scheme": {
                "dimensions": {
                    "material_fabrication": ["YBCO"],
                    "deposition_techniques": ["PLD"],
                }
            }
        }
        summary = report_svc._create_summary_data(data)
        assert summary["实验方案维度数"] == 2

    def test_jc_indicators_count(self, report_svc):
        """Jc 指标数统计"""
        data = {
            "jc_analysis": {
                "jc_indicators": [{"jc_value": 1.5e6}, {"jc_value": 2.3e6}],
                "ranking": {"success": True, "target_rank": 3}
            }
        }
        summary = report_svc._create_summary_data(data)
        assert summary["提取 Jc 指标数"] == 2
        assert "第3名" in summary["Jc 排名"]

    def test_pdf_info_entity_counts(self, report_svc):
        """NER 实体数和 RE 关系数"""
        data = {
            "pdf_info": {"ner_entity_count": 42, "re_relation_count": 15}
        }
        summary = report_svc._create_summary_data(data)
        assert summary["NER 实体数"] == 42
        assert summary["RE 关系数"] == 15

    def test_empty_analysis_data(self, report_svc):
        """空 analysis_data 只返回任务 ID、生成时间和 DOI"""
        summary = report_svc._create_summary_data({})
        assert "任务 ID" in summary
        assert "生成时间" in summary
        assert "目标 DOI" in summary
        assert summary["目标 DOI"] == "N/A"


# ============================================================================
# DOI 提取逻辑一致性测试
# ============================================================================

class TestDoiExtractionConsistency:
    """验证 DOI 提取逻辑在不同方法中的一致性"""

    def test_markdown_and_summary_doi_agree(self, report_svc):
        """Markdown 报告和 _create_summary_data 的 DOI 应一致"""
        data = {
            "pdf_info": {"doi": "10.1234/test", "ner_entity_count": 5, "re_relation_count": 3},
            "jc_analysis": {},
            "tech_route": {},
            "exp_scheme": {},
        }
        summary = report_svc._create_summary_data(data, task_id="t1")
        md_path = report_svc.generate_markdown_report(data, task_id="t1")

        # 从 summary 获取 DOI
        summary_doi = summary["目标 DOI"]

        # 从 Markdown 文件内容获取 DOI
        with open(md_path, encoding="utf-8") as f:
            md_content = f.read()
        # Markdown 中 DOI 行格式: **目标 DOI**: `xxx`
        import re
        doi_match = re.search(r"\*\*目标 DOI\*\*: `([^`]+)`", md_content)
        md_doi = doi_match.group(1) if doi_match else "N/A"

        assert summary_doi == md_doi