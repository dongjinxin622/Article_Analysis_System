"""
Excel 批量提取 LangGraph State 定义
"""
from typing import TypedDict, Dict, List, Optional, Any
import pandas as pd


class AgentState(TypedDict):
    """
    Excel 批量提取工作流状态

    包含数据流转、检查结果、流程控制、HITL 对话等完整状态
    """

    # ==================== 配置 ====================
    config: Dict
    """任务配置，包含 folder_path, task_name, strategy_docx, llm_model 等"""

    # ==================== 数据流转 ====================
    df: Optional[pd.DataFrame]
    """整合后 -> 过滤后的 DataFrame"""
    original_df: Optional[pd.DataFrame]
    """原始 DataFrame（用于导出时保留完整数据）"""

    # ==================== 检查结果 ====================
    check_results: Dict[str, Dict]
    """检查结果
    {
        "field": {"passed": bool, "failed_count": int, "failed_indices": [...], "issues": [...]},
        "quality": {"passed": bool, "avg_score": float, "low_score_count": int, ...},
        "filter": {"passed": bool, "remaining_count": int, "removed_count": int, ...},
        "eval": {"passed": bool, "success_rate": float, "parse_rate": float, "failed_dois": [...]}
    }
    """

    # ==================== 流程控制 ====================
    current_step: str
    """当前步骤名称"""
    current_node: str
    """当前 LangGraph 节点名称"""
    error_message: str
    """错误信息"""
    pending_check: Optional[str]
    """当前待审核的检查类型: field/quality/filter/prompt/eval"""

    # ==================== HITL 对话 ====================
    user_action: str
    """用户选择的动作: continue/modify/terminate/accept/edit/ask_more 等"""
    action_data: Optional[Dict]
    """用户动作附带的数据（如修改后的配置值）"""
    chat_history: List[Dict[str, str]]
    """对话历史 [{"role": "assistant/user", "content": "..."}]"""
    hitl_turns: int
    """当前 HITL 对话轮次（防止无限对话）"""
    max_hitl_turns: int
    """最大 HITL 对话轮次限制"""

    # ==================== Prompt 生成 ====================
    strategy_content: Optional[str]
    """策略 Word 文档原始内容"""
    parsed_strategy: Optional[Dict]
    """解析后的策略定义
    {
        "domain_fields": {"laser_type": "激光类型", ...},
        "key_indicators": {"pulse_width": "脉冲宽度", ...}
    }
    """
    generated_prompt: Optional[str]
    """生成的评估 Prompt"""
    prompt_saved_path: Optional[str]
    """Prompt 保存路径"""

    # ==================== 批量评估 ====================
    input_dict: Optional[Dict[str, Dict]]
    """评估输入数据 {doi: {title, abstract, authors, ...}}"""
    results_dict: Optional[Dict[str, Dict]]
    """评估结果数据 {doi: {related, institution, summary, ...}}"""
    batch_save_dir: Optional[str]
    """批次结果保存目录（断点续传）"""
    failed_dois: Optional[List[str]]
    """失败的 DOI 列表"""
    retry_count: int
    """重试次数"""

    # ==================== 结构化输出 ====================
    evaluation_model: Optional[Dict]
    """动态生成的 Pydantic 模型定义（序列化）"""
    use_structured_output: bool
    """是否使用结构化输出"""
    structured_supported: Optional[bool]
    """当前模型是否支持结构化输出"""

    # ==================== 结果导出 ====================
    output_pkl_path: Optional[str]
    """输出 PKL 文件路径"""
    output_xlsx_path: Optional[str]
    """输出 Excel 文件路径"""

    # ==================== 任务元数据 ====================
    task_id: Optional[str]
    """任务 ID"""
    session_id: Optional[str]
    """WebSocket 会话 ID"""
    user_id: Optional[int]
    """用户 ID"""


def get_default_state() -> AgentState:
    """获取默认状态"""
    return AgentState(
        config={},
        df=None,
        original_df=None,
        check_results={},
        current_step="",
        current_node="",
        error_message="",
        pending_check=None,
        user_action="",
        action_data=None,
        chat_history=[],
        hitl_turns=0,
        max_hitl_turns=10,
        strategy_content=None,
        parsed_strategy=None,
        generated_prompt=None,
        prompt_saved_path=None,
        input_dict=None,
        results_dict=None,
        batch_save_dir=None,
        failed_dois=None,
        retry_count=0,
        evaluation_model=None,
        use_structured_output=True,
        structured_supported=None,
        output_pkl_path=None,
        output_xlsx_path=None,
        task_id=None,
        session_id=None,
        user_id=None,
    )


def merge_config(user_config: Dict, default_config: Dict = None) -> Dict:
    """合并用户配置和默认配置"""
    if default_config is None:
        default_config = DEFAULT_CONFIG

    merged = default_config.copy()
    for key, value in user_config.items():
        if value is not None:
            merged[key] = value
    return merged


from backend.app.core.config import settings

# 默认配置
DEFAULT_CONFIG = {
    "folder_path": "",
    "task_name": "批量提取任务",
    "strategy_docx": None,
    "llm_model": settings.MODEL_NAME,
    "hitl_llm_model": settings.MODEL_NAME,
    "max_concurrent": 5,
    "batch_size": 50,
    "quality_threshold": 0.6,
    "min_filter_count": 5,
    "dedup_field": "doi",
    "required_fields": ["doi", "title", "abstract"],
    "extract_fields": ["related", "institution", "summary", "key_technologies", "application_areas"],
    "domain_fields": {},
    "key_indicators": {},
    "enable_hitl": True,
    "enable_smart_hitl": True,
    "max_retry_count": 3,
    "prompt_save_folder": "prompts",
    "batch_save_folder": "batch_results",
    "output_folder": "outputs",
}