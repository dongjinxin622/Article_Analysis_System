"""
异步任务处理器 - 替代 ThreadPoolExecutor 的异步版本
支持批量 LLM API 调用，带重试机制
"""
import os
import json
import pickle
import logging
import asyncio
import re
import math
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from tqdm.asyncio import tqdm_asyncio
import json5

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class AsyncTaskProcessor:
    """异步任务处理器，支持批量 LLM API 调用"""

    def __init__(
        self,
        task_name: str,
        max_concurrent: int = 30,  # 并发数
        model: str = None,
        save_folder: str = "results",
        request_timeout: int = 120,  # 单次请求超时120秒
        rate_limit_delay: float = 0.3,  # 速率限制延迟
        max_retries: int = 3,  # 最大重试次数
        retry_delay: int = 10  # 重试间隔10秒
    ):
        """
        初始化异步任务处理器

        Args:
            task_name: 任务名称
            max_concurrent: 最大并发数
            model: 使用的模型名称（默认从 .env 读取）
            save_folder: 结果保存目录
            request_timeout: 单个请求超时时间（秒）
            rate_limit_delay: API 调用间隔（秒）
        """
        self.task_name = task_name
        self.max_concurrent = max_concurrent
        self.model = model or settings.MODEL_NAME
        self.save_folder = save_folder
        self.request_timeout = request_timeout
        self.rate_limit_delay = rate_limit_delay

        self.temperature = 0.1
        self.top_p = 0.9
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.input_dict: Dict = {}
        self.message_dict: Dict = {}
        self.save_path = f'{save_folder}/{self.task_name}_final_merged.pkl'

        # 并发统计
        self._active_count = 0
        self._max_active_seen = 0
        self._start_times: Dict = {}

        # 创建 OpenAI 客户端（异步版本使用 aiohttp）
        from openai import AsyncOpenAI
        import httpx

        logger.info(f"[并行处理] 初始化 TaskProcessor, max_concurrent={max_concurrent}, model={self.model}, timeout={request_timeout}s, retries={max_retries}")

        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout, connect=30.0),
            limits=httpx.Limits(max_connections=max_concurrent)
        )

        self.client = AsyncOpenAI(
            api_key=settings.API_KEY,
            base_url=settings.BASE_URL,
            http_client=self.http_client
        )

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()

    def load_query(self, query_file_path: str) -> str:
        """加载查询模板"""
        try:
            with open(query_file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            logger.warning(f"查询文件 {query_file_path} 未找到")
            return ""

    async def call_api(
        self,
        input_text: str,
        query_template: str,
        max_retries: int = None,
        extra_body: Optional[Dict] = None
    ) -> Tuple[List[Dict], str]:
        """
        调用 API 处理单个文本（异步版本，带重试机制）

        Args:
            input_text: 输入文本
            query_template: Prompt模板
            max_retries: 最大重试次数（None则使用实例默认）
            extra_body: 额外的请求体参数（如 {"enable_thinking": False}）

        Returns:
            (messages, raw_response)
        """
        if max_retries is None:
            max_retries = self.max_retries

        messages = [{"role": "user", "content": f"{query_template}\n目标文本：{input_text}"}]

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    top_p=self.top_p,
                    temperature=self.temperature,
                    response_format={"type": "json_object"},
                    extra_body=extra_body
                )

                raw_response = response.choices[0].message.content
                return messages, raw_response

            except Exception as e:
                error_msg = str(e).lower()
                is_timeout = 'timeout' in error_msg or 'timed out' in error_msg

                if is_timeout and attempt < max_retries - 1:
                    wait_time = self.retry_delay * (attempt + 1)  # 递增等待
                    logger.warning(f'请求超时，{wait_time}秒后重试 ({attempt + 1}/{max_retries})')
                    await asyncio.sleep(wait_time)
                elif is_timeout:
                    logger.error(f'请求超时，已达最大重试次数 ({max_retries})')
                    raise
                else:
                    raise

        raise Exception("API 调用失败：超过最大重试次数")

    def parse_response(self, response_text: str) -> Any:
        """解析 API 响应中的结构化数据"""
        if not response_text or not response_text.strip():
            return []

        try:
            # 首先尝试直接解析 JSON
            try:
                return json5.loads(response_text.strip())
            except:
                pass

            # 尝试提取 markdown 代码块中的 JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                return json5.loads(json_str)

            # 如果没有 markdown 标记，尝试直接解析
            return json5.loads(response_text.strip())
        except Exception as e:
            logger.warning(f"解析错误：{str(e)}")
            return []

    async def process_single_item(
        self,
        item: Tuple,
        query_template: str,
        processed_keys: set,
        semaphore: asyncio.Semaphore,
        retry_queue: List,
        task_start_time: float
    ) -> Optional[Dict]:
        """
        处理单个文档条目（异步版本）
        """
        key, content = item
        input_text = f"content: {content}"

        if key in processed_keys:
            logger.debug(f'跳过已处理文档：{key}')
            return None

        result = None

        async with semaphore:
            # 记录并发数
            self._active_count += 1
            self._max_active_seen = max(self._max_active_seen, self._active_count)
            start_time = asyncio.get_event_loop().time()
            elapsed_since_batch_start = start_time - task_start_time
            logger.debug(f"[并发] 开始处理 {key}, 当前并发数={self._active_count}, 最大={self._max_active_seen}")

            try:
                messages, raw_response = await self.call_api(input_text, query_template)

                try:
                    parsed_data = json5.loads(raw_response)
                except Exception as e:
                    logger.warning(f"解析错误 {key}: {str(e)}")
                    # 注意：不要在这里减少 _active_count，finally 块会处理
                    return None

                self.message_dict[key] = parsed_data

                # 随机保存机制
                if uuid.uuid4().int % 1000 == 0:
                    await self.save_temp()

                end_time = asyncio.get_event_loop().time()
                logger.debug(f"[并发] 完成 {key}, 耗时{end_time - start_time:.2f}秒")
                result = {key: parsed_data}

            except Exception as e:
                error_msg = str(e)
                if 'timeout' in error_msg.lower():
                    retry_queue.append(item)
                    logger.warning(f'处理超时 {key}，已加入重试队列')
                else:
                    logger.error(f'处理异常 {key}: {error_msg}')
            finally:
                self._active_count -= 1

        # rate_limit_delay 移到 semaphore 外部，不阻塞并发槽
        await asyncio.sleep(self.rate_limit_delay)
        return result

    async def save_temp(self, save_path: Optional[str] = None):
        """保存临时结果（异步版本）"""
        if not save_path:
            save_path = f'{self.save_folder}/{self.task_name}_temp.pkl'

        try:
            def _save():
                with open(save_path, 'wb') as f:
                    pickle.dump(self.message_dict, f)

            await asyncio.to_thread(_save)
            logger.info(f'进度已保存至：{save_path}')
        except Exception as e:
            logger.error(f'保存失败：{str(e)}')

    async def process_batch(
        self,
        data_list: List[Tuple],
        query_file_path: str,
        processed_keys: set = None,
        batch_size: int = 1000,
        max_retry_rounds: int = 3
    ) -> str:
        """
        批量处理数据（异步版本，带重试机制）
        """
        if processed_keys is None:
            processed_keys = set()

        query_template = self.load_query(query_file_path)
        if not query_template:
            return ""

        save_dir = f"{self.save_folder}/batch_results_{self.task_name}"
        Path(save_dir).mkdir(parents=True, exist_ok=True)

        total_batches = math.ceil(len(data_list) / batch_size)
        semaphore = asyncio.Semaphore(self.max_concurrent)

        for batch_idx in range(total_batches):
            start = batch_idx * batch_size
            end = min((batch_idx + 1) * batch_size, len(data_list))
            batch_data = data_list[start:end]

            if len(batch_data) == 0:
                continue

            batch_save_path = os.path.join(save_dir, f"batch_{batch_idx + 1}_start{start}_end{end - 1}.pkl")

            try:
                self.message_dict = {}
                retry_queue = []
                self._active_count = 0
                self._max_active_seen = 0
                task_start_time = asyncio.get_event_loop().time()

                logger.info(f"[并行处理] 批次 {batch_idx + 1} 开始, 共 {len(batch_data)} 个任务, max_concurrent={self.max_concurrent}")

                # 并发处理
                tasks = [
                    self.process_single_item(item, query_template, processed_keys, semaphore, retry_queue, task_start_time)
                    for item in batch_data
                ]

                results = await tqdm_asyncio.gather(*tasks, desc=f"处理批次 {batch_idx + 1}")

                batch_elapsed = asyncio.get_event_loop().time() - task_start_time
                logger.info(f"[并行处理] 批次 {batch_idx + 1} 完成, 耗时 {batch_elapsed:.2f}秒, 最大并发数={self._max_active_seen}, 平均速度={len(batch_data)/batch_elapsed:.2f}个/秒")

                # 处理重试队列
                for round_idx in range(max_retry_rounds):
                    if not retry_queue:
                        break

                    wait_time = 30 * (round_idx + 1)
                    logger.info(f"\n等待 {wait_time} 秒后开始第 {round_idx + 1} 轮重试...")
                    await asyncio.sleep(wait_time)

                    # 减少并发数进行重试
                    retry_semaphore = asyncio.Semaphore(max(5, self.max_concurrent // 3))
                    new_retry_queue = []

                    retry_tasks = [
                        self.process_single_item(item, query_template, processed_keys, retry_semaphore, new_retry_queue)
                        for item in retry_queue
                    ]

                    await tqdm_asyncio.gather(*retry_tasks, desc=f"重试轮次 {round_idx + 1}")
                    retry_queue = new_retry_queue

                if retry_queue:
                    failed_keys = [item[0] for item in retry_queue]
                    logger.warning(f"\n批次{batch_idx + 1}最终仍有{len(retry_queue)} 个任务失败")

                # 保存批次结果
                def _save_batch():
                    with open(batch_save_path, "wb") as f:
                        pickle.dump(self.message_dict, f)

                await asyncio.to_thread(_save_batch)
                logger.info(f"批次{batch_idx + 1}处理完成，保存至 {batch_save_path}")

            except Exception as e:
                logger.error(f"批次{batch_idx + 1}处理失败：{str(e)}")
                continue

        return save_dir

    async def merge_results(self, batch_dir: str) -> Dict:
        """合并批次结果（异步版本）"""
        final_result_dict = {}

        def _merge():
            batch_files = [f for f in os.listdir(batch_dir) if f.startswith("batch_") and f.endswith(".pkl")]

            if len(batch_files) == 0:
                raise FileNotFoundError(f"在 {batch_dir} 中未找到任何批次结果文件")

            for file_name in batch_files:
                file_path = os.path.join(batch_dir, file_name)
                try:
                    with open(file_path, "rb") as f:
                        batch_dict = pickle.load(f)

                    if isinstance(batch_dict, dict):
                        final_result_dict.update(batch_dict)
                        logger.info(f"合并 {file_name}：新增 {len(batch_dict)} 条数据")

                except Exception as e:
                    logger.error(f"读取文件 {file_name} 失败：{str(e)}")

            with open(self.save_path, "wb") as f:
                pickle.dump(final_result_dict, f)

            return final_result_dict

        result = await asyncio.to_thread(_merge)
        logger.info(f"合并完成，最终结果保存至：{self.save_path}")
        return result


async def process_with_llm(
    input_dict: Dict,
    query_file_path: str,
    task_name: str = "llm_task",
    max_concurrent: int = 30  # 并发数设置为30
) -> Dict:
    """
    使用 LLM API 批量处理数据的便捷函数

    Args:
        input_dict: 输入数据 {key: content}
        query_file_path: Prompt 模板文件路径
        task_name: 任务名称
        max_concurrent: 最大并发数

    Returns:
        处理结果字典
    """
    unique_task_name = f"{task_name}_{uuid.uuid4().hex[:8]}"
    processor = AsyncTaskProcessor(
        task_name=unique_task_name,
        max_concurrent=max_concurrent
    )

    try:
        data_list = list(input_dict.items())
        batch_dir = await processor.process_batch(data_list, query_file_path)
        result = await processor.merge_results(batch_dir)
        return result
    finally:
        await processor.close()