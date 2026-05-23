#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
直接测试综合分析服务
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

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathlib import Path
from loguru import logger

# 配置日志
logger.add(sys.stderr, level="INFO")


async def test_comprehensive_service():
    """测试综合分析服务"""
    from backend.app.services.comprehensive_service import get_comprehensive_service

    service = get_comprehensive_service()

    # 模拟NER实体数据（参考V2格式）
    ner_entities = [
        {
            "type": "Material",
            "subtype": "Material_Fabrication",
            "symbol": "YBCO",
            "entity_text": "YBCO coated conductor",
            "value": None,
            "parameters": []
        },
        {
            "type": "Deposition",
            "subtype": "Deposition_Techniques",
            "symbol": "MOD",
            "entity_text": "metal organic deposition",
            "value": None,
            "parameters": []
        },
        {
            "type": "Jc",
            "subtype": "Jc_Value",
            "symbol": "Jc",
            "entity_text": "Jc = 1.5 MA/cm2",
            "value": 1500000,  # 1.5 MA/cm2 = 1500000 A/cm2
            "unit": "A/cm²",
            "parameters": [
                {"type": "temperature", "value": 77, "unit": "K"},
                {"type": "magnetic_field", "value": 0, "unit": "T"}
            ]
        },
        {
            "type": "Jc",
            "subtype": "Jc_Value",
            "symbol": "Jc",
            "entity_text": "Jc = 3.0 MA/cm2 at 65K",
            "value": 3000000,
            "unit": "A/cm²",
            "parameters": [
                {"type": "temperature", "value": 65, "unit": "K"},
                {"type": "magnetic_field", "value": 0, "unit": "T"}
            ]
        },
        {
            "type": "Jc",
            "subtype": "Jc_Value",
            "symbol": "Jc",
            "entity_text": "Jc at 77K, 1T",
            "value": 0.5,  # 测试异常值过滤（<0.001会被过滤）
            "unit": "MA/cm²",
            "parameters": []
        },
        {
            "type": "Jc",
            "subtype": "Jc_Value",
            "symbol": "Jc",
            "entity_text": "Jc = -1.0 MA/cm2",  # 测试负值过滤
            "value": -1.0,
            "unit": "MA/cm²",
            "parameters": []
        },
        {
            "type": "Temperature",
            "symbol": "T",
            "entity_text": "77K",
            "value": 77,
            "parameters": []
        },
        {
            "type": "Process",
            "subtype": "Post-Processing",
            "symbol": "annealing",
            "entity_text": "thermal annealing at 800C",
            "parameters": []
        },
        {
            "type": "Characterization",
            "subtype": "Characterization_Techniques",
            "symbol": "XRD",
            "entity_text": "X-ray diffraction",
            "parameters": []
        }
    ]

    # 模拟RE关系数据
    re_relations = [
        {
            "source_entity": "YBCO",
            "target_entity": "MOD",
            "relation_type": "synthesized_by"
        },
        {
            "source_entity": "MOD",
            "target_entity": "Jc",
            "relation_type": "produces"
        },
        {
            "source_entity": "annealing",
            "target_entity": "Jc",
            "relation_type": "enhances"
        }
    ]

    # 模拟PDF内容
    pdf_content = {
        "doi": "10.1016/j.physc.2012.10.010",
        "title": "High performance YBCO coated conductor by MOD process",
        "abstract": "We report high critical current density YBCO coated conductor..."
    }

    # 模拟原文内容（用于LLM补充Jc条件）
    content_text = """
    The critical current density (Jc) measurements were performed at various temperatures
    and magnetic fields. At 77K in self-field (0T), we achieved Jc of 1.5 MA/cm².
    At 65K and 0.5T magnetic field, Jc reached 2.0 MA/cm².
    The angular dependence of Jc was measured at 77K, 1T, showing peak values at 0°.
    """

    print("=" * 60)
    print("测试综合分析服务 - 改进版")
    print("=" * 60)

    # 测试Jc提取改进
    print("\n1. 测试Jc提取改进（过滤异常值）...")
    jc_conditions = service._extract_jc_conditions_improved(ner_entities, pdf_content)
    print(f"   有效Jc指标数量: {len(jc_conditions['jc_indicators'])}")
    for jc in jc_conditions['jc_indicators']:
        print(f"   - Jc={jc['jc_value']} {jc['unit']} (T={jc['temperature']}K, B={jc['magnetic_field']}T)")

    # 测试8维度分类
    print("\n2. 测试完整8维度分类...")
    dimensions = service._parse_dimensions(ner_entities)
    for dim_key, values in dimensions.items():
        if values:
            dim_name = service.DIM_NAMES.get(dim_key, dim_key)
            print(f"   {dim_name}: {', '.join(values)}")

    # 测试技术路线构建（含RE关系）
    print("\n3. 测试技术路线构建（含RE关系链）...")
    tech_route_text = service._build_tech_route_text(ner_entities, re_relations)
    print(f"   技术路线: {tech_route_text}")

    # 测试实验方案文本构建
    print("\n4. 测试实验方案文本构建...")
    exp_scheme_text = service._build_exp_scheme_text(ner_entities, pdf_content)
    print(f"   实验方案: {exp_scheme_text}")

    # 测试Markdown报告构建
    print("\n5. 测试Markdown报告构建...")
    result = {
        "success": True,
        "message": "测试完成",
        "timestamp": "2026-04-23T22:30:00",
        "tech_route": {
            "tech_route_text": tech_route_text,
            "similar_papers": [
                {"doi": "10.1234/test1", "title": "Test Paper 1", "score": 0.85},
                {"doi": "10.1234/test2", "title": "Test Paper 2", "score": 0.72}
            ]
        },
        "exp_scheme": {
            "exp_scheme_text": exp_scheme_text,
            "dimensions": dimensions
        },
        "jc_analysis": {
            "jc_indicators": jc_conditions['jc_indicators'],
            "ranking": {
                "success": True,
                "target_doi": "10.1016/j.physc.2012.10.010",
                "target_jc_max": 3000000,
                "target_rank": 5,
                "total_papers": 100,
                "rank_percentile": 0.95
            }
        },
        "llm_comparison": "### 测试LLM分析结果\n这是模拟的LLM对比分析报告内容。"
    }

    report = service._build_markdown_report(result)
    print("\n--- 报告预览 ---")
    print(report[:500])
    print("...")

    # 保存完整报告
    report_path = Path("data/results/test_comprehensive_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n完整报告已保存: {report_path}")

    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_comprehensive_service())