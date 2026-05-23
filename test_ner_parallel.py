"""
NER/RE 并行处理测试脚本
监测并行执行情况，验证并发数是否正确
"""
import asyncio
import sys
import time
import os
from pathlib import Path

# 设置输出编码
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from backend.app.core.config import settings, BASE_DIR
from backend.app.services.pdf_service import process_pdf
from backend.app.services.ner_service import (
    prepare_sentences_from_pdf,
    group_sentences,
    process_ner_with_llm,
    load_ner_entities
)
from backend.app.services.re_service import process_re_for_ner
from backend.app.utils.task_processor import AsyncTaskProcessor


async def test_ner_parallel():
    """测试 NER 并行处理"""

    print("=" * 60)
    print("NER/RE 并行处理测试")
    print("=" * 60)

    # 打印配置信息
    print(f"\n[配置信息]")
    print(f"  BASE_DIR: {BASE_DIR}")
    print(f"  API_KEY: {settings.API_KEY[:20]}...")
    print(f"  BASE_URL: {settings.BASE_URL}")
    print(f"  MODEL_NAME: {settings.MODEL_NAME}")
    print(f"  MAX_CONCURRENT: 20 (默认)")

    # 测试 PDF 文件
    pdf_path = BASE_DIR / "10.1134_S0020168522130015.pdf"
    print(f"\n[测试文件]")
    print(f"  PDF路径: {pdf_path}")
    print(f"  文件存在: {pdf_path.exists()}")

    if not pdf_path.exists():
        print("错误: PDF 文件不存在")
        return

    # Step 1: PDF 解析
    print(f"\n[Step 1] PDF 解析...")
    start_time = time.time()

    pdf_result = await process_pdf(
        str(pdf_path),
        pdf_path.name,
        max_retries=settings.PDF_MAX_RETRIES,
        retry_delay=settings.PDF_RETRY_DELAY,
        user_id=1
    )

    pdf_elapsed = time.time() - start_time
    print(f"  PDF解析耗时: {pdf_elapsed:.2f}秒")
    print(f"  结果: success={pdf_result.get('success')}, result_id={pdf_result.get('result_id')}")

    if not pdf_result.get('success'):
        print(f"  错误: {pdf_result.get('error')}")
        return

    result_id = pdf_result.get('result_id')

    # Step 2: 准备句子数据
    print(f"\n[Step 2] 准备句子数据...")
    start_time = time.time()

    parse_result, sentences_data = await prepare_sentences_from_pdf(
        result_id=result_id,
        skip_introduction=True
    )

    prepare_elapsed = time.time() - start_time
    print(f"  准备耗时: {prepare_elapsed:.2f}秒")
    print(f"  章节数: {len(sentences_data)}")

    if not sentences_data:
        print("错误: 没有有效的章节内容")
        return

    # Step 3: 句子分组
    print(f"\n[Step 3] 句子分组...")
    grouped_data = group_sentences(
        sentences_data=sentences_data,
        group_size=5,
        keep_abstract_intact=True
    )
    print(f"  分组数: {len(grouped_data)}")
    # 只显示分组结构，不显示具体内容（避免编码问题）
    if grouped_data:
        first = grouped_data[0]
        print(f"  示例分组结构: [doi, section_idx={first[1]}, group_idx={first[2]}, heading={first[3] if len(first[3]) < 20 else first[3][:20]+'...'}, text_len={len(first[4]) if len(first) > 4 else 0}]")

    # Step 4: NER 处理 (并行)
    print(f"\n[Step 4] NER 并行处理...")
    print(f"  并发数设置: 30")
    print(f"  速率延迟: 0.1s")

    # 查找 NER prompt 文件
    ner_prompt_dir = BASE_DIR / "scipdf" / "ner_queries"
    ner_prompt_file = None
    if ner_prompt_dir.exists():
        for f in ner_prompt_dir.glob("*.txt"):
            ner_prompt_file = str(f)
            break

    if not ner_prompt_file:
        print("错误: 未找到 NER prompt 文件")
        return

    print(f"  NER Prompt: {ner_prompt_file}")

    start_time = time.time()

    # 直接使用 AsyncTaskProcessor 测试并行
    processor = AsyncTaskProcessor(
        task_name=f"test_ner_{time.strftime('%Y%m%d%H%M%S')}",
        max_concurrent=30,
        rate_limit_delay=0.1,
        model=settings.MODEL_NAME
    )

    print(f"\n  [并行监测开始]")
    print(f"  任务数: {len(grouped_data)}")
    print(f"  预期并发数: 30")

    # 构建输入数据
    input_dict = {}
    for item in grouped_data:
        doi, section_idx, group_idx, heading, text = item
        key = (doi, section_idx, group_idx)
        input_dict[key] = {"content": text}

    # 加载 prompt
    query_template = processor.load_query(ner_prompt_file)

    # 准备数据列表
    data_list = list(input_dict.items())

    # 创建信号量
    semaphore = asyncio.Semaphore(30)

    # 记录并发统计
    active_count = 0
    max_active = 0
    task_start_times = {}
    completed_count = 0

    async def process_with_monitoring(item):
        """带并发监测的处理"""
        nonlocal active_count, max_active, completed_count

        key, content = item
        input_text = f"content: {content}"
        key_str = f"{key[1]}-{key[2]}"  # 只显示 section_idx 和 group_idx

        async with semaphore:
            active_count += 1
            max_active = max(max_active, active_count)
            enter_time = time.time()
            print(f"    [并发] 进入任务 {key_str}, 当前并发={active_count}, 最大={max_active}")

            try:
                messages, raw_response = await processor.call_api(input_text, query_template)
                elapsed = time.time() - enter_time
                completed_count += 1
                print(f"    [完成] 任务 {key_str}, 耗时={elapsed:.2f}s, 并发={active_count}")

                try:
                    import json5
                    parsed_data = json5.loads(raw_response)
                    return {key: parsed_data}
                except:
                    return None
            except Exception as e:
                print(f"    [错误] 任务 {key_str}: {str(e)[:50]}")
                return None
            finally:
                active_count -= 1

        await asyncio.sleep(0.5)

    # 并行执行所有任务
    tasks = [process_with_monitoring(item) for item in data_list]

    print(f"\n  开始并行处理 {len(tasks)} 个任务...")
    results = await asyncio.gather(*tasks, return_exceptions=True)

    ner_elapsed = time.time() - start_time

    print(f"\n  [NER 并行统计]")
    print(f"  总耗时: {ner_elapsed:.2f}秒")
    print(f"  任务数: {len(tasks)}")
    print(f"  最大并发数: {max_active}")
    print(f"  完成数: {completed_count}")
    print(f"  平均速度: {completed_count/ner_elapsed:.2f}个/秒")
    print(f"  理论速度(串行): ~{len(tasks)*2:.2f}秒 (按每个2秒计算)")
    print(f"  加速比: {len(tasks)*2/ner_elapsed:.2f}x")

    await processor.close()

    # 检查是否真正并行
    if max_active >= 25:
        print(f"\n  ✓ 并行正常工作！最大并发达到 {max_active}")
    else:
        print(f"\n  ✗ 并行可能有问题，最大并发仅 {max_active}，预期接近30")

    return {
        "ner_elapsed": ner_elapsed,
        "max_concurrent": max_active,
        "completed_count": completed_count,
        "speed": completed_count/ner_elapsed
    }


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("开始测试 NER/RE 并行处理")
    print("=" * 60 + "\n")

    result = await test_ner_parallel()

    if result:
        print("\n" + "=" * 60)
        print("测试结果总结")
        print("=" * 60)
        print(f"  NER 处理耗时: {result['ner_elapsed']:.2f}秒")
        print(f"  最大并发数: {result['max_concurrent']}")
        print(f"  完成任务数: {result['completed_count']}")
        print(f"  处理速度: {result['speed']:.2f}个/秒")

        if result['max_concurrent'] >= 15:
            print("\n  结论: 并行处理正常工作")
        else:
            print("\n  结论: 需要检查并行配置")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())