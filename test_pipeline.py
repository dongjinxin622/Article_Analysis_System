"""
测试 NER+RE 流水线
"""
import asyncio
import sys
import time
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

from backend.app.core.config import settings, BASE_DIR
from backend.app.services.pdf_service import process_pdf
from backend.app.services.ner_re_pipeline import process_ner_re_pipeline
from backend.app.services.ner_service import load_ner_entities
from backend.app.services.re_service import load_re_relations


async def main():
    print("=" * 60)
    print("NER+RE 流水线测试")
    print("=" * 60)
    print(f"  MODEL: {settings.MODEL_NAME}")
    print(f"  BASE_URL: {settings.BASE_URL}")
    print(f"  并发: 30, 延迟: 0.1s")

    pdf_path = BASE_DIR / "10.1134_S0020168522130015.pdf"
    if not pdf_path.exists():
        print(f"错误: PDF 不存在 {pdf_path}")
        return

    # Step 1: PDF 解析
    print(f"\n[1] PDF 解析: {pdf_path.name}")
    t0 = time.time()
    pdf_result = await process_pdf(str(pdf_path), pdf_path.name, user_id=1)
    print(f"  耗时: {time.time()-t0:.2f}s, result_id={pdf_result.get('result_id')}")
    if not pdf_result.get("success"):
        print(f"  PDF解析失败: {pdf_result.get('error')}")
        return

    result_id = pdf_result["result_id"]

    # 查找 Prompt 文件
    ner_dir = BASE_DIR / "scipdf" / "ner_queries"
    re_dir = BASE_DIR / "scipdf" / "re_queries"
    ner_prompt = str(list(ner_dir.glob("*.txt"))[0]) if list(ner_dir.glob("*.txt")) else None
    re_prompt = str(list(re_dir.glob("*.txt"))[0]) if list(re_dir.glob("*.txt")) else None

    if not ner_prompt or not re_prompt:
        print(f"错误: Prompt 文件缺失 (NER={ner_prompt}, RE={re_prompt})")
        return

    # 进度追踪
    ner_times = []
    re_times = []

    async def progress_callback(stage, completed, total, message):
        if stage == "ner":
            ner_times.append(time.time())
        else:
            re_times.append(time.time())
        if completed % 20 == 0 or completed == total:
            print(f"  [{stage.upper()}] {message}")

    # Step 2: NER+RE 流水线
    print(f"\n[2] NER+RE 流水线处理")
    print(f"  NER Prompt: {ner_prompt}")
    print(f"  RE Prompt: {re_prompt}")
    t0 = time.time()

    pipeline_result = await process_ner_re_pipeline(
        result_id=result_id,
        ner_query_file=ner_prompt,
        re_query_file=re_prompt,
        user_id=1,
        progress_callback=progress_callback
    )

    total_elapsed = time.time() - t0

    print(f"\n  总耗时: {total_elapsed:.2f}s")
    print(f"  成功: {pipeline_result.get('success')}")
    print(f"  实体数: {pipeline_result.get('entity_count')}")
    print(f"  关系数: {pipeline_result.get('relation_count')}")
    print(f"  NER ID: {pipeline_result.get('ner_id')}")
    print(f"  RE ID: {pipeline_result.get('re_id')}")

    if pipeline_result.get('entity_count', 0) > 0:
        print(f"  平均每实体耗时: {total_elapsed/pipeline_result['entity_count']:.3f}s")

    # 分析时间线
    if ner_times and re_times:
        print(f"\n  [时间线分析]")
        first_ner = ner_times[0] - t0
        last_ner = ner_times[-1] - t0
        first_re = re_times[0] - t0
        last_re = re_times[-1] - t0
        print(f"  NER 开始: {first_ner:.1f}s")
        print(f"  NER 结束: {last_ner:.1f}s")
        print(f"  RE 开始: {first_re:.1f}s")
        print(f"  RE 结束: {last_re:.1f}s")
        print(f"  RE与NER重叠时间: {last_ner - first_re:.1f}s (越大说明流水线效果越好)")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
