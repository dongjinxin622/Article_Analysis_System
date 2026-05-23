"""
HITL 对话 LLM 服务
实现智能对话 HITL，理解用户意图，生成友好回复
"""
import json
import logging
from typing import Dict, List, Optional, Any
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


# HITL 系统提示词模板
HITL_SYSTEM_PROMPT_TEMPLATE = """你是批量数据处理任务的智能助手。你的职责是：
1. 用清晰友好的语言向用户解释当前遇到的问题
2. 提供多个处理方案供用户选择
3. 回答用户关于数据的任何问题
4. 将用户的自然语言回复转化为系统可执行的动作

当前情况：
- 检查类型：{check_type}
- 问题描述：{error_message}
- 影响范围：{affected_count} 条记录 / 总共 {total_count} 条
- 可选动作：{available_actions}

回复格式要求：
- 用自然语言解释问题（用 Markdown 格式）
- 列出建议的处理方案（用列表格式）
- 结尾询问用户意图
- 如果用户回复不是标准动作，解析其真实意图并给出建议

注意：不要使用过于技术化的语言，让用户容易理解。
"""


INTENT_PARSE_PROMPT_TEMPLATE = """请分析用户的意图，将其转化为系统可执行的动作。

用户输入："{user_message}"

可选动作：{available_actions}
当前检查类型：{check_type}

请返回 JSON 格式的结果：
{
    "action": "动作名称",
    "data": {},
    "confidence": 0.0-1.0,
    "reasoning": "解析理由"
}

**重要规则**：

1. **有效指令识别**：只有以下输入才应该被识别为有效动作：
   - 明确的指令关键词（如：确认、接受、继续、编辑、修改、终止、取消、重试等）
   - 对应的英文指令（如：accept, continue, edit, terminate, retry等）
   - 明确的同意/不同意表达（如：好的、同意、可以、没问题 vs 算了、取消、不做了）

2. **无效输入判断**：以下输入应该返回 "invalid_input"：
   - 数学计算（如：1+1、3*5、计算一下）
   - 纯数字（如：123、456）
   - 闲聊内容（如：天气怎么样、你好）
   - 与当前任务完全无关的任何内容
   - 无法明确识别为有效动作的输入

3. 当返回 "invalid_input" 时：
   - action: "invalid_input"
   - data: {"original_input": "用户的原始输入"}
   - confidence: 0.9
   - reasoning: "简要说明为什么这是无效输入"

4. 有效意图映射：
   - "好的"、"同意"、"可以"、"继续"、"没问题"、"导出"、"确认"、"接受" → "continue" 或 "accept"
   - "编辑"、"修改"、"改一下" → "edit" 或 "modify"
   - "算了"、"取消"、"停止"、"退出"、"终止" → "terminate"
   - "重新生成"、"再试一次"、"重试" → "retry" 或 "regenerate"
   - "查看"、"看看"、"展示"、"失败列表" → "view_failed"
   - 用户提问（为什么、怎么、什么）→ "ask_more"

请严格按照以上规则判断，不要将无关输入错误地映射为有效动作。
"""


class HITLConversationLLM:
    """HITL 对话 LLM 服务"""

    def __init__(self, model: str = None, temperature: float = 0.7):
        """
        初始化 HITL 对话服务

        Args:
            model: LLM 模型名称（默认从 .env 读取）
            temperature: 温度参数（较高的温度使回复更自然）
        """
        self.model = model or settings.MODEL_NAME
        self.temperature = temperature
        self.llm = None
        self._initialized = False

    def _init_llm(self):
        """延迟初始化 LLM"""
        if not self._initialized:
            from backend.app.core.config import settings
            self.llm = ChatOpenAI(
                model=self.model,
                api_key=settings.API_KEY,
                base_url=settings.BASE_URL,
                temperature=self.temperature,
            )
            self._initialized = True

    async def generate_hitl_message(
        self,
        context: Dict,
        chat_history: List[Dict] = None,
        user_message: str = None
    ) -> Dict:
        """
        生成 HITL 对话消息

        Args:
            context: 当前上下文（check_type, error_message, affected_count 等）
            chat_history: 对话历史
            user_message: 用户当前输入（可选）

        Returns:
            生成的消息字典 {message, suggested_actions, issue_details}
        """
        self._init_llm()

        # 构建系统提示
        system_prompt = HITL_SYSTEM_PROMPT_TEMPLATE.format(
            check_type=context.get("check_type", "unknown"),
            error_message=context.get("error_message", ""),
            affected_count=context.get("affected_count", 0),
            total_count=context.get("total_count", 0),
            available_actions=", ".join(context.get("available_actions", [])),
        )

        messages = [SystemMessage(content=system_prompt)]

        # 添加历史对话
        if chat_history:
            for msg in chat_history:
                if msg["role"] == "assistant":
                    messages.append(AIMessage(content=msg["content"]))
                else:
                    messages.append(HumanMessage(content=msg["content"]))

        # 添加当前用户输入
        if user_message:
            messages.append(HumanMessage(content=user_message))

        # 调用 LLM
        try:
            response = await self.llm.ainvoke(messages)
            response_text = response.content
        except Exception as e:
            logger.error(f"[HITL LLM] 调用失败: {e}")
            # Fallback：生成基本消息
            response_text = self._fallback_hitl_message(context)

        # 解析建议动作
        suggested_actions = self._extract_suggested_actions(response_text, context.get("available_actions", []))

        # 构建问题详情
        issue_details = {
            "summary": self._generate_issue_summary(context),
            "details": context.get("error_message", ""),
            "affected_count": context.get("affected_count", 0),
            "affected_records": context.get("data_preview", [])[:5],
        }

        return {
            "message": response_text,
            "suggested_actions": suggested_actions,
            "issue_details": issue_details,
        }

    async def parse_user_intent(
        self,
        user_message: str,
        context: Dict,
        available_actions: List[str] = None
    ) -> Dict:
        """
        解析用户意图

        Args:
            user_message: 用户输入文本
            context: 当前上下文
            available_actions: 可选动作列表

        Returns:
            解析结果 {action, data, confidence, reasoning}
        """
        self._init_llm()

        available_actions = available_actions or context.get("available_actions", ["continue", "modify", "terminate"])

        # 简单规则优先：直接匹配关键词（不依赖 LLM）
        msg_lower = user_message.strip().lower()

        # 快速匹配规则
        continue_keywords = ["好的", "同意", "可以", "继续", "没问题", "导出", "ok", "yes", "sure", "好", "行", "确认", "接受", "accept", "继续处理"]
        terminate_keywords = ["算了", "取消", "停止", "退出", "不做了", "no", "stop", "quit", "cancel", "终止", "terminate"]
        edit_keywords = ["编辑", "修改", "改一下", "edit", "modify", "调整"]
        retry_keywords = ["重新", "重试", "再来", "retry", "再试", "regenerate", "重新生成"]
        use_default_keywords = ["使用默认", "默认", "default", "use_default"]
        view_keywords = ["查看", "看看", "展示", "失败", "view", "failed", "查看失败"]
        ask_keywords = ["为什么", "怎么", "什么", "多少", "如何", "who", "what", "how", "why"]
        # 无关输入特征（数学计算、纯数字、闲聊等）
        irrelevant_patterns = ["+", "-", "*", "/", "=", "乘", "除", "加", "减", "等于", "是多少"]

        # 按优先级匹配关键词
        if any(kw in msg_lower for kw in terminate_keywords):
            return {"action": "terminate", "data": {}, "confidence": 0.9, "reasoning": "关键词匹配：终止任务"}
        if any(kw in msg_lower for kw in edit_keywords):
            # 根据available_actions选择合适的编辑动作
            if "edit" in available_actions:
                return {"action": "edit", "data": {}, "confidence": 0.9, "reasoning": "关键词匹配：编辑修改"}
            elif "modify" in available_actions:
                return {"action": "modify", "data": {}, "confidence": 0.9, "reasoning": "关键词匹配：修改配置"}
            else:
                return {"action": "continue", "data": {}, "confidence": 0.8, "reasoning": "关键词匹配：编辑意图，但无编辑选项，默认继续"}
        if any(kw in msg_lower for kw in use_default_keywords):
            if "use_default" in available_actions:
                return {"action": "use_default", "data": {}, "confidence": 0.9, "reasoning": "关键词匹配：使用默认"}
            else:
                return {"action": "continue", "data": {}, "confidence": 0.8, "reasoning": "关键词匹配：默认意图，默认继续"}
        if any(kw in msg_lower for kw in retry_keywords):
            return {"action": "retry" if "retry" in available_actions else "regenerate" if "regenerate" in available_actions else "continue", "data": {}, "confidence": 0.8, "reasoning": "关键词匹配：重试"}
        if any(kw in msg_lower for kw in continue_keywords):
            return {"action": "continue" if "continue" in available_actions else "accept" if "accept" in available_actions else "continue", "data": {}, "confidence": 0.9, "reasoning": "关键词匹配：确认继续"}
        if any(kw in msg_lower for kw in view_keywords):
            return {"action": "view_failed" if "view_failed" in available_actions else "continue", "data": {}, "confidence": 0.8, "reasoning": "关键词匹配：查看"}
        if any(kw in msg_lower for kw in ask_keywords):
            return {"action": "ask_more", "data": {}, "confidence": 0.7, "reasoning": "关键词匹配：用户提问"}

        # 检测无关输入（数学计算、纯数字、闲聊等）- 返回 special action 让上层引导用户
        if any(pattern in user_message for pattern in irrelevant_patterns):
            return {"action": "invalid_input", "data": {"original_input": user_message}, "confidence": 0.95, "reasoning": "检测到无关输入（数学计算/闲聊），需要引导用户输入正确选项"}

        # 检测纯数字或极短无意义输入 - 同样引导用户
        stripped = user_message.strip()
        if stripped.isdigit() or (len(stripped) < 3 and not any(c.isalpha() for c in stripped)):
            return {"action": "invalid_input", "data": {"original_input": user_message}, "confidence": 0.95, "reasoning": "检测到纯数字/极短无意义输入，需要引导用户输入正确选项"}

        # 输入太短且不是明确指令关键词 - 引导用户
        if len(stripped) < 5 and not any(kw in msg_lower for kw in continue_keywords + terminate_keywords):
            return {"action": "invalid_input", "data": {"original_input": user_message}, "confidence": 0.8, "reasoning": "输入太短且不是明确指令，需要引导用户输入正确选项"}

        # 规则无法匹配，尝试 LLM 解析
        parse_prompt = INTENT_PARSE_PROMPT_TEMPLATE.format(
            user_message=user_message,
            available_actions=", ".join(available_actions),
            check_type=context.get("check_type", "unknown"),
        )

        messages = [
            SystemMessage(content=parse_prompt),
            HumanMessage(content=user_message),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            response_text = response.content

            # 解析 JSON
            try:
                # 尝试直接解析
                result = json.loads(response_text)
            except json.JSONDecodeError:
                # 尝试提取 JSON 块
                json_match = response_text
                if "```json" in response_text:
                    json_match = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    json_match = response_text.split("```")[1].split("```")[0]

                try:
                    result = json.loads(json_match.strip())
                except:
                    raise ValueError("LLM 返回格式无法解析")

            # 验证动作是否在可选范围内
            if result.get("action") not in available_actions + ["ask_more", "invalid_input"]:
                # 如果动作不在可选范围内，返回 invalid_input 引导用户
                result["action"] = "invalid_input"
                result["data"] = {"original_input": user_message}
                result["reasoning"] = f"无法识别 '{user_message[:30]}' 为有效动作，请选择正确的操作按钮或输入明确的指令"
                result["confidence"] = 0.8

            return result

        except Exception as e:
            logger.warning(f"[意图解析] LLM 调用失败，使用规则 fallback: {e}")
            # LLM 失败时的 fallback：返回 invalid_input 引导用户
            return {
                "action": "invalid_input",
                "data": {"original_input": user_message},
                "confidence": 0.5,
                "reasoning": f"无法解析输入 '{user_message[:30]}'，请选择正确的操作按钮或输入明确的指令（如：确认、接受、编辑、终止等）",
            }

    async def answer_data_question(
        self,
        question: str,
        df_data: Dict,
        context: Dict
    ) -> str:
        """
        回答用户关于数据的问题

        Args:
            question: 用户问题
            df_data: 数据摘要信息
            context: 当前上下文

        Returns:
            回答文本
        """
        self._init_llm()

        answer_prompt = f"""用户提问："{question}"

当前数据概况：
- 总记录数：{df_data.get("total_count", 0)}
- 字段分布：{json.dumps(df_data.get("field_stats", {}), ensure_ascii=False)}
- 当前问题：{context.get("check_type", "")} - {context.get("error_message", "")}
- 受影响记录数：{context.get("affected_count", 0)}

请回答用户的问题，如果需要可以提供：
- 受影响记录的具体示例
- 数据统计信息
- 建议的处理方式

用自然语言回答，不要使用 JSON 格式。
"""

        messages = [
            SystemMessage(content="你是数据分析助手，帮助用户了解数据情况。"),
            HumanMessage(content=answer_prompt),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.warning(f"[数据问答] LLM 调用失败: {e}")
            return f"抱歉，暂时无法回答这个问题。当前数据概况：总记录数 {df_data.get('total_count', 0)} 条。"

    async def force_decision_prompt(self, context: Dict, chat_history: List[Dict]) -> str:
        """
        强制引导用户做出决定（当对话轮次过多时）

        Args:
            context: 当前上下文
            chat_history: 对话历史

        Returns:
            强制决策提示
        """
        self._init_llm()

        available_actions = context.get("available_actions", ["continue", "modify", "terminate"])

        prompt = f"""对话已经进行了较长时间，需要引导用户做出最终决定。

当前情况：
- 检查类型：{context.get("check_type", "unknown")}
- 问题描述：{context.get("error_message", "")}

请生成一个简短的回复，直接询问用户是否：
1. {available_actions[0] if available_actions else "继续处理"}
2. {available_actions[1] if len(available_actions) > 1 else "修改配置"}
3. {available_actions[2] if len(available_actions) > 2 else "终止任务"}

回复要简洁直接，不要超过 100 字。
"""

        messages = [
            SystemMessage(content="你是引导用户决策的助手，需要简洁直接。"),
            HumanMessage(content=prompt),
        ]

        try:
            response = await self.llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.warning(f"[强制决策] LLM 调用失败: {e}")
            available_actions = context.get("available_actions", ["continue", "modify", "terminate"])
            return f"请做出决定：1. {available_actions[0]}  2. {available_actions[1] if len(available_actions)>1 else 'modify'}  3. {available_actions[2] if len(available_actions)>2 else 'terminate'}"

    def _fallback_hitl_message(self, context: Dict) -> str:
        """LLM 失败时的 fallback 消息"""
        check_type = context.get("check_type", "unknown")
        affected = context.get("affected_count", 0)
        total = context.get("total_count", 0)
        actions = context.get("available_actions", [])

        messages = {
            "field": f"有 {affected}/{total} 条记录缺少必需字段。请选择操作。",
            "quality": f"有 {affected} 条记录质量不达标。请选择操作。",
            "filter": f"过滤后有 {affected} 条记录。请选择操作。",
            "prompt": "Prompt 需要确认。请选择操作。",
            "eval": f"评估完成，有 {affected} 条失败记录。请选择操作。",
        }
        return messages.get(check_type, f"检查未通过，影响 {affected} 条记录。请选择操作。")

    def _extract_suggested_actions(self, response_text: str, available_actions: List[str]) -> List[Dict]:
        """从回复文本中提取建议动作"""
        suggested = []

        # 尝试识别回复中提到的动作
        action_labels = {
            "continue": "继续处理",
            "modify": "修改配置",
            "terminate": "终止任务",
            "accept": "确认接受",
            "edit": "编辑修改",
            "regenerate": "重新生成",
            "use_default": "使用默认",
            "retry": "重新尝试",
            "view_failed": "查看失败",
        }

        for action in available_actions:
            if action in response_text.lower() or action_labels.get(action, "") in response_text:
                suggested.append({
                    "value": action,
                    "label": action_labels.get(action, action),
                    "type": self._get_action_type(action),
                })

        # 确保至少有一个选项
        if not suggested and available_actions:
            for action in available_actions[:3]:
                suggested.append({
                    "value": action,
                    "label": action_labels.get(action, action),
                    "type": self._get_action_type(action),
                })

        return suggested

    def _get_action_type(self, action: str) -> str:
        """获取动作的按钮类型"""
        type_map = {
            "continue": "success",
            "accept": "success",
            "modify": "warning",
            "edit": "warning",
            "terminate": "danger",
            "retry": "primary",
            "regenerate": "primary",
        }
        return type_map.get(action, "default")

    def _generate_issue_summary(self, context: Dict) -> str:
        """生成问题摘要"""
        check_type = context.get("check_type", "unknown")
        affected_count = context.get("affected_count", 0)
        total_count = context.get("total_count", 0)

        summaries = {
            "field": f"有 {affected_count}/{total_count} 条记录缺少必需字段",
            "quality": f"有 {affected_count} 条记录质量评分低于阈值",
            "filter": f"过滤后剩余 {affected_count} 条记录，低于最小要求",
            "prompt": "Prompt 需要确认",
            "eval": f"评估失败 {affected_count} 条记录",
        }

        return summaries.get(check_type, f"检查未通过，影响 {affected_count} 条记录")


# 全局实例（延迟初始化）
_hitl_llm_instance: Optional[HITLConversationLLM] = None


def get_hitl_llm(model: str = None) -> HITLConversationLLM:
    """获取 HITL LLM 实例（默认从 .env 读取模型名）"""
    global _hitl_llm_instance
    if _hitl_llm_instance is None:
        _hitl_llm_instance = HITLConversationLLM(model=model or settings.MODEL_NAME)
    return _hitl_llm_instance