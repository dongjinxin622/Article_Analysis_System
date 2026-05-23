#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
使用真实NER/RE数据测试改进后的综合分析服务
"""
import sys
import os
import asyncio
import json

# Windows编码设置
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from loguru import logger


async def test_with_real_data():
    """使用真实数据测试"""
    from backend.app.services.comprehensive_service import get_comprehensive_service

    service = get_comprehensive_service()

    # 读取真实NER数据
    ner_path = Path("data/ner_results/ner_10.1016_j.physc.2012.10.010.json")
    re_path = Path("data/re_results/re_ner_10.1016_j.physc.2012.10.010_20260423223518.json")

    with open(ner_path, "r", encoding="utf-8") as f:
        ner_data = json.load(f)
    ner_entities = ner_data.get("entities", [])

    # 尝试读取RE数据
    re_relations = []
    if re_path.exists():
        with open(re_path, "r", encoding="utf-8") as f:
            re_data = json.load(f)
        re_relations = re_data.get("relations", [])

    # 读取PDF内容
    pdf_json_path = Path("data/results/10.1016_j.physc.2012.10.010.json")
    pdf_content = {}
    content_text = ""
    if pdf_json_path.exists():
        with open(pdf_json_path, "r", encoding="utf-8") as f:
            pdf_data = json.load(f)
        pdf_content = {
            "doi": pdf_data.get("doi", ""),
            "title": pdf_data.get("title", ""),
            "abstract": pdf_data.get("abstract", "")
        }
        # 提取原文内容
        sections = pdf_data.get("sections", [])
        content_text = "\n".join([s.get("text", "") for s in sections if s.get("text")])

    print("=" * 70)
    print("使用真实数据测试改进后的综合分析服务")
    print("=" * 70)
    print(f"\n数据来源: {ner_path}")
    print(f"NER实体数量: {len(ner_entities)}")
    print(f"RE关系数量: {len(re_relations)}")

    # ===== 测试1: Jc提取改进 =====
    print("\n" + "-" * 50)
    print("测试1: Jc指标提取改进")
    print("-" * 50)

    jc_result = service._extract_jc_conditions_improved(ner_entities, pdf_content)
    jc_indicators = jc_result.get("jc_indicators", [])

    print(f"\n提取到 {len(jc_indicators)} 个有效Jc指标:")
    if jc_indicators:
        print("\n| Jc值 | 单位 | 温度(K) | 磁场(T) | 来源 |")
        print("|------|------|---------|---------|------|")
        for jc in jc_indicators[:10]:
            jc_val = jc.get('jc_value', 'N/A')
            unit = jc.get('unit', 'A/cm²')
            temp = jc.get('temperature') or jc.get('jc_temp') or 'N/A'
            field = jc.get('magnetic_field') or jc.get('jc_field') or 'N/A'
            source = jc.get('entity_text', '')[:20]
            jc_str = f"{jc_val:.2e}" if isinstance(jc_val, (int, float)) else str(jc_val)
            print(f"| {jc_str} | {unit} | {temp} | {field} | {source} |")

    # 检查是否过滤了异常值
    print("\n异常值检查:")
    negative_values = [jc for jc in jc_indicators if jc.get('jc_value') and jc['jc_value'] < 0]
    zero_values = [jc for jc in jc_indicators if jc.get('jc_value') and jc['jc_value'] == 0]
    small_values = [jc for jc in jc_indicators if jc.get('jc_value') and 0 < jc['jc_value'] < 0.001]

    print(f"  - 负值数量: {len(negative_values)} (应为0)")
    print(f"  - 零值数量: {len(zero_values)} (应为0)")
    print(f"  - 过小值(<0.001)数量: {len(small_values)} (应为0)")

    # ===== 测试2: 8维度分类 =====
    print("\n" + "-" * 50)
    print("测试2: 完整8维度分类")
    print("-" * 50)

    dimensions = service._parse_dimensions(ner_entities)

    for dim_key, values in dimensions.items():
        dim_name = service.DIM_NAMES.get(dim_key, dim_key)
        count = len(values)
        if count > 0:
            print(f"\n{dim_name} ({count}项):")
            for v in values[:5]:
                print(f"  - {v}")
            if count > 5:
                print(f"  ... 共{count}项")

    # ===== 测试3: 技术路线构建 =====
    print("\n" + "-" * 50)
    print("测试3: 技术路线构建（含RE关系链）")
    print("-" * 50)

    tech_route_text = service._build_tech_route_text(ner_entities, re_relations)
    print(f"\n技术路线文本:")
    print(f"  {tech_route_text}")

    # ===== 测试4: 实验方案文本 =====
    print("\n" + "-" * 50)
    print("测试4: 实验方案文本（8维度）")
    print("-" * 50)

    exp_scheme_text = service._build_exp_scheme_text(ner_entities, pdf_content)
    print(f"\n实验方案文本:")
    print(f"  {exp_scheme_text}")

    # ===== 测试5: 生成完整报告 =====
    print("\n" + "-" * 50)
    print("测试5: 生成Markdown报告")
    print("-" * 50)

    result = {
        "success": True,
        "message": "真实数据测试完成",
        "timestamp": "2026-04-23T23:00:00",
        "tech_route": {
            "tech_route_text": tech_route_text,
            "similar_papers": []
        },
        "exp_scheme": {
            "exp_scheme_text": exp_scheme_text,
            "dimensions": dimensions
        },
        "jc_analysis": {
            "jc_indicators": jc_indicators,
            "conditions": {
                "temperature": jc_result.get("temperature"),
                "magnetic_field": jc_result.get("magnetic_field"),
                "angle": jc_result.get("angle")
            },
            "ranking": {}
        },
        "llm_comparison": ""
    }

    report = service._build_markdown_report(result)

    # 保存报告
    report_path = Path("data/results/real_data_test_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n报告已保存: {report_path}")
    print("\n报告预览 (前500字符):")
    print(report[:500])
    print("...")

    # ===== 对比原报告 =====
    print("\n" + "=" * 70)
    print("对比原报告")
    print("=" * 70)

    old_report_path = Path("data/results/comprehensive_reports/10.1016_j.physc.2012.10.010_20260423215231_e744b319_comprehensive_20260423_220335.md")
    if old_report_path.exists():
        with open(old_report_path, "r", encoding="utf-8") as f:
            old_report = f.read()

        # 提取原报告的Jc值部分
        print("\n原报告Jc值 (第44-57行):")
        old_jc_lines = old_report.split("\n")[44:57]
        for line in old_jc_lines:
            print(f"  {line}")

        print("\n" + "-" * 40)
        print("改进后报告Jc值:")
        new_jc_start = report.find("## 4. Jc指标分析")
        new_jc_end = report.find("## 5.")
        if new_jc_start > 0 and new_jc_end > 0:
            new_jc_section = report[new_jc_start:new_jc_end]
            print(new_jc_section[:300])

    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_with_real_data())