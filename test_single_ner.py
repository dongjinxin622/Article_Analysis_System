"""
测试单个块的 NER 解析
验证 API 返回和解析逻辑
"""
import asyncio
import sys
import os

os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))

import json
import json5
from backend.app.core.config import settings, BASE_DIR
from backend.app.services.pdf_service import load_result_json
from backend.app.services.ner_service import prepare_sentences_from_pdf, group_sentences
from backend.app.utils.task_processor import AsyncTaskProcessor


async def test_single_ner():
    """测试单个块的 NER 解析"""

    result_id = "10.2478_v10177-011-0030-y"

    # 加载 PDF 数据
    parse_result = await load_result_json(result_id)
    if not parse_result:
        print("PDF 解析结果不存在")
        return

    print(f"PDF Title: {parse_result.get('title', 'N/A')}")
    print(f"Sections: {len(parse_result.get('sections', []))}")

    # 准备句子
    _, sentences_data = await prepare_sentences_from_pdf(result_id, skip_introduction=True)
    grouped_data = group_sentences(sentences_data, group_size=5, keep_abstract_intact=True)

    print(f"Total chunks: {len(grouped_data)}")

    # 只测试第一个块
    if grouped_data:
        first_chunk = grouped_data[0]
        doi, section_idx, group_idx, heading, text = first_chunk
        print(f"\n测试第一个块:")
        print(f"  DOI: {doi}")
        print(f"  Section: {section_idx}")
        print(f"  Heading: {heading}")
        print(f"  Text length: {len(text)}")

        # 加载 NER prompt
        ner_prompt = BASE_DIR / "scipdf" / "ner_queries" / "material_ner.txt"
        with open(ner_prompt, 'r', encoding='utf-8') as f:
            query_template = f.read()

        # 创建处理器
        processor = AsyncTaskProcessor(
            task_name="test_single_ner",
            max_concurrent=1,
            rate_limit_delay=0.5,
            request_timeout=90,
            model=settings.MODEL_NAME
        )

        try:
            # 调用 API
            ner_input = f"content: {text}"
            print(f"\n调用 API...")
            _, ner_raw = await processor.call_api(ner_input, query_template)

            print(f"\n原始响应 (前500字符):")
            print(ner_raw[:500] if ner_raw else "Empty")

            # 解析
            print(f"\n解析 JSON...")
            ner_parsed = json5.loads(ner_raw)
            print(f"解析结果类型: {type(ner_parsed)}")
            print(f"解析结果: {json.dumps(ner_parsed, ensure_ascii=False, indent=2)[:1000]}")

            # 提取实体
            chunk_entities = []
            if isinstance(ner_parsed, list):
                for ent in ner_parsed:
                    if isinstance(ent, dict):
                        ent['doi'] = doi
                        ent['section_idx'] = section_idx
                        ent['group_idx'] = group_idx
                        chunk_entities.append(ent)
                print(f"\n提取实体数: {len(chunk_entities)}")
            elif isinstance(ner_parsed, dict):
                # 如果返回的是 dict，检查是否有 entities key
                if 'entities' in ner_parsed:
                    for ent in ner_parsed['entities']:
                        if isinstance(ent, dict):
                            ent['doi'] = doi
                            ent['section_idx'] = section_idx
                            ent['group_idx'] = group_idx
                            chunk_entities.append(ent)
                    print(f"\n从 'entities' key 提取实体数: {len(chunk_entities)}")
                else:
                    ner_parsed['doi'] = doi
                    ner_parsed['section_idx'] = section_idx
                    ner_parsed['group_idx'] = group_idx
                    chunk_entities.append(ner_parsed)
                    print(f"\n单个 dict 实体提取: 1")

            print(f"\n实体列表:")
            for i, ent in enumerate(chunk_entities[:5]):
                print(f"  {i+1}. {ent.get('type', 'N/A')} - {ent.get('symbol', 'N/A')}")

        finally:
            await processor.close()


if __name__ == "__main__":
    asyncio.run(test_single_ner())