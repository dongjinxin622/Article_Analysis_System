"""
一键分析完整流程测试脚本（带配置文件读取）
测试 PDF → NER+RE流水线 → 技术路线 → 实验方案 → Jc → LLM报告 全流程
配置文件: blog/config.log
"""
import asyncio
import sys
import time
import os
import json
import re
import logging
from pathlib import Path

# 设置输出编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).parent))

from backend.app.core.config import settings, BASE_DIR
from backend.app.services.pdf_service import process_pdf
from backend.app.services.ner_re_pipeline import process_ner_re_pipeline
from backend.app.services.ner_service import load_ner_entities
from backend.app.services.re_service import load_re_relations
from backend.app.services.comprehensive_service import get_comprehensive_service


def load_config(config_path: str) -> dict:
    """从 .log 配置文件读取参数"""
    config = {
        'pdf_file': '10.2478_v10177-011-0030-y.pdf',
        'max_concurrent': 15,
        'chunk_timeout': 300,
        'request_timeout': 90,
        'max_retries': 3,
        'retry_delay': 15,
        'rate_limit_delay': 0.3,
        'log_level': 'DEBUG',
        'progress_interval': 10
    }

    if Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析配置
        for line in content.split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            match = re.match(r'^(\w+)\s*=\s*(.+)$', line)
            if match:
                key, value = match.groups()
                value = value.strip()

                # 转换类型
                if key in ['max_concurrent', 'chunk_timeout', 'request_timeout', 'max_retries', 'retry_delay', 'progress_interval']:
                    config[key] = int(value)
                elif key in ['rate_limit_delay']:
                    config[key] = float(value)
                elif key == 'pdf_file':
                    config[key] = value
                else:
                    config[key] = value

    return config


async def test_one_click_analysis():
    """测试一键分析完整流程"""

    # 读取配置
    config_path = BASE_DIR / "blog" / "config.log"
    config = load_config(str(config_path))

    print("=" * 70)
    print("一键分析完整流程测试")
    print("=" * 70)
    print(f"\n[配置文件] {config_path}")
    print(f"  PDF: {config['pdf_file']}")
    print(f"  并发: {config['max_concurrent']}")
    print(f"  块超时: {config['chunk_timeout']}s")
    print(f"  请求超时: {config['request_timeout']}s")
    print(f"  重试次数: {config['max_retries']}")
    print(f"  重试延迟: {config['retry_delay']}s")
    print(f"  Rate Delay: {config['rate_limit_delay']}s")

    # 设置日志级别
    logging.basicConfig(level=logging.getLevelName(config['log_level']))

    # 配置信息
    print(f"\n[LLM配置]")
    print(f"  MODEL: {settings.MODEL_NAME}")
    print(f"  BASE_URL: {settings.BASE_URL}")
    print(f"  API_KEY: {settings.API_KEY[:20]}...")

    # 测试PDF
    pdf_path = BASE_DIR / config['pdf_file']
    print(f"\n[测试文件] {pdf_path.name}")
    print(f"  路径: {pdf_path}")
    print(f"  存在: {pdf_path.exists()}")

    if not pdf_path.exists():
        print("错误: PDF文件不存在")
        return

    total_start = time.time()
    stage_times = {}

    # ========== Step 1: PDF解析 ==========
    print(f"\n{'='*60}")
    print("[Step 1] PDF解析")
    print("="*60)

    t0 = time.time()
    pdf_result = await process_pdf(
        str(pdf_path),
        pdf_path.name,
        max_retries=3,
        retry_delay=2,
        user_id=1
    )
    stage_times['pdf'] = time.time() - t0

    if not pdf_result.get("success"):
        print(f"  PDF解析失败: {pdf_result.get('error')}")
        return

    result_id = pdf_result["result_id"]
    doi = pdf_result.get("doi")
    print(f"  成功! result_id={result_id}, doi={doi}")
    print(f"  耗时: {stage_times['pdf']:.2f}s")

    # ========== Step 2+3: NER+RE流水线 ==========
    print(f"\n{'='*60}")
    print("[Step 2+3] NER+RE 流水线处理")
    print("="*60)

    # 查找Prompt文件
    ner_dir = BASE_DIR / "scipdf" / "ner_queries"
    re_dir = BASE_DIR / "scipdf" / "re_queries"
    ner_prompt = str(list(ner_dir.glob("*.txt"))[0]) if list(ner_dir.glob("*.txt")) else None
    re_prompt = str(list(re_dir.glob("*.txt"))[0]) if list(re_dir.glob("*.txt")) else None

    if not ner_prompt or not re_prompt:
        print(f"  错误: Prompt文件缺失")
        return

    print(f"  NER Prompt: {ner_prompt}")
    print(f"  RE Prompt: {re_prompt}")

    # 进度回调
    last_ner = 0
    last_re = 0
    progress_interval = config['progress_interval']

    async def progress_callback(stage, completed, total, message):
        nonlocal last_ner, last_re
        if stage == "ner" and completed > last_ner:
            last_ner = completed
            if completed % progress_interval == 0 or completed == total:
                pct = completed * 100 // total
                print(f"  [NER] {completed}/{total} ({pct}%)")
        elif stage == "re" and completed > last_re:
            last_re = completed
            if completed % progress_interval == 0 or completed == total:
                pct = completed * 100 // total
                print(f"  [RE] {completed}/{total} ({pct}%)")

    t0 = time.time()
    pipeline_result = await process_ner_re_pipeline(
        result_id=result_id,
        ner_query_file=ner_prompt,
        re_query_file=re_prompt,
        user_id=1,
        progress_callback=progress_callback,
        chunk_timeout=config['chunk_timeout'],
        max_concurrent=config['max_concurrent']
    )
    stage_times['ner_re'] = time.time() - t0

    if not pipeline_result.get("success"):
        print(f"  NER+RE失败: {pipeline_result.get('error')}")
        return

    ner_id = pipeline_result["ner_id"]
    re_id = pipeline_result["re_id"]
    entity_count = pipeline_result.get("entity_count", 0)
    relation_count = pipeline_result.get("relation_count", 0)

    print(f"\n  成功! ner_id={ner_id}, re_id={re_id}")
    print(f"  实体数: {entity_count}")
    print(f"  关系数: {relation_count}")
    print(f"  耗时: {stage_times['ner_re']:.2f}s")

    # 加载实体和关系用于后续分析
    ner_entities = await load_ner_entities(ner_id)
    re_relations = await load_re_relations(re_id)

    # ========== Step 4: 并行分析(技术路线+实验方案+Jc) ==========
    print(f"\n{'='*60}")
    print("[Step 4] 并行分析 (技术路线 + 实验方案 + Jc)")
    print("="*60)

    pdf_content = {
        "title": pdf_result.get("title", ""),
        "doi": doi,
        "abstract": pdf_result.get("abstract", "")
    }

    service = get_comprehensive_service()

    t0 = time.time()

    # 并行执行三个分析
    tech_route_task = service._analyze_tech_route(
        ner_entities=ner_entities,
        re_relations=re_relations,
        pdf_content=pdf_content,
        top_k=10
    )
    exp_scheme_task = service._analyze_exp_scheme(
        ner_entities=ner_entities,
        pdf_content=pdf_content,
        top_k=10
    )
    jc_task = service._analyze_jc(
        ner_entities=ner_entities,
        pdf_content=pdf_content,
        target_doi=doi,
        top_k=10
    )

    tech_route_result, exp_scheme_result, jc_result = await asyncio.gather(
        tech_route_task, exp_scheme_task, jc_task,
        return_exceptions=True
    )

    stage_times['parallel_analysis'] = time.time() - t0

    # 处理异常
    if isinstance(tech_route_result, Exception):
        print(f"  技术路线分析失败: {tech_route_result}")
        tech_route_result = {"success": False, "message": str(tech_route_result)}
    if isinstance(exp_scheme_result, Exception):
        print(f"  实验方案分析失败: {exp_scheme_result}")
        exp_scheme_result = {"success": False, "message": str(exp_scheme_result)}
    if isinstance(jc_result, Exception):
        print(f"  Jc分析失败: {jc_result}")
        jc_result = {"success": False, "message": str(jc_result)}

    print(f"  技术路线: success={tech_route_result.get('success')}, 相似论文={tech_route_result.get('similar_count', 0)}")
    print(f"  实验方案: success={exp_scheme_result.get('success')}, 相似论文={exp_scheme_result.get('similar_count', 0)}")
    print(f"  Jc分析: success={jc_result.get('success')}, Jc指标={len(jc_result.get('jc_indicators', []))}")
    print(f"  耗时: {stage_times['parallel_analysis']:.2f}s")

    # ========== Step 5: LLM综合分析 ==========
    print(f"\n{'='*60}")
    print("[Step 5] LLM综合分析报告")
    print("="*60)

    t0 = time.time()
    llm_comparison = await service._generate_llm_comparison(
        tech_route_result=tech_route_result,
        exp_scheme_result=exp_scheme_result,
        jc_result=jc_result,
        pdf_content=pdf_content
    )
    stage_times['llm'] = time.time() - t0

    print(f"  报告长度: {len(llm_comparison)} 字符")
    print(f"  耗时: {stage_times['llm']:.2f}s")

    # ========== Step 6: 生成报告 ==========
    print(f"\n{'='*60}")
    print("[Step 6] 生成报告")
    print("="*60)

    final_result = {
        "success": True,
        "message": "一键分析完成",
        "pdf_info": {
            "result_id": result_id,
            "ner_id": ner_id,
            "re_id": re_id,
            "doi": doi,
            "title": pdf_result.get("title"),
            "file_name": pdf_path.name,
            "ner_entity_count": entity_count,
            "re_relation_count": relation_count
        },
        "ner_entities": ner_entities,
        "re_relations": re_relations,
        "tech_route": tech_route_result,
        "exp_scheme": exp_scheme_result,
        "jc_analysis": jc_result,
        "llm_comparison": llm_comparison
    }

    t0 = time.time()
    report_path = await service._generate_report(final_result, str(pdf_path))
    stage_times['report'] = time.time() - t0

    print(f"  报告路径: {report_path}")
    print(f"  耗时: {stage_times['report']:.2f}s")

    # ========== 总计 ==========
    total_elapsed = time.time() - total_start

    print(f"\n{'='*70}")
    print("测试完成 - 时间统计")
    print("="*70)

    print(f"\n  各阶段耗时:")
    print(f"    PDF解析:      {stage_times['pdf']:>8.2f}s ({stage_times['pdf']*100//total_elapsed:>3}%)")
    print(f"    NER+RE流水线: {stage_times['ner_re']:>8.2f}s ({stage_times['ner_re']*100//total_elapsed:>3}%)")
    print(f"    并行分析:     {stage_times['parallel_analysis']:>8.2f}s ({stage_times['parallel_analysis']*100//total_elapsed:>3}%)")
    print(f"    LLM分析:      {stage_times['llm']:>8.2f}s ({stage_times['llm']*100//total_elapsed:>3}%)")
    print(f"    报告生成:     {stage_times['report']:>8.2f}s ({stage_times['report']*100//total_elapsed:>3}%)")
    print(f"\n  总耗时: {total_elapsed:.2f}s ({total_elapsed/60:.1f}分钟)")

    print(f"\n  结果统计:")
    print(f"    实体数: {entity_count}")
    print(f"    关系数: {relation_count}")
    print(f"    技术路线相似论文: {tech_route_result.get('similar_count', 0)}")
    print(f"    实验方案相似论文: {exp_scheme_result.get('similar_count', 0)}")
    print(f"    Jc指标数: {len(jc_result.get('jc_indicators', []))}")

    if entity_count > 0:
        avg_time_per_entity = stage_times['ner_re'] / entity_count
        print(f"\n  NER+RE效率:")
        print(f"    平均每实体耗时: {avg_time_per_entity:.3f}s")

    # 保存结果到日志
    result_log_path = BASE_DIR / "blog" / f"result_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with open(result_log_path, 'w', encoding='utf-8') as f:
        f.write(f"# Test Result Log\n")
        f.write(f"# Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"pdf_file = {config['pdf_file']}\n")
        f.write(f"result_id = {result_id}\n")
        f.write(f"ner_id = {ner_id}\n")
        f.write(f"re_id = {re_id}\n")
        f.write(f"entity_count = {entity_count}\n")
        f.write(f"relation_count = {relation_count}\n")
        f.write(f"total_time = {total_elapsed:.2f}s\n")
        f.write(f"ner_re_time = {stage_times['ner_re']:.2f}s\n")

    print(f"\n  结果日志: {result_log_path}")
    print("="*70)

    return final_result


async def main():
    """主函数"""
    try:
        result = await test_one_click_analysis()
        if result and result.get("success"):
            print("\n✓ 测试成功!")
        else:
            print("\n✗ 测试失败")
    except Exception as e:
        import traceback
        print(f"\n✗ 测试异常: {e}")
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())