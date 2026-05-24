"""
Web Agent Runner
Excel 批量提取工作流执行器，支持 HITL 智能对话
"""
import asyncio
import threading
import logging
from typing import Dict, Any, Callable, Awaitable, Optional

from langgraph.graph import StateGraph, END, START

from backend.app.excel_extraction.state import AgentState, get_default_state, merge_config
from backend.app.excel_extraction.nodes import NODES
from backend.app.excel_extraction.llm_hitl_nodes import WEB_NODES, WebHITLContext

logger = logging.getLogger(__name__)


# ============================================================================
# 路由函数
# ============================================================================

def route_after_check(state: AgentState, check_type: str, next_step: str) -> str:
    """通用检查路由逻辑"""
    results = state.get("check_results", {})
    if results.get(check_type, {}).get("passed"):
        return next_step
    state["pending_check"] = check_type
    return "llm_hitl"


def field_check_router(state: AgentState) -> str:
    """字段检查路由"""
    return route_after_check(state, "field", "data_quality")


def data_quality_router(state: AgentState) -> str:
    """数据质量检查路由"""
    return route_after_check(state, "quality", "filter")


def filter_router(state: AgentState) -> str:
    """过滤检查路由"""
    results = state.get("check_results", {})
    if results.get("filter", {}).get("passed"):
        config = state.get("config", {})
        if config.get("strategy_docx"):
            return "parse_strategy"
        return "prepare_eval"  # 无策略文档，直接评估
    state["pending_check"] = "filter"
    return "llm_hitl"


def llm_hitl_router(state: AgentState) -> str:
    """HITL 用户选择路由"""
    action = state.get("user_action", "continue")

    if action == "terminate":
        return "terminate"
    if action == "ask_more":
        return "data_lookup"
    if action == "modify":
        return "modify_config"

    pending = state.get("pending_check", "")
    next_map = {
        "field": "data_quality",
        "quality": "filter",
        "filter": "parse_strategy",
    }
    return next_map.get(pending, "integrate")


def data_lookup_router(state: AgentState) -> str:
    """数据查询后路由"""
    action = state.get("user_action", "ask_more")

    if action == "ask_more":
        return "data_lookup"  # 继续对话
    if action == "terminate":
        return "terminate"

    # 用户做出了决定，返回 HITL 节点更新状态
    pending = state.get("pending_check", "")
    return "llm_hitl"


def retry_router(state: AgentState) -> str:
    """修改配置后返回对应检查点"""
    pending = state.get("pending_check", "")
    config = state.get("config", {})

    if config.get("folder_path_modified"):
        config["folder_path_modified"] = False
        return "integrate"

    retry_map = {
        "field": "field_check",
        "quality": "data_quality",
        "filter": "filter",
    }
    return retry_map.get(pending, "integrate")


def prompt_check_router(state: AgentState) -> str:
    """Prompt 确认路由"""
    action = state.get("user_action", "accept")

    if action == "terminate":
        return "terminate"
    elif action == "edit":
        return "edit_prompt"
    elif action == "regenerate":
        return "generate_prompt"
    elif action == "use_default":
        return "use_default"
    elif action == "manual":
        return "manual_prompt"
    else:
        return "prepare_eval"


def result_check_router(state: AgentState) -> str:
    """结果检查路由"""
    eval_result = state.get("check_results", {}).get("eval", {})
    if eval_result.get("passed"):
        return "export_result"
    return "llm_eval_approval"


def llm_eval_approval_router(state: AgentState) -> str:
    """评估结果确认路由"""
    action = state.get("user_action", "continue")

    if action == "terminate":
        return "terminate"
    elif action == "retry":
        retry_count = state.get("retry_count", 0)
        max_retry = state.get("config", {}).get("max_retry_count", 3)
        if retry_count >= max_retry:
            return "export_result"
        return "retry_failed"
    elif action == "view_failed":
        return "view_failed"
    elif action == "eval_approval":
        return "llm_eval_approval"
    else:
        return "export_result"


def view_failed_router(state: AgentState) -> str:
    """查看失败列表后返回"""
    action = state.get("user_action", "back")
    if action == "back":
        return "llm_eval_approval"
    return action


def retry_router_after_eval(state: AgentState) -> str:
    """重试后返回结果检查"""
    return "result_check"


def modify_config_placeholder(state: AgentState) -> Dict:
    """修改配置占位节点（实际逻辑在 HITL 对话中处理）"""
    # 从 action_data 获取修改内容
    action_data = state.get("action_data", {})
    config = state.get("config", {})

    # 应用修改
    if action_data.get("threshold"):
        try:
            config["quality_threshold"] = float(action_data["threshold"])
        except:
            pass
    if action_data.get("required_fields"):
        config["required_fields"] = action_data["required_fields"]

    return {
        "config": config,
        "user_action": "continue",
    }


def edit_prompt_placeholder(state: AgentState) -> Dict:
    """编辑 Prompt 占位节点"""
    action_data = state.get("action_data", {})
    new_prompt = action_data.get("prompt", "")

    if new_prompt.strip():
        # 保存编辑后的 Prompt
        import os
        save_path = state.get("prompt_saved_path", "")
        if save_path:
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(new_prompt)

        return {
            "generated_prompt": new_prompt,
            "user_action": "accept",
        }

    return {"user_action": "accept"}


def manual_prompt_placeholder(state: AgentState) -> Dict:
    """手动输入 Prompt 占位节点"""
    action_data = state.get("action_data", {})
    prompt_text = action_data.get("prompt", "")

    if not prompt_text.strip():
        return {"user_action": "use_default"}

    # 保存手动 Prompt
    import os
    task_name = state.get("config", {}).get("task_name", "manual")
    save_folder = state.get("config", {}).get("prompt_save_folder", "prompts")
    os.makedirs(save_folder, exist_ok=True)
    save_path = os.path.join(save_folder, f"{task_name}_manual_prompt.txt")

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(prompt_text)

    return {
        "generated_prompt": prompt_text,
        "prompt_saved_path": save_path,
        "user_action": "accept",
    }


# ============================================================================
# 工作流构建
# ============================================================================

def build_web_workflow() -> StateGraph:
    """
   构建 Web 版 LangGraph 工作流
    使用智能 HITL 对话节点
    """
    workflow = StateGraph(AgentState)

    # 添加数据处理节点
    workflow.add_node("load_config", NODES["load_config_node"])
    workflow.add_node("integrate", NODES["integrate_node"])
    workflow.add_node("field_check", NODES["field_check_node"])
    workflow.add_node("data_quality", NODES["data_quality_node"])
    workflow.add_node("filter", NODES["filter_node"])

    # 添加智能 HITL 节点
    workflow.add_node("llm_hitl", lambda state: state)  # 占位，实际在 Runner 中处理
    workflow.add_node("modify_config", modify_config_placeholder)
    workflow.add_node("data_lookup", lambda state: state)  # 占位

    # Prompt 生成节点
    workflow.add_node("parse_strategy", NODES["parse_strategy_node"])
    workflow.add_node("generate_prompt", NODES["generate_prompt_node"])
    workflow.add_node("llm_prompt_check", lambda state: state)  # 占位
    workflow.add_node("edit_prompt", lambda state: state)  # 占位，由 WEB_NODES 处理
    workflow.add_node("use_default", NODES["use_default_prompt_node"])
    workflow.add_node("manual_prompt", manual_prompt_placeholder)

    # 批量评估节点
    workflow.add_node("prepare_eval", NODES["prepare_eval_node"])
    workflow.add_node("batch_eval", NODES["batch_eval_node"])
    workflow.add_node("result_check", NODES["result_check_node"])
    workflow.add_node("llm_eval_approval", lambda state: state)  # 占位
    workflow.add_node("retry_failed", NODES["retry_failed_node"])
    workflow.add_node("view_failed", lambda state: state)  # 占位
    workflow.add_node("export_result", NODES["export_result_node"])

    # 入口边
    workflow.add_edge(START, "load_config")
    workflow.add_edge("load_config", "integrate")
    workflow.add_edge("integrate", "field_check")

    # 检查路由
    workflow.add_conditional_edges("field_check", field_check_router, {
        "data_quality": "data_quality",
        "llm_hitl": "llm_hitl",
    })

    workflow.add_conditional_edges("data_quality", data_quality_router, {
        "filter": "filter",
        "llm_hitl": "llm_hitl",
    })

    workflow.add_conditional_edges("filter", filter_router, {
        "parse_strategy": "parse_strategy",
        "prepare_eval": "prepare_eval",
        "llm_hitl": "llm_hitl",
    })

    # HITL 路由
    workflow.add_conditional_edges("llm_hitl", llm_hitl_router, {
        "data_quality": "data_quality",
        "filter": "filter",
        "parse_strategy": "parse_strategy",
        "modify_config": "modify_config",
        "data_lookup": "data_lookup",
        "terminate": END,
    })

    # 数据查询路由
    workflow.add_conditional_edges("data_lookup", data_lookup_router, {
        "data_lookup": "data_lookup",
        "llm_hitl": "llm_hitl",
        "terminate": END,
    })

    # 修改后重试路由
    workflow.add_conditional_edges("modify_config", retry_router, {
        "integrate": "integrate",
        "field_check": "field_check",
        "data_quality": "data_quality",
        "filter": "filter",
    })

    # Prompt 生成流程
    workflow.add_edge("parse_strategy", "generate_prompt")
    workflow.add_edge("generate_prompt", "llm_prompt_check")

    workflow.add_conditional_edges("llm_prompt_check", prompt_check_router, {
        "prepare_eval": "prepare_eval",
        "edit_prompt": "edit_prompt",
        "generate_prompt": "generate_prompt",
        "use_default": "use_default",
        "manual_prompt": "manual_prompt",
        "terminate": END,
    })

    workflow.add_edge("edit_prompt", "prepare_eval")
    workflow.add_edge("use_default", "prepare_eval")
    workflow.add_edge("manual_prompt", "prepare_eval")

    # 批量评估流程
    workflow.add_edge("prepare_eval", "batch_eval")
    workflow.add_edge("batch_eval", "result_check")

    workflow.add_conditional_edges("result_check", result_check_router, {
        "export_result": "export_result",
        "llm_eval_approval": "llm_eval_approval",
    })

    workflow.add_conditional_edges("llm_eval_approval", llm_eval_approval_router, {
        "export_result": "export_result",
        "retry_failed": "retry_failed",
        "view_failed": "view_failed",
        "llm_eval_approval": "llm_eval_approval",
        "terminate": END,
    })

    workflow.add_conditional_edges("view_failed", view_failed_router, {
        "retry_failed": "retry_failed",
        "llm_eval_approval": "llm_eval_approval",
        "export_result": "export_result",
    })

    workflow.add_edge("retry_failed", "result_check")
    workflow.add_edge("export_result", END)

    return workflow


# ============================================================================
# Web Agent Runner
# ============================================================================

class WebAgentRunner:
    """
    Web Agent 执行器
    处理 HITL 节点的异步通信和流程控制
    """

    HITL_NODES = [
        "llm_hitl",
        "llm_prompt_check",
        "llm_eval_approval",
        "data_lookup",
        "view_failed",
        "edit_prompt",
    ]

    def __init__(self, session_id: str, ws_callback: Callable[[Dict], Awaitable[None]]):
        self.session_id = session_id
        self.ws_callback = ws_callback
        self.hitl_ctx: Optional[WebHITLContext] = None

        # 构建工作流
        self.workflow = build_web_workflow()
        self.app = self.workflow.compile()

        # 执行状态
        self._running = False
        self._current_state: Dict = {}
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    async def initialize(self):
        """初始化 HITL 上下文"""
        self.hitl_ctx = await WebHITLContext.get(self.session_id)
        self.hitl_ctx.set_ws_callback(self.ws_callback)

    async def run(self, config: Dict) -> Dict:
        """
        运行 Agent

        Args:
            config: 任务配置

        Returns:
            执行结果
        """
        await self.initialize()

        # 初始化状态
        initial_state = get_default_state()
        initial_state["config"] = merge_config(config)
        initial_state["session_id"] = self.session_id
        initial_state["task_id"] = config.get("task_id", "")

        self._current_state = dict(initial_state)
        self._running = True

        # 发送开始消息
        await self.hitl_ctx.send_progress("start", 0, "任务开始")

        # 执行工作流
        result = await self._run_workflow_async()

        return result

    async def _run_workflow_async(self) -> Dict:
        """异步执行工作流，处理 HITL 节点"""
        state = self._current_state

        try:
            current_node = "load_config"

            while self._running:
                # 执行当前节点
                node_result = await self._execute_node(current_node, state)

                # 更新状态
                if node_result:
                    for key, value in node_result.items():
                        state[key] = value

                # 确定下一个节点
                next_node = self._get_next_node(current_node, state)

                await self.hitl_ctx.send_log("INFO", "_run_workflow", f"[DEBUG] after {current_node}, next_node={next_node}, user_action={state.get('user_action', 'N/A')}")

                if next_node == END or next_node is None:
                    break

                current_node = next_node

            # 发送完成消息
            await self.hitl_ctx.send_completed({
                "output_xlsx_path": state.get("output_xlsx_path"),
                "output_pkl_path": state.get("output_pkl_path"),
                "results_summary": {
                    "total": len(state.get("input_dict", {})),
                    "success": len(state.get("results_dict", {})),
                    "failed": len(state.get("failed_dois", [])),
                }
            })

            return state

        except Exception as e:
            logger.exception(f"Web Agent 执行异常: {self.session_id}")
            await self.hitl_ctx.send_failed(str(e))
            return {"error_message": str(e)}

    async def _execute_node(self, node_name: str, state: Dict) -> Dict:
        """
        执行单个节点

        Args:
            node_name: 节点名称
            state: 当前状态

        Returns:
            节点返回的状态更新
        """
        # 发送进度
        await self.hitl_ctx.send_progress(node_name, 0, f"正在执行: {node_name}")
        await self.hitl_ctx.send_log("INFO", node_name, f"开始执行")

        if node_name in self.HITL_NODES:
            # HITL 节点使用异步 Web 版本
            node_func = WEB_NODES.get(f"{node_name}_node")
            if node_func:
                result = await node_func(state, self.hitl_ctx)
            else:
                result = {}
        else:
            # 非 HITL 节点使用同步版本（在线程池执行）
            node_func = NODES.get(f"{node_name}_node")
            if node_func:
                # 注入进度回调，让同步节点能从线程中发送进度
                loop = asyncio.get_running_loop()
                state["_progress_callback"] = lambda step, progress, message, details=None: \
                    asyncio.run_coroutine_threadsafe(
                        self.hitl_ctx.send_progress(step, progress, message, details),
                        loop
                    )
                state["_log_callback"] = lambda level, node, message: \
                    asyncio.run_coroutine_threadsafe(
                        self.hitl_ctx.send_log(level, node, message),
                        loop
                    )
                result = await asyncio.get_event_loop().run_in_executor(
                    None, node_func, state
                )
                # 清理回调
                state.pop("_progress_callback", None)
                state.pop("_log_callback", None)
            else:
                result = {}

        # 发送完成进度
        step_details = result.get("step_details", {})
        await self.hitl_ctx.send_progress(node_name, 100, f"完成: {node_name}", step_details)

        # 发送详细的执行结果日志
        check_results = result.get("check_results", {})
        if check_results:
            # 发送检查结果摘要
            for check_type, check_data in check_results.items():
                if isinstance(check_data, dict):
                    passed = check_data.get("passed", False)
                    status = "✅ 通过" if passed else "❌ 未通过"
                    summary_parts = []

                    if "failed_count" in check_data:
                        summary_parts.append(f"失败: {check_data['failed_count']}")
                    if "total_count" in check_data:
                        summary_parts.append(f"总数: {check_data['total_count']}")
                    if "missing_fields" in check_data and check_data["missing_fields"]:
                        summary_parts.append(f"缺失字段: {', '.join(check_data['missing_fields'])}")
                    if "success_rate" in check_data:
                        summary_parts.append(f"成功率: {check_data['success_rate']*100:.1f}%")

                    summary = ", ".join(summary_parts) if summary_parts else ""
                    log_msg = f"{status} - {summary}"
                    await self.hitl_ctx.send_log("INFO", node_name, log_msg)

        # 发送其他重要结果
        if result.get("error_message"):
            await self.hitl_ctx.send_log("WARNING", node_name, result.get("error_message"))

        # 发送数据统计
        total_rows = result.get("total_rows")
        if total_rows:
            await self.hitl_ctx.send_log("INFO", node_name, f"数据行数: {total_rows}")

        return result

    def _get_next_node(self, current_node: str, state: Dict) -> str:
        """
        获取下一个节点

        Args:
            current_node: 当前节点名称
            state: 当前状态

        Returns:
            下一个节点名称或 END
        """
        # 定义路由逻辑
        routers = {
            "field_check": lambda s: field_check_router(s),
            "data_quality": lambda s: data_quality_router(s),
            "filter": lambda s: filter_router(s),
            "llm_hitl": lambda s: llm_hitl_router(s),
            "modify_config": lambda s: retry_router(s),
            "data_lookup": lambda s: data_lookup_router(s),
            "llm_prompt_check": lambda s: prompt_check_router(s),
            "result_check": lambda s: result_check_router(s),
            "llm_eval_approval": lambda s: llm_eval_approval_router(s),
            "view_failed": lambda s: view_failed_router(s),
            "retry_failed": lambda s: retry_router_after_eval(s),
        }

        # 定义固定边
        edges = {
            "load_config": "integrate",
            "integrate": "field_check",
            "parse_strategy": "generate_prompt",
            "generate_prompt": "llm_prompt_check",
            "edit_prompt": "prepare_eval",
            "use_default": "prepare_eval",
            "manual_prompt": "prepare_eval",
            "prepare_eval": "batch_eval",
            "batch_eval": "result_check",
            "export_result": END,
        }

        # 检查是否有路由
        if current_node in routers:
            next_node = routers[current_node](state)
            # 映射特殊路由结果
            route_map = {
                "terminate": END,
            }
            return route_map.get(next_node, next_node)

        # 检查是否有固定边
        if current_node in edges:
            return edges[current_node]

        return END

    def stop(self):
        """停止执行（同时唤醒可能阻塞在 HITL 等待中的工作流）"""
        self._running = False
        try:
            hitl_ctx = WebHITLContext.get_sync(self.session_id)
            if hitl_ctx:
                hitl_ctx.abort("任务被取消")
        except Exception:
            pass


# ============================================================================
# 便捷函数
# ============================================================================

async def run_web_agent(
    session_id: str,
    config: Dict,
    ws_callback: Callable[[Dict], Awaitable[None]]
) -> Dict:
    """
    运行 Web Agent

    Args:
        session_id: 会话 ID
        config: 任务配置
        ws_callback: WebSocket 回调函数

    Returns:
        执行结果
    """
    runner = WebAgentRunner(session_id, ws_callback)
    return await runner.run(config)


async def handle_user_action(session_id: str, action: str, data: Dict = None):
    """
    处理用户动作

    Args:
        session_id: 会话 ID
        action: 用户选择的动作
        data: 额外数据
    """
    logger.info(f"[DEBUG handle_user_action] session_id={session_id}, action={action}, data={data}")
    hitl_ctx = await WebHITLContext.get(session_id)
    hitl_ctx.set_user_action(action, data)
    logger.info(f"[DEBUG handle_user_action] set_user_action completed for session_id={session_id}")


async def cleanup_session(session_id: str):
    """
    清理会话

    Args:
        session_id: 会话 ID
    """
    await WebHITLContext.remove(session_id)