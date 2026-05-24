"""
智能 HITL 异步节点
基于 LLM 对话的 HITL 交互，支持自然语言输入
"""
import asyncio
import logging
from typing import Dict, List, Optional, Callable, Awaitable, Any
from datetime import datetime

from backend.app.excel_extraction.state import AgentState
from backend.app.excel_extraction.conversation import get_hitl_llm, HITLConversationLLM
from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class WebHITLContext:
    """Web HITL 上下文管理 - 管理每个会话的 HITL 状态"""

    _instances: Dict[str, 'WebHITLContext'] = {}
    _lock = asyncio.Lock()
    HITL_TIMEOUT = 300  # 5分钟超时（用户长时间无响应则自动继续）

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.ws_callback: Optional[Callable[[Dict], Awaitable[None]]] = None
        self._pending_action: Optional[str] = None
        self._pending_data: Optional[Dict] = None
        self._action_event = asyncio.Event()
        self._created_at = datetime.now()
        self._aborted = False

    @classmethod
    async def get(cls, session_id: str) -> 'WebHITLContext':
        """获取或创建会话上下文"""
        async with cls._lock:
            if session_id not in cls._instances:
                cls._instances[session_id] = cls(session_id)
            return cls._instances[session_id]

    @classmethod
    def get_sync(cls, session_id: str) -> Optional['WebHITLContext']:
        """同步获取已存在的会话上下文（不创建新的）"""
        return cls._instances.get(session_id)

    @classmethod
    async def remove(cls, session_id: str):
        """移除会话上下文（先唤醒等待中的工作流，再删除）"""
        async with cls._lock:
            if session_id in cls._instances:
                ctx = cls._instances[session_id]
                ctx.abort("会话已被清理")
                del cls._instances[session_id]

    def abort(self, reason: str = "会话已终止"):
        """中断等待中的 HITL 上下文（由 WebSocket 断开或取消任务触发）"""
        if self._aborted:
            return
        self._aborted = True
        # 设置默认动作为 continue，避免工作流永久阻塞
        if self._pending_action is None:
            self._pending_action = "continue"
            self._pending_data = {"text": f"[系统自动] {reason}", "action": "continue", "data": {}}
        self._action_event.set()
        logger.info(f"[WebHITL] 会话 {self.session_id} 已中断: {reason}")

    def set_ws_callback(self, callback: Callable[[Dict], Awaitable[None]]):
        """设置 WebSocket 回调函数"""
        self.ws_callback = callback

    async def _wait_for_action(self):
        """等待用户动作，支持超时和中断（会话清理或取消时不会永久阻塞）"""
        try:
            done, pending = await asyncio.wait(
                [asyncio.create_task(self._action_event.wait())],
                timeout=self.HITL_TIMEOUT
            )
            for t in pending:
                t.cancel()
            if not done:
                # 超时：自动继续
                logger.warning(f"[WebHITL] 会话 {self.session_id} HITL 等待超时，自动继续")
                self._pending_action = "continue"
                self._pending_data = {"text": "[系统自动] 用户响应超时，自动继续", "action": "continue", "data": {}}
        except asyncio.CancelledError:
            # 被外部取消时，确保 _pending_action 不为 None
            if self._pending_action is None:
                self._pending_action = "continue"
                self._pending_data = {"text": "[系统自动] 任务被取消，自动继续", "action": "continue", "data": {}}

    async def send_message(self, message: Dict):
        """发送消息到 WebSocket"""
        if self.ws_callback and not self._aborted:
            try:
                await self.ws_callback(message)
            except Exception as e:
                logger.error(f"[WebHITL] WebSocket 发送失败: {e}")

    async def request_user_action(
        self,
        message: str,
        options: List[str],
        check_type: str = "unknown",
        details: Dict = None
    ) -> str:
        """
        请求用户动作并等待响应（传统按钮模式）

        Args:
            message: 显示给用户的消息
            options: 可选项列表
            check_type: 检查类型
            details: 详细信息

        Returns:
            用户选择的动作
        """
        await self.send_message({
            "type": "hitl_request",
            "content": {
                "message": message,
                "options": options,
                "check_type": check_type,
                "details": details or {}
            },
            "timestamp": datetime.now().isoformat()
        })

        await self._wait_for_action()
        action = self._pending_action

        self._pending_action = None
        self._pending_data = None
        self._action_event.clear()

        return action

    async def request_llm_chat(
        self,
        llm_response: Dict,
        issue_details: Dict = None
    ) -> Dict:
        """
        发送 LLM 对话消息并等待用户响应（智能对话模式）

        Args:
            llm_response: LLM 生成的回复
            issue_details: 问题详情

        Returns:
            用户输入 {type: "text"|"action", content: "...", data: {...}}
        """
        logger.info(f"[DEBUG request_llm_chat] session_id={self.session_id}, sending llm_chat message")
        await self.send_message({
            "type": "llm_chat",
            "content": {
                "role": "assistant",
                "message": llm_response.get("message", ""),
                "suggested_actions": llm_response.get("suggested_actions", []),
                "issue_details": issue_details or llm_response.get("issue_details", {}),
            },
            "timestamp": datetime.now().isoformat()
        })

        logger.info(f"[DEBUG request_llm_chat] session_id={self.session_id}, waiting for user response (timeout={self.HITL_TIMEOUT}s)")
        await self._wait_for_action()
        logger.info(f"[DEBUG request_llm_chat] session_id={self.session_id}, _action_event unblocked")

        result = {
            "type": "action" if self._pending_action else "text",
            "action": self._pending_action,
            "text": self._pending_data.get("text", "") if self._pending_data else "",
            "data": self._pending_data or {},
        }

        # 处理 "text_input" 特殊情况 - 表示用户输入了文本而非点击按钮
        if result.get("action") == "text_input":
            result["type"] = "text"
            result["action"] = None
            logger.info(f"[DEBUG request_llm_chat] converted text_input to text type")

        logger.info(f"[DEBUG request_llm_chat] session_id={self.session_id}, returning: type={result['type']}, action={result['action']}")

        self._pending_action = None
        self._pending_data = None
        self._action_event.clear()

        return result

    def set_user_action(self, action: str, data: Dict = None):
        """
        设置用户动作（由 WebSocket 调用）

        Args:
            action: 用户选择的动作
            data: 额外数据（如文本输入、修改内容等）
        """
        logger.info(f"[DEBUG set_user_action] session_id={self.session_id}, action={action}, data_keys={list(data.keys()) if data else None}")
        self._pending_action = action
        self._pending_data = data
        self._action_event.set()
        logger.info(f"[DEBUG set_user_action] _action_event.set() called for session_id={self.session_id}")

    async def send_progress(self, step: str, progress: int, message: str, details: Dict = None):
        """发送进度更新"""
        await self.send_message({
            "type": "progress",
            "content": {
                "step": step,
                "progress": progress,
                "message": message,
                "details": details or {}
            },
            "timestamp": datetime.now().isoformat()
        })

    async def send_log(self, level: str, node: str, message: str):
        """发送日志消息"""
        await self.send_message({
            "type": "log",
            "content": {
                "level": level,
                "node": node,
                "message": message
            },
            "timestamp": datetime.now().isoformat()
        })

    async def send_completed(self, results: Dict):
        """发送完成消息"""
        await self.send_message({
            "type": "completed",
            "content": results,
            "timestamp": datetime.now().isoformat()
        })

    async def send_failed(self, error: str):
        """发送失败消息"""
        await self.send_message({
            "type": "failed",
            "content": {"error": error},
            "timestamp": datetime.now().isoformat()
        })


def build_hitl_context(state: Dict) -> Dict:
    """构建 HITL 对话上下文"""
    pending = state.get("pending_check", "unknown")
    check_result = state.get("check_results", {}).get(pending, {})
    config = state.get("config", {})
    df = state.get("df")

    context = {
        "check_type": pending,
        "error_message": state.get("error_message", ""),
        "affected_count": check_result.get("failed_count", 0) or check_result.get("affected_count", 0),
        "total_count": len(df) if df is not None else 0,
        "available_actions": get_available_actions(pending),
        "data_preview": None,
        "config": config,
    }

    # 添加数据预览
    if df is not None and check_result.get("failed_indices"):
        try:
            import pandas as pd
            failed_indices = check_result["failed_indices"][:10]
            preview_rows = df.iloc[failed_indices].head(10).to_dict(orient="records")
            context["data_preview"] = preview_rows
        except:
            pass

    return context


def get_available_actions(check_type: str) -> List[str]:
    """根据检查类型获取可选动作"""
    actions_map = {
        "field": ["continue", "modify", "terminate", "ask_more"],
        "quality": ["continue", "modify", "terminate", "ask_more"],
        "filter": ["continue", "modify", "terminate", "ask_more"],
        "prompt": ["accept", "edit", "regenerate", "use_default", "terminate", "ask_more"],
        "eval": ["continue", "retry", "view_failed", "terminate", "ask_more"],
    }
    return actions_map.get(check_type, ["continue", "terminate"])


# ============================================================================
# 智能对话 HITL 节点
# ============================================================================

async def llm_hitl_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """
    LLM 智能对话 HITL 节点（通用检查确认）
    """
    pending = state.get("pending_check", "unknown")
    enable_smart_hitl = state.get("config", {}).get("enable_smart_hitl", True)
    hitl_llm_model = state.get("config", {}).get("hitl_llm_model", settings.MODEL_NAME)

    await hitl_ctx.send_log("INFO", "llm_hitl", f"HITL 对话开始: {pending}")

    # 构建上下文
    context = build_hitl_context(state)

    if enable_smart_hitl:
        # 智能对话模式
        hitl_llm = get_hitl_llm(hitl_llm_model)

        # 生成首次回复
        chat_history = state.get("chat_history", [])
        llm_response = await hitl_llm.generate_hitl_message(
            context=context,
            chat_history=chat_history,
        )

        # 发送并等待用户响应
        user_input = await hitl_ctx.request_llm_chat(llm_response, context)

        # 更新对话历史
        new_history = chat_history + [
            {"role": "assistant", "content": llm_response.get("message", "")},
        ]
        if user_input.get("text"):
            new_history.append({"role": "user", "content": user_input.get("text", "")})

        # 解析用户意图
        if user_input.get("type") == "text" and user_input.get("text"):
            intent = await hitl_llm.parse_user_intent(
                user_message=user_input.get("text", ""),
                context=context,
                available_actions=context.get("available_actions", []),
            )
            action = intent.get("action", "continue")
            action_data = intent.get("data", {})
            confidence = intent.get("confidence", 0.5)

            # 如果检测到无效输入，发送引导消息并重新等待用户输入
            if action == "invalid_input":
                original_input = action_data.get("original_input", user_input.get("text", ""))
                guidance_message = f"您的输入 '{original_input[:30]}' 与当前任务无关。\n\n请选择正确的操作：\n- 输入 **确认** 或 **接受** 以继续处理\n- 输入 **编辑** 或 **修改** 以调整配置\n- 输入 **终止** 或 **取消** 以停止任务\n- 或直接点击下方按钮选择操作"

                await hitl_ctx.send_message({
                    "type": "llm_chat",
                    "content": {
                        "role": "assistant",
                        "message": guidance_message,
                        "suggested_actions": llm_response.get("suggested_actions", [
                            {"value": "continue", "label": "继续处理", "type": "success"},
                            {"value": "modify", "label": "修改配置", "type": "warning"},
                            {"value": "terminate", "label": "终止任务", "type": "danger"},
                        ]),
                    }
                })

                # 重新等待用户输入
                user_input = await hitl_ctx.request_llm_chat({"message": ""}, context)

                # 再次解析
                if user_input.get("type") == "text":
                    intent = await hitl_llm.parse_user_intent(
                        user_message=user_input.get("text", ""),
                        context=context,
                        available_actions=context.get("available_actions", []),
                    )
                    action = intent.get("action", "continue")
                    action_data = intent.get("data", {})
                else:
                    action = user_input.get("action", "continue")
                    action_data = user_input.get("data", {})

                # 更新对话历史
                new_history.append({"role": "user", "content": user_input.get("text", "")})
                new_history.append({"role": "assistant", "content": "收到您的选择，继续处理..."})
        else:
            action = user_input.get("action", "continue")
            action_data = user_input.get("data", {})

        hitl_turns = state.get("hitl_turns", 0) + 1
        max_turns = state.get("max_hitl_turns", 10)

        # 如果对话轮次过多，强制引导决策
        if hitl_turns >= max_turns - 2:
            force_message = await hitl_llm.force_decision_prompt(context, new_history)
            await hitl_ctx.send_message({
                "type": "llm_chat",
                "content": {"role": "assistant", "message": force_message}
            })

        return {
            "current_step": "llm_hitl",
            "current_node": "llm_hitl",
            "user_action": action,
            "action_data": action_data,
            "chat_history": new_history,
            "hitl_turns": hitl_turns,
        }

    else:
        # 传统按钮模式
        check_messages = {
            "field": "字段检查未通过",
            "quality": "数据质量检查未通过",
            "filter": "数据过滤检查未通过",
        }

        message = check_messages.get(pending, "检查未通过")
        if state.get("error_message"):
            message += f"\n详情: {state.get('error_message')}"

        options = get_available_actions(pending)
        action = await hitl_ctx.request_user_action(
            message=message,
            options=options,
            check_type=pending,
            details=context
        )

        return {
            "current_step": "llm_hitl",
            "current_node": "llm_hitl",
            "user_action": action,
            "chat_history": state.get("chat_history", []),
        }


async def llm_prompt_check_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """
    LLM 智能 Prompt 确认节点
    """
    prompt_text = state.get("generated_prompt", "") or ""
    enable_smart_hitl = state.get("config", {}).get("enable_smart_hitl", True)
    hitl_llm_model = state.get("config", {}).get("hitl_llm_model", settings.MODEL_NAME)

    await hitl_ctx.send_log("INFO", "llm_prompt_check", "Prompt 确认")

    context = {
        "check_type": "prompt",
        "error_message": "",
        "affected_count": 0,
        "total_count": 0,
        "available_actions": get_available_actions("prompt"),
        "data_preview": None,
        "has_prompt": bool(prompt_text),
    }

    if enable_smart_hitl:
        hitl_llm = get_hitl_llm(hitl_llm_model)

        if not prompt_text:
            # Prompt 未生成
            message = "Prompt 未生成（策略文档不存在或解析失败）。\n\n您可以选择：\n1. 使用默认 Prompt\n2. 手动输入 Prompt\n3. 重新提供策略文档\n4. 终止任务"
        else:
            message = f"我已根据策略文档生成了评估 Prompt。\n\n**提取字段包括：**\n- related（相关性判断）\n- institution（机构）\n- summary（摘要）\n- 以及其他领域特定字段\n\n完整 Prompt 内容较长，您可以在下方查看。\n\n请确认是否使用此 Prompt，或选择其他操作。"

        llm_response = {
            "message": message,
            "suggested_actions": [
                {"value": "accept", "label": "确认使用", "type": "success"},
                {"value": "edit", "label": "编辑修改", "type": "warning"},
                {"value": "use_default", "label": "使用默认", "type": "default"},
                {"value": "terminate", "label": "终止任务", "type": "danger"},
            ] if prompt_text else [
                {"value": "use_default", "label": "使用默认", "type": "primary"},
                {"value": "manual", "label": "手动输入", "type": "warning"},
                {"value": "terminate", "label": "终止任务", "type": "danger"},
            ],
            "issue_details": {
                "summary": "Prompt 确认",
                "details": "请确认生成的评估 Prompt",
                "prompt_preview": prompt_text[:500] + "..." if len(prompt_text) > 500 else prompt_text,
                "prompt_full": prompt_text,
            }
        }

        user_input = await hitl_ctx.request_llm_chat(llm_response, None)

        if user_input.get("type") == "text":
            hitl_llm = get_hitl_llm(hitl_llm_model)
            intent = await hitl_llm.parse_user_intent(
                user_message=user_input.get("text", ""),
                context=context,
                available_actions=["accept", "edit", "regenerate", "use_default", "terminate"],
            )
            action = intent.get("action", "accept")
            confidence = intent.get("confidence", 0.5)
            reasoning = intent.get("reasoning", "")

            # 如果检测到无效输入，发送引导消息并重新等待用户输入
            if action == "invalid_input":
                original_input = intent.get("data", {}).get("original_input", user_input.get("text", ""))
                guidance_message = f"您的输入 '{original_input[:30]}' 与当前任务无关。\n\n请选择正确的操作：\n- 输入 **确认** 或 **接受** 以使用当前 Prompt\n- 输入 **编辑** 或 **修改** 以调整 Prompt 内容\n- 输入 **使用默认** 以切换到默认 Prompt\n- 输入 **终止** 以停止任务\n- 或直接点击下方按钮选择操作"

                await hitl_ctx.send_message({
                    "type": "llm_chat",
                    "content": {
                        "role": "assistant",
                        "message": guidance_message,
                        "suggested_actions": llm_response.get("suggested_actions", []),
                        "issue_details": llm_response.get("issue_details", {}),
                    }
                })

                # 重新等待用户输入
                user_input = await hitl_ctx.request_llm_chat({"message": ""}, None)

                # 再次解析
                if user_input.get("type") == "text":
                    intent = await hitl_llm.parse_user_intent(
                        user_message=user_input.get("text", ""),
                        context=context,
                        available_actions=["accept", "edit", "regenerate", "use_default", "terminate"],
                    )
                    action = intent.get("action", "accept")
                else:
                    action = user_input.get("action", "accept")

                await hitl_ctx.send_log("INFO", "llm_prompt_check", f"用户重新选择: {action}")
        else:
            action = user_input.get("action", "accept")

        return {
            "current_step": "llm_prompt_check",
            "current_node": "llm_prompt_check",
            "user_action": action,
        }

    else:
        # 传统模式
        if not prompt_text:
            message = "Prompt 未生成，请选择操作"
            options = ["use_default", "manual", "terminate"]
        else:
            message = f"Prompt 已生成，请确认:\n\n{prompt_text[:300]}..."
            options = ["accept", "edit", "regenerate", "use_default", "terminate"]

        action = await hitl_ctx.request_user_action(
            message=message,
            options=options,
            check_type="prompt",
            details={"prompt_full": prompt_text}
        )

        return {
            "current_step": "llm_prompt_check",
            "current_node": "llm_prompt_check",
            "user_action": action,
        }


async def llm_eval_approval_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """
    LLM 智能评估结果确认节点
    """
    eval_result = state.get("check_results", {}).get("eval", {})
    failed_dois = state.get("failed_dois", [])
    retry_count = state.get("retry_count", 0)
    max_retry = state.get("config", {}).get("max_retry_count", 3)
    enable_smart_hitl = state.get("config", {}).get("enable_smart_hitl", True)
    hitl_llm_model = state.get("config", {}).get("hitl_llm_model", settings.MODEL_NAME)

    await hitl_ctx.send_log("INFO", "llm_eval_approval", "评估结果确认")

    success_rate = eval_result.get("success_rate", 0)
    parse_rate = eval_result.get("parse_rate", 0)
    failed_count = len(failed_dois)

    context = {
        "check_type": "eval",
        "error_message": f"成功率: {success_rate:.0%}, 解析率: {parse_rate:.0%}",
        "affected_count": failed_count,
        "total_count": eval_result.get("total_count", 0),
        "available_actions": get_available_actions("eval"),
        "data_preview": None,
        "retry_count": retry_count,
        "max_retry": max_retry,
    }

    if enable_smart_hitl:
        hitl_llm = get_hitl_llm(hitl_llm_model)

        # 构建智能消息
        if success_rate >= 0.9:
            message = f"评估进展良好！\n\n**结果统计：**\n- API 调用成功率：{success_rate:.0%}\n- 解析成功率：{parse_rate:.0%}\n- 失败记录：{failed_count} 条\n\n可以直接导出结果，或查看失败记录详情。"
        else:
            message = f"评估过程中遇到了一些问题。\n\n**结果统计：**\n- API 调用成功率：{success_rate:.0%}\n- 解析成功率：{parse_rate:.0%}\n- 失败记录：{failed_count} 条\n- 已重试次数：{retry_count}/{max_retry}\n\n建议您选择继续导出当前结果，或尝试重试失败的记录。"

        suggested_actions = [
            {"value": "continue", "label": "继续导出", "type": "success"},
        ]
        if retry_count < max_retry:
            suggested_actions.append({"value": "retry", "label": "重试失败", "type": "primary"})
        if failed_count > 0:
            suggested_actions.append({"value": "view_failed", "label": "查看失败", "type": "warning"})
        suggested_actions.append({"value": "terminate", "label": "终止任务", "type": "danger"})

        llm_response = {
            "message": message,
            "suggested_actions": suggested_actions,
            "issue_details": {
                "summary": f"评估成功率 {success_rate:.0%}",
                "details": f"失败 {failed_count} 条记录",
                "success_rate": success_rate,
                "parse_rate": parse_rate,
            }
        }

        user_input = await hitl_ctx.request_llm_chat(llm_response, context)

        if user_input.get("type") == "text":
            intent = await hitl_llm.parse_user_intent(
                user_message=user_input.get("text", ""),
                context=context,
                available_actions=["continue", "retry", "view_failed", "terminate"],
            )
            action = intent.get("action", "continue")

            # 如果检测到无效输入，发送引导消息并重新等待用户输入
            if action == "invalid_input":
                original_input = intent.get("data", {}).get("original_input", user_input.get("text", ""))
                guidance_message = f"您的输入 '{original_input[:30]}' 与当前任务无关。\n\n请选择正确的操作：\n- 输入 **继续** 或 **导出** 以导出当前结果\n- 输入 **重试** 以重新处理失败记录\n- 输入 **查看** 以查看失败列表\n- 输入 **终止** 以停止任务\n- 或直接点击下方按钮选择操作"

                await hitl_ctx.send_message({
                    "type": "llm_chat",
                    "content": {
                        "role": "assistant",
                        "message": guidance_message,
                        "suggested_actions": suggested_actions,
                        "issue_details": llm_response.get("issue_details", {}),
                    }
                })

                # 重新等待用户输入
                user_input = await hitl_ctx.request_llm_chat({"message": ""}, context)

                # 再次解析
                if user_input.get("type") == "text":
                    intent = await hitl_llm.parse_user_intent(
                        user_message=user_input.get("text", ""),
                        context=context,
                        available_actions=["continue", "retry", "view_failed", "terminate"],
                    )
                    action = intent.get("action", "continue")
                else:
                    action = user_input.get("action", "continue")

                await hitl_ctx.send_log("INFO", "llm_eval_approval", f"用户重新选择: {action}")
        else:
            action = user_input.get("action", "continue")

        return {
            "current_step": "llm_eval_approval",
            "current_node": "llm_eval_approval",
            "user_action": action,
        }

    else:
        message = f"评估结果质量检查\n成功率: {success_rate:.0%}\n解析率: {parse_rate:.0%}\n失败: {failed_count} 条\n重试: {retry_count}/{max_retry}"
        options = ["continue", "retry", "view_failed", "terminate"]
        if retry_count >= max_retry:
            options.remove("retry")

        action = await hitl_ctx.request_user_action(
            message=message,
            options=options,
            check_type="eval",
            details={"success_rate": success_rate, "failed_count": failed_count}
        )

        return {
            "current_step": "llm_eval_approval",
            "current_node": "llm_eval_approval",
            "user_action": action,
        }


async def data_lookup_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """
    数据查询节点（回答用户关于数据的问题）
    """
    user_question = state.get("action_data", {}).get("question", "") or state.get("action_data", {}).get("text", "")
    df = state.get("df")
    pending_check = state.get("pending_check", "")
    hitl_llm_model = state.get("config", {}).get("hitl_llm_model", settings.MODEL_NAME)

    await hitl_ctx.send_log("INFO", "data_lookup", f"查询用户问题: {user_question[:50]}")

    hitl_llm = get_hitl_llm(hitl_llm_model)

    # 构建数据摘要
    df_data = {
        "total_count": len(df) if df is not None else 0,
        "field_stats": {},
    }

    if df is not None:
        # 字段统计
        for col in df.columns[:10]:
            missing = df[col].isna().sum()
            df_data["field_stats"][col] = {
                "total": len(df),
                "missing": int(missing),
                "missing_rate": f"{missing / len(df):.0%}",
            }

    context = build_hitl_context(state)

    # 回答用户问题
    answer = await hitl_llm.answer_data_question(user_question, df_data, context)

    # 发送回答
    await hitl_ctx.send_message({
        "type": "llm_chat",
        "content": {
            "role": "assistant",
            "message": answer,
            "suggested_actions": [
                {"value": "continue", "label": "继续处理", "type": "success"},
                {"value": "modify", "label": "修改配置", "type": "warning"},
                {"value": "ask_more", "label": "继续提问", "type": "default"},
            ],
        }
    })

    # 等待用户下一步操作
    user_input = await hitl_ctx.request_llm_chat({"message": ""}, context)

    # 解析意图
    if user_input.get("type") == "text":
        intent = await hitl_llm.parse_user_intent(
            user_message=user_input.get("text", ""),
            context=context,
            available_actions=["continue", "modify", "terminate", "ask_more"],
        )
        action = intent.get("action", "ask_more")
        action_data = intent.get("data", {})

        # 如果检测到无效输入，发送引导消息并重新等待用户输入
        if action == "invalid_input":
            original_input = action_data.get("original_input", user_input.get("text", ""))
            guidance_message = f"您的输入 '{original_input[:30]}' 与当前任务无关。\n\n请选择正确的操作：\n- 输入 **继续** 以继续处理任务\n- 输入 **修改** 以调整配置\n- 输入 **提问** 以继续询问数据相关问题\n- 输入 **终止** 以停止任务\n- 或直接点击下方按钮选择操作"

            await hitl_ctx.send_message({
                "type": "llm_chat",
                "content": {
                    "role": "assistant",
                    "message": guidance_message,
                    "suggested_actions": [
                        {"value": "continue", "label": "继续处理", "type": "success"},
                        {"value": "modify", "label": "修改配置", "type": "warning"},
                        {"value": "ask_more", "label": "继续提问", "type": "default"},
                    ],
                }
            })

            # 重新等待用户输入
            user_input = await hitl_ctx.request_llm_chat({"message": ""}, context)

            # 再次解析
            if user_input.get("type") == "text":
                intent = await hitl_llm.parse_user_intent(
                    user_message=user_input.get("text", ""),
                    context=context,
                    available_actions=["continue", "modify", "terminate", "ask_more"],
                )
                action = intent.get("action", "ask_more")
                action_data = intent.get("data", {})
            else:
                action = user_input.get("action", "continue")
                action_data = {}
    else:
        action = user_input.get("action", "continue")
        action_data = {}

    return {
        "current_step": "data_lookup",
        "current_node": "data_lookup",
        "user_action": action,
        "action_data": action_data,
        "pending_check": pending_check,  # 保持当前检查类型
    }


async def view_failed_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """查看失败列表节点"""
    failed_dois = state.get("failed_dois", [])
    input_dict = state.get("input_dict", {})
    results_dict = state.get("results_dict", {})

    await hitl_ctx.send_log("INFO", "view_failed", f"查看失败 DOI: {len(failed_dois)} 条")

    # 构建失败列表详情
    failed_list = []
    for doi in failed_dois[:30]:
        data = input_dict.get(doi, {})
        title = data.get("title", "N/A")[:50]
        error = "评估失败"
        if doi in results_dict:
            error = results_dict.get(doi, {}).get("error", "Unknown")
        failed_list.append({
            "doi": doi,
            "title": title,
            "error": str(error)[:100],
        })

    # 发送失败列表
    await hitl_ctx.send_message({
        "type": "failed_list",
        "content": {
            "total": len(failed_dois),
            "failed_list": failed_list,
            "showing": len(failed_list),
        }
    })

    # 等待用户确认返回
    await hitl_ctx.send_message({
        "type": "llm_chat",
        "content": {
            "role": "assistant",
            "message": f"共有 **{len(failed_dois)}** 条记录评估失败。上面显示了前 {len(failed_list)} 条。\n\n请选择下一步操作。",
            "suggested_actions": [
                {"value": "retry", "label": "重试这些记录", "type": "primary"},
                {"value": "continue", "label": "忽略并继续", "type": "success"},
                {"value": "back", "label": "返回上一步", "type": "default"},
            ],
        }
    })

    user_input = await hitl_ctx.request_llm_chat({"message": ""}, {})

    action = user_input.get("action", "back")

    return {
        "current_step": "view_failed",
        "current_node": "view_failed",
        "user_action": action if action != "back" else "eval_approval",
    }


# ============================================================================
# edit_prompt_node - 编辑 Prompt 节点
# ============================================================================

async def edit_prompt_node(state: Dict, hitl_ctx: WebHITLContext) -> Dict:
    """
    编辑 Prompt 节点 - 请求用户输入修改后的 Prompt
    """
    prompt_text = state.get("generated_prompt", "") or ""
    hitl_llm_model = state.get("config", {}).get("hitl_llm_model", settings.MODEL_NAME)

    await hitl_ctx.send_log("INFO", "edit_prompt", "开始执行")

    # 发送请求编辑的消息
    llm_response = {
        "message": "请编辑修改 Prompt 后提交。\n\n您可以在下方输入框中修改 Prompt 内容，或直接发送新的 Prompt。",
        "suggested_actions": [
            {"value": "submit", "label": "提交修改", "type": "success"},
            {"value": "cancel_edit", "label": "取消编辑", "type": "warning"},
            {"value": "terminate", "label": "终止任务", "type": "danger"},
        ],
        "issue_details": {
            "summary": "编辑 Prompt",
            "details": "请在下方输入框编辑 Prompt 内容",
            "prompt_full": prompt_text,
            "prompt_preview": prompt_text[:500] + "..." if len(prompt_text) > 500 else prompt_text,
        }
    }

    context = {
        "check_type": "prompt_edit",
        "error_message": "",
        "affected_count": 0,
        "total_count": 0,
        "available_actions": ["submit", "cancel_edit", "terminate"],
        "data_preview": None,
        "has_prompt": bool(prompt_text),
    }

    user_input = await hitl_ctx.request_llm_chat(llm_response, None)
    await hitl_ctx.send_log("INFO", "edit_prompt", f"[DEBUG] user_input received: type={user_input.get('type')}, action={user_input.get('action')}, text_len={len(user_input.get('text', ''))}")

    new_prompt = None
    action = "accept"

    if user_input.get("type") == "text":
        # 用户输入了新的 Prompt
        new_prompt = user_input.get("text", "")
        action = "submit"
        await hitl_ctx.send_log("INFO", "edit_prompt", f"[DEBUG] text input detected, new_prompt length={len(new_prompt)}, first 50 chars: {new_prompt[:50]}")
    elif user_input.get("action"):
        action = user_input.get("action")
        if action == "cancel_edit":
            action = "accept"  # 取消编辑，使用原 Prompt
        await hitl_ctx.send_log("INFO", "edit_prompt", f"[DEBUG] action input: {action}")

    # 如果用户提供了新 Prompt，保存它
    if new_prompt and new_prompt.strip():
        import os
        save_path = state.get("prompt_saved_path", "")
        await hitl_ctx.send_log("INFO", "edit_prompt", f"[DEBUG] saving prompt to: {save_path}")
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(new_prompt)

        await hitl_ctx.send_log("INFO", "edit_prompt", "Prompt 已更新")
        result = {
            "current_step": "edit_prompt",
            "current_node": "edit_prompt",
            "generated_prompt": new_prompt,
            "user_action": "accept",
        }
        await hitl_ctx.send_log("INFO", "edit_prompt", f"[DEBUG] returning with user_action=accept, generated_prompt length={len(new_prompt)}")
        return result

    await hitl_ctx.send_log("INFO", "edit_prompt", "完成")
    await hitl_ctx.send_log("INFO", "edit_prompt", f"[DEBUG] returning with user_action={action}")
    return {
        "current_step": "edit_prompt",
        "current_node": "edit_prompt",
        "user_action": action,
    }


# ============================================================================
# Web Nodes 字典
# ============================================================================
WEB_NODES = {
    "llm_hitl_node": llm_hitl_node,
    "llm_prompt_check_node": llm_prompt_check_node,
    "llm_eval_approval_node": llm_eval_approval_node,
    "data_lookup_node": data_lookup_node,
    "view_failed_node": view_failed_node,
    "edit_prompt_node": edit_prompt_node,
}