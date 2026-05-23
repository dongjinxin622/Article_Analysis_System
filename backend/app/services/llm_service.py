"""
LLM 服务 - 处理 OpenAI/Qwen API 调用
"""
import os
import json
import logging
import asyncio
import re
from typing import Dict, Any, Optional, List
from pathlib import Path
import json5

from backend.app.core.config import settings
from openai import AsyncOpenAI
import httpx

logger = logging.getLogger(__name__)


class LLMService:
    """LLM 服务类"""

    def __init__(
        self,
        api_key: str = None,
        base_url: str = None,
        model: str = None,
        temperature: float = 0.1,
        top_p: float = 0.9,
        request_timeout: int = 180
    ):
        """
        初始化 LLM 服务

        Args:
            api_key: API 密钥（默认从配置读取）
            base_url: API 基础 URL（默认从配置读取）
            model: 模型名称（默认从配置读取）
            temperature: 温度参数
            top_p: Top-P 参数
            request_timeout: 请求超时时间（秒）
        """
        self.api_key = api_key or settings.API_KEY
        self.base_url = base_url or settings.BASE_URL
        self.model = model or settings.MODEL_NAME
        self.temperature = temperature
        self.top_p = top_p
        self.request_timeout = request_timeout

        # 创建异步 HTTP 客户端
        self.http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(request_timeout, connect=30.0),
            limits=httpx.Limits(max_connections=100)
        )

        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            http_client=self.http_client
        )

    async def close(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()

    async def chat(
        self,
        user_message: str,
        system_message: Optional[str] = None,
        json_mode: bool = True,
        max_retries: int = 3
    ) -> str:
        """
        发送聊天请求

        Args:
            user_message: 用户消息
            system_message: 系统消息（可选）
            json_mode: 是否使用 JSON 模式
            max_retries: 最大重试次数

        Returns:
            模型响应文本
        """
        messages = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        messages.append({"role": "user", "content": user_message})

        for attempt in range(max_retries):
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    top_p=self.top_p,
                    response_format={"type": "json_object"} if json_mode else None
                )

                return response.choices[0].message.content

            except Exception as e:
                error_msg = str(e).lower()
                is_timeout = 'timeout' in error_msg

                if is_timeout and attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 10
                    logger.warning(f'请求超时，{wait_time}秒后重试')
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f'LLM API 调用失败: {error_msg}')
                    raise

        raise Exception("LLM API 调用失败：超过最大重试次数")

    async def chat_with_prompt_template(
        self,
        input_text: str,
        prompt_file_path: str,
        max_retries: int = 3
    ) -> str:
        """
        使用 Prompt 模板文件发送聊天请求

        Args:
            input_text: 输入文本
            prompt_file_path: Prompt 模板文件路径
            max_retries: 最大重试次数

        Returns:
            模型响应文本
        """
        # 加载 Prompt 模板
        try:
            with open(prompt_file_path, 'r', encoding='utf-8') as f:
                prompt_template = f.read()
        except FileNotFoundError:
            logger.error(f"Prompt 文件不存在: {prompt_file_path}")
            raise

        # 构建消息
        user_message = f"{prompt_template}\n目标文本：{input_text}"

        return await self.chat(user_message, json_mode=True, max_retries=max_retries)

    def parse_json_response(self, response_text: str) -> Any:
        """
        解析 JSON 响应

        Args:
            response_text: 响应文本

        Returns:
            解析后的数据
        """
        if not response_text or not response_text.strip():
            return []

        try:
            # 首先尝试直接解析
            try:
                return json5.loads(response_text.strip())
            except:
                pass

            # 尝试提取 markdown 代码块中的 JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                return json5.loads(json_match.group(1))

            # 尝试提取 ``` 代码块
            code_match = re.search(r'```\s*(.*?)\s*```', response_text, re.DOTALL)
            if code_match:
                return json5.loads(code_match.group(1))

            return json5.loads(response_text.strip())
        except Exception as e:
            logger.warning(f"JSON 解析失败: {str(e)}")
            return None

    async def batch_process(
        self,
        inputs: Dict[str, str],
        prompt_file_path: str,
        max_concurrent: int = 50
    ) -> Dict[str, Any]:
        """
        批量处理输入数据

        Args:
            inputs: 输入数据字典 {key: text}
            prompt_file_path: Prompt 模板文件路径
            max_concurrent: 最大并发数

        Returns:
            处理结果字典 {key: parsed_result}
        """
        from backend.app.utils.task_processor import process_with_llm

        return await process_with_llm(
            input_dict=inputs,
            query_file_path=prompt_file_path,
            max_concurrent=max_concurrent
        )


# 全局 LLM 服务实例（懒加载）
_llm_service: Optional[LLMService] = None


async def get_llm_service() -> LLMService:
    """获取 LLM 服务实例"""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service