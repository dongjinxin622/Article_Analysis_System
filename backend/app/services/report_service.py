"""
分析报告生成服务
支持 Markdown、PDF、Excel 格式的报告导出
"""
import os
import json
import logging
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ReportService:
    """报告生成服务"""

    # 8维度名称映射（中文）
    DIM_NAMES = {
        "material_fabrication": "材料准备",
        "deposition_techniques": "沉积技术",
        "process_parameters": "工艺参数",
        "post_processing": "后处理",
        "characterization_techniques": "表征技术",
        "system_constraints": "系统约束",
        "simulation": "模拟分析",
        "irradiation": "辐照处理"
    }

    def __init__(self, output_dir: str = "data/reports"):
        """
        初始化报告服务

        Args:
            output_dir: 报告输出目录
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"ReportService 已初始化，输出目录：{output_dir}")

    def generate_markdown_report(
        self,
        analysis_data: Dict[str, Any],
        task_id: str
    ) -> str:
        """
        生成 Markdown 格式报告

        Args:
            analysis_data: 分析数据
            task_id: 任务 ID

        Returns:
            报告文件路径
        """
        output_path = self.output_dir / f"{task_id}_report.md"

        report_md = self._generate_markdown_content(analysis_data, task_id)

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report_md)

        logger.info(f"Markdown 报告已生成：{output_path}")
        return str(output_path)

    def _generate_markdown_content(
        self,
        analysis_data: Dict[str, Any],
        task_id: str
    ) -> str:
        """生成 Markdown 格式报告内容"""
        md = []

        # 标题
        md.append("# 📊 SciPDF AI 论文分析报告\n")
        md.append(f"**任务 ID**: `{task_id}`  \n")
        md.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        target_doi = (analysis_data.get('pdf_info', {}) or {}).get('doi') or (analysis_data.get('jc_analysis', {}) or {}).get('ranking', {}).get('target_doi') or 'N/A'
        md.append(f"**目标 DOI**: `{target_doi}`  \n")
        md.append("\n---\n")

        # 一、摘要
        md.append("## 一、摘要\n")
        summary = self._create_summary_data(analysis_data)
        for key, value in summary.items():
            md.append(f"- **{key}**: {value}\n")
        md.append("\n")

        # 显示综合结论（如果有）
        if 'analysis_summary' in analysis_data and analysis_data['analysis_summary']:
            md.append(f"**综合结论**: {analysis_data['analysis_summary']}\n\n")

        # 二、技术路线分析
        md.append("## 二、技术路线分析\n")
        tech_route = analysis_data.get('tech_route', {})
        if tech_route:
            tech_route_text = tech_route.get('tech_route_text', '')
            similar_papers = tech_route.get('similar_papers', [])

            if tech_route_text:
                md.append("### 2.1 技术路线描述\n")
                md.append(f"{tech_route_text}\n\n")

            if similar_papers:
                md.append("### 2.2 相似论文对比\n")
                md.append("| 排名 | DOI | 相似度 | 标题 |\n")
                md.append("|------|-------|--------|------|\n")
                for i, paper in enumerate(similar_papers[:10], 1):
                    title = paper.get('title', 'N/A')[:50]
                    score = paper.get('score', paper.get('similarity_score', 0))
                    md.append(f"| {i} | {paper.get('doi', 'N/A')} | {score:.2%} | {title} |\n")

                # 显示技术路线详情（前 3 篇）
                md.append("\n### 2.3 技术路线详情对比\n")
                for i, paper in enumerate(similar_papers[:3], 1):
                    route_text = paper.get('route_text', paper.get('tech_route_text', 'N/A'))
                    if route_text and route_text != 'N/A':
                        md.append(f"**{i}. {paper.get('doi', 'N/A')} (相似度：{score:.2%})**:\n")
                        md.append(f"> {route_text[:300]}...\n\n" if len(str(route_text)) > 300 else f"> {route_text}\n\n")
            else:
                md.append("*未找到相似技术路线*\n")
        else:
            md.append("*无数据*\n")
        md.append("\n")

        # 三、实验方案分析
        md.append("## 三、实验方案分析\n")
        exp_scheme = analysis_data.get('exp_scheme', {})
        if exp_scheme:
            exp_scheme_text = exp_scheme.get('exp_scheme_text', '')
            dimensions = exp_scheme.get('dimensions', {})

            if exp_scheme_text:
                md.append("### 3.1 实验方案描述\n")
                md.append(f"{exp_scheme_text}\n\n")

            if dimensions:
                md.append("### 3.2 8维度分析\n")
                md.append("| 维度 | 内容 |\n")
                md.append("|------|------|\n")
                for dim_key, values in dimensions.items():
                    dim_name = self.DIM_NAMES.get(dim_key, dim_key)
                    if values:
                        md.append(f"| {dim_name} | {', '.join(values)} |\n")
                md.append("\n")

            # 显示目标论文类别统计
            target_categories = list(dimensions.keys()) if dimensions else []
            if target_categories:
                md.append(f"**目标论文实验方案类别**: {', '.join([self.DIM_NAMES.get(c, c) for c in target_categories])}\n\n")
        else:
            md.append("*无数据*\n")
        md.append("\n")

        # 四、综合对比分析（LLM 生成）
        md.append("## 四、综合对比分析\n")
        llm_comparison = analysis_data.get('llm_comparison', '')
        if llm_comparison:
            md.append(f"{llm_comparison}\n")
        else:
            md.append("*暂无 LLM 详细对比分析*\n")
        md.append("\n")

        # 五、Jc 指标分析
        md.append("## 五、Jc 指标分析\n")
        jc_analysis = analysis_data.get('jc_analysis', {})
        if jc_analysis:
            jc_indicators = jc_analysis.get('jc_indicators', [])
            ranking = jc_analysis.get('ranking', {})

            if jc_indicators:
                md.append("### 5.1 提取的 Jc 指标\n")
                md.append("| 序号 | Jc 值 | 单位 | 温度 (K) | 磁场 (T) | 角度 (°) |\n")
                md.append("|------|------|------|----------|----------|----------|\n")
                for i, jc in enumerate(jc_indicators, 1):
                    jc_val = jc.get('jc_value', jc.get('Jc', 'N/A'))
                    unit = jc.get('unit', jc.get('Jc_unit', 'A/cm²'))
                    temp = jc.get('temperature', 'N/A')
                    field = jc.get('magnetic_field', jc.get('magneticfield', 'N/A'))
                    angle = jc.get('angle', 'N/A')
                    jc_str = f"{jc_val:.2e}" if isinstance(jc_val, (int, float)) else str(jc_val)
                    md.append(f"| {i} | {jc_str} | {unit} | {temp} | {field} | {angle} |\n")
                md.append("\n")

            if ranking and ranking.get('success'):
                md.append("### 5.2 排名分析\n")
                md.append(f"- 目标 DOI: {ranking.get('target_doi', 'N/A')}\n")
                md.append(f"- 目标 Jc 最大值: {ranking.get('target_jc_max', 'N/A')} A/cm²\n")
                md.append(f"- 排名: 第{ranking.get('target_rank', 'N/A')}名 / 共{ranking.get('total_papers', 0)}篇论文\n")
                percentile = ranking.get('rank_percentile')
                if percentile is not None:
                    md.append(f"- 百分位: {percentile}（前{100-percentile*100:.1f}%）\n")
                md.append("\n")
        else:
            md.append("*无 Jc 分析数据*\n")
        md.append("\n")

        # 六、综合结论
        md.append("## 六、综合结论\n")
        if analysis_data.get('success'):
            md.append("综合分析完成，详细结果见上述各部分。\n")
        else:
            md.append(f"综合分析失败: {analysis_data.get('message', '未知错误')}\n")

        return ''.join(md)

    def generate_excel_report(
        self,
        analysis_data: Dict[str, Any],
        task_id: str
    ) -> str:
        """
        生成 Excel 格式报告（8-9 个 Sheet，Jc排名信息为可选 Sheet）

        Args:
            analysis_data: 分析数据
            task_id: 任务 ID

        Returns:
            报告文件路径
        """
        output_path = self.output_dir / f"{task_id}_report.xlsx"

        try:
            with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
                # Sheet 1: 摘要
                summary_data = self._create_summary_data(analysis_data)
                summary_df = pd.DataFrame([summary_data])
                summary_df.to_excel(writer, sheet_name='摘要', index=False)

                # Sheet 2: 技术路线比较结果
                tech_route = analysis_data.get('tech_route', {})
                similar_papers = tech_route.get('similar_papers', [])
                if similar_papers:
                    techroute_df = pd.DataFrame(similar_papers)
                    techroute_df.to_excel(writer, sheet_name='技术路线比较', index=False)
                else:
                    pd.DataFrame({'消息': ['暂无数据']}).to_excel(writer, sheet_name='技术路线比较', index=False)

                # Sheet 3: 实验方案比较结果
                exp_scheme = analysis_data.get('exp_scheme', {})
                if exp_scheme:
                    exp_scheme_data = {
                        '实验方案描述': exp_scheme.get('exp_scheme_text', 'N/A')
                    }
                    dimensions = exp_scheme.get('dimensions', {})
                    for dim_key, values in dimensions.items():
                        dim_name = self.DIM_NAMES.get(dim_key, dim_key)
                        exp_scheme_data[dim_name] = ', '.join(values) if values else 'N/A'
                    expscheme_df = pd.DataFrame([exp_scheme_data])
                    expscheme_df.to_excel(writer, sheet_name='实验方案比较', index=False)
                else:
                    pd.DataFrame({'消息': ['暂无数据']}).to_excel(writer, sheet_name='实验方案比较', index=False)

                # Sheet 4: Jc 指标比较结果
                jc_analysis = analysis_data.get('jc_analysis', {})
                jc_indicators = jc_analysis.get('jc_indicators', [])
                ranking = jc_analysis.get('ranking', {})

                if jc_indicators:
                    jc_df_data = []
                    for jc in jc_indicators:
                        jc_df_data.append({
                            'Jc值': jc.get('jc_value', jc.get('Jc', 'N/A')),
                            '单位': jc.get('unit', jc.get('Jc_unit', 'A/cm²')),
                            '温度(K)': jc.get('temperature', 'N/A'),
                            '磁场(T)': jc.get('magnetic_field', jc.get('magneticfield', 'N/A')),
                            '角度(°)': jc.get('angle', 'N/A')
                        })
                    jc_df = pd.DataFrame(jc_df_data)
                    jc_df.to_excel(writer, sheet_name='Jc 指标比较', index=False)

                    # 排名信息
                    if ranking and ranking.get('success'):
                        ranking_df = pd.DataFrame([{
                            '目标DOI': ranking.get('target_doi', 'N/A'),
                            '目标Jc最大值': ranking.get('target_jc_max', 'N/A'),
                            '排名': ranking.get('target_rank', 'N/A'),
                            '总论文数': ranking.get('total_papers', 0),
                            '百分位': ranking.get('rank_percentile', 'N/A')
                        }])
                        ranking_df.to_excel(writer, sheet_name='Jc 排名信息', index=False)
                else:
                    pd.DataFrame({'消息': ['暂无 Jc 指标数据']}).to_excel(writer, sheet_name='Jc 指标比较', index=False)

                # Sheet 5: 综合结果
                if 'llm_comparison' in analysis_data:
                    llm_df = pd.DataFrame([{'LLM综合分析': analysis_data.get('llm_comparison', 'N/A')}])
                    llm_df.to_excel(writer, sheet_name='综合结果', index=False)
                else:
                    pd.DataFrame({'消息': ['暂无综合结果']}).to_excel(writer, sheet_name='综合结果', index=False)

                # Sheet 6: NER 实体
                ner_entities = analysis_data.get('ner_entities', [])
                if ner_entities:
                    ner_df = pd.DataFrame(ner_entities)
                    ner_df.to_excel(writer, sheet_name='NER 实体', index=False)
                else:
                    pd.DataFrame({'消息': ['暂无 NER 数据']}).to_excel(writer, sheet_name='NER 实体', index=False)

                # Sheet 7: RE 关系
                re_relations = analysis_data.get('re_relations', [])
                if re_relations:
                    re_df = pd.DataFrame(re_relations)
                    re_df.to_excel(writer, sheet_name='RE 关系', index=False)
                else:
                    pd.DataFrame({'消息': ['暂无 RE 数据']}).to_excel(writer, sheet_name='RE 关系', index=False)

                # Sheet 8: PDF 基本信息
                pdf_info = analysis_data.get('pdf_info', {})
                if pdf_info:
                    pdf_df = pd.DataFrame([pdf_info])
                    pdf_df.to_excel(writer, sheet_name='PDF 信息', index=False)
                else:
                    pd.DataFrame({'消息': ['暂无 PDF 信息']}).to_excel(writer, sheet_name='PDF 信息', index=False)

            logger.info(f"Excel 报告已生成：{output_path}")
            return str(output_path)

        except Exception as e:
            logger.error(f"生成 Excel 报告失败：{e}")
            raise

    def generate_pdf_report(
        self,
        analysis_data: Dict[str, Any],
        task_id: str
    ) -> str:
        """
        生成 PDF 格式报告

        Args:
            analysis_data: 分析数据
            task_id: 任务 ID

        Returns:
            报告文件路径
        """
        output_path = self.output_dir / f"{task_id}_report.pdf"

        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import (
                SimpleDocTemplate, Table, Paragraph, Spacer, TableStyle
            )
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import cm
            from reportlab.lib.enums import TA_CENTER, TA_LEFT

            # 创建文档
            doc = SimpleDocTemplate(
                str(output_path),
                pagesize=A4,
                leftMargin=2*cm,
                rightMargin=2*cm,
                topMargin=2*cm,
                bottomMargin=2*cm
            )

            elements = []
            styles = getSampleStyleSheet()

            # 自定义样式
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Heading1'],
                fontSize=18,
                textColor=colors.HexColor('#1a1a1a'),
                spaceAfter=20,
                alignment=TA_CENTER
            )

            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor('#2c3e50'),
                spaceAfter=12
            )

            # 标题
            elements.append(Paragraph("SciPDF AI 论文分析报告", title_style))
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(f"任务 ID: {task_id}", styles['Normal']))
            elements.append(Paragraph(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
            target_doi_pdf = (analysis_data.get('pdf_info', {}) or {}).get('doi') or (analysis_data.get('jc_analysis', {}) or {}).get('ranking', {}).get('target_doi') or 'N/A'
            elements.append(Paragraph(f"目标 DOI：{target_doi_pdf}", styles['Normal']))
            elements.append(Spacer(1, 20))

            # 一、摘要
            elements.append(Paragraph("一、摘要", heading_style))
            summary = self._create_summary_data(analysis_data)
            summary_data = [[k, str(v)] for k, v in summary.items()]
            summary_table = Table(summary_data, colWidths=[6*cm, 8*cm])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8f9fa')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, -1), 'TOP')
            ]))
            elements.append(summary_table)
            elements.append(Spacer(1, 20))

            # 二、技术路线分析
            elements.append(Paragraph("二、技术路线分析", heading_style))
            tech_route = analysis_data.get('tech_route', {})
            similar_papers = tech_route.get('similar_papers', [])
            if similar_papers:
                tr_data = [['DOI', '相似度', '标题']]
                for paper in similar_papers[:5]:
                    score = paper.get('score', paper.get('similarity_score', 0))
                    tr_data.append([
                        paper.get('doi', 'N/A'),
                        f"{score:.2%}",
                        paper.get('title', 'N/A')[:50]
                    ])
                tr_table = Table(tr_data, colWidths=[5*cm, 2*cm, 9*cm])
                tr_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e3f2fd')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                elements.append(tr_table)
            else:
                elements.append(Paragraph("暂无技术路线数据", styles['Normal']))
            elements.append(Spacer(1, 20))

            # 三、实验方案分析
            elements.append(Paragraph("三、实验方案分析", heading_style))
            exp_scheme = analysis_data.get('exp_scheme', {})
            dimensions = exp_scheme.get('dimensions', {})
            if dimensions:
                dim_data = [['维度', '内容']]
                for dim_key, values in dimensions.items():
                    dim_name = self.DIM_NAMES.get(dim_key, dim_key)
                    dim_data.append([dim_name, ', '.join(values) if values else 'N/A'])
                dim_table = Table(dim_data, colWidths=[4*cm, 10*cm])
                dim_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e8f5e9')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                elements.append(dim_table)
            else:
                elements.append(Paragraph("暂无实验方案数据", styles['Normal']))
            elements.append(Spacer(1, 20))

            # 四、Jc 指标分析
            elements.append(Paragraph("四、Jc 指标分析", heading_style))
            jc_analysis = analysis_data.get('jc_analysis', {})
            jc_indicators = jc_analysis.get('jc_indicators', [])
            if jc_indicators:
                jc_data = [['Jc 值', '单位', '温度', '磁场', '角度']]
                for jc in jc_indicators[:5]:
                    jc_val = jc.get('jc_value', jc.get('Jc', 'N/A'))
                    jc_str = f"{jc_val:.2e}" if isinstance(jc_val, (int, float)) else str(jc_val)
                    jc_data.append([
                        jc_str,
                        jc.get('unit', jc.get('Jc_unit', 'A/cm²')),
                        str(jc.get('temperature', 'N/A')),
                        str(jc.get('magnetic_field', jc.get('magneticfield', 'N/A'))),
                        str(jc.get('angle', 'N/A'))
                    ])
                jc_table = Table(jc_data, colWidths=[3*cm, 2*cm, 2*cm, 2*cm, 2*cm])
                jc_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fff3e0')),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
                ]))
                elements.append(jc_table)
            else:
                elements.append(Paragraph("暂无 Jc 指标数据", styles['Normal']))
            elements.append(Spacer(1, 20))

            # 五、综合结论
            elements.append(Paragraph("五、综合结论", heading_style))
            conclusion = analysis_data.get('llm_comparison', analysis_data.get('analysis_summary', '无'))
            # 截断过长的结论（reportlab 对超长 Paragraph 支持有限）
            if len(str(conclusion)) > 10000:
                conclusion = str(conclusion)[:10000] + '\n\n...（内容过长，完整内容请查看 Markdown 或 Excel 报告）'
            conclusion_para = Paragraph(str(conclusion), styles['Normal'])
            elements.append(conclusion_para)

            # 构建文档
            doc.build(elements)

            logger.info(f"PDF 报告已生成：{output_path}")
            return str(output_path)

        except ImportError:
            logger.warning("reportlab 未安装，无法生成 PDF 报告")
            raise ImportError("请安装 reportlab: pip install reportlab")
        except Exception as e:
            logger.error(f"生成 PDF 报告失败：{e}")
            raise

    def _create_summary_data(self, analysis_data: Dict[str, Any]) -> Dict[str, Any]:
        """创建摘要数据"""
        summary = {
            '任务 ID': analysis_data.get('task_id', 'N/A'),
            '生成时间': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            '目标 DOI': (analysis_data.get('pdf_info', {}) or {}).get('doi') or (analysis_data.get('jc_analysis', {}) or {}).get('ranking', {}).get('target_doi') or 'N/A',
        }

        # 技术路线结果摘要
        tech_route = analysis_data.get('tech_route', {})
        similar_papers = tech_route.get('similar_papers', [])
        if similar_papers:
            summary['技术路线相似论文数'] = len(similar_papers)
            score = similar_papers[0].get('score', similar_papers[0].get('similarity_score', 0))
            summary['最高技术路线相似度'] = f"{score:.2%}"

        # 实验方案结果摘要
        exp_scheme = analysis_data.get('exp_scheme', {})
        dimensions = exp_scheme.get('dimensions', {})
        if dimensions:
            summary['实验方案维度数'] = len(dimensions)
            summary['实验方案类别'] = ', '.join([self.DIM_NAMES.get(k, k) for k in dimensions.keys()])

        # Jc 结果摘要
        jc_analysis = analysis_data.get('jc_analysis', {})
        jc_indicators = jc_analysis.get('jc_indicators', [])
        if jc_indicators:
            summary['提取 Jc 指标数'] = len(jc_indicators)
        ranking = jc_analysis.get('ranking', {})
        if ranking and ranking.get('success'):
            summary['Jc 排名'] = f"第{ranking.get('target_rank', 'N/A')}名"

        # PDF 信息
        pdf_info = analysis_data.get('pdf_info', {})
        if pdf_info:
            summary['NER 实体数'] = pdf_info.get('ner_entity_count', 0)
            summary['RE 关系数'] = pdf_info.get('re_relation_count', 0)

        return summary


# 全局服务实例
_report_service_instance = None


def get_report_service(output_dir: str = None) -> ReportService:
    """获取报告服务单例实例"""
    global _report_service_instance
    if _report_service_instance is None:
        from backend.app.core.config import RESULTS_DIR
        actual_dir = output_dir or str(Path(RESULTS_DIR) / "reports")
        _report_service_instance = ReportService(output_dir=actual_dir)
    return _report_service_instance