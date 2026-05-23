"""
Excel 批量提取同步处理节点
数据处理、检查、Prompt生成、批量评估等节点函数
"""
import os
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Any
import logging
import pickle
from concurrent.futures import ThreadPoolExecutor, as_completed

from backend.app.excel_extraction.state import AgentState
from backend.app.excel_extraction.models import create_evaluation_model
from backend.app.core.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# 节点函数字典
# ============================================================================
NODES = {}


# ============================================================================
# 数据处理节点
# ============================================================================

def load_config_node(state: AgentState) -> Dict:
    """加载配置节点"""
    config = state.get("config", {})

    # 确保必要目录存在
    folders = ["prompt_save_folder", "batch_save_folder", "output_folder"]
    for folder_key in folders:
        folder_path = config.get(folder_key, "")
        if folder_path:
            os.makedirs(folder_path, exist_ok=True)

    return {
        "current_step": "load_config",
        "current_node": "load_config",
        "config": config,
        "error_message": "",
    }


def integrate_node(state: AgentState) -> Dict:
    """数据整合节点 - 合并多个 Excel 文件"""
    config = state.get("config", {})
    folder_path = config.get("folder_path", "")

    if not folder_path:
        return {
            "current_step": "integrate",
            "current_node": "integrate",
            "error_message": "未指定 Excel 文件路径",
            "df": None,
        }

    try:
        # 查找所有 Excel 文件
        excel_files = []
        for f in os.listdir(folder_path):
            if f.endswith((".xlsx", ".xls")):
                excel_files.append(os.path.join(folder_path, f))

        if not excel_files:
            return {
                "current_step": "integrate",
                "current_node": "integrate",
                "error_message": f"目录 {folder_path} 中未找到 Excel 文件",
                "df": None,
            }

        # 合并所有 Excel
        dfs = []
        for file_path in excel_files:
            df = pd.read_excel(file_path)
            df["_source_file"] = os.path.basename(file_path)
            dfs.append(df)

        merged_df = pd.concat(dfs, ignore_index=True)

        # 标准化列名
        column_mapping = {
            "DOI": "doi",
            "doi": "doi",
            "Title": "title",
            "title": "title",
            "Article Title": "title",
            "Abstract": "abstract",
            "abstract": "abstract",
            "Authors": "authors",
            "authors": "authors",
            "Author": "authors",
            "Year": "year",
            "year": "year",
            "Publication Year": "year",
            "Journal": "journal",
            "journal": "journal",
            "Source": "journal",
        }
        merged_df.columns = [column_mapping.get(c, c.lower()) for c in merged_df.columns]

        logger.info(f"[integrate] 合并 {len(excel_files)} 个文件，共 {len(merged_df)} 条记录")

        return {
            "current_step": "integrate",
            "current_node": "integrate",
            "df": merged_df,
            "original_df": merged_df.copy(),
            "error_message": "",
            "step_details": {
                "file_count": len(excel_files),
                "row_count": len(merged_df),
                "columns": list(merged_df.columns),
            }
        }

    except Exception as e:
        logger.exception(f"[integrate] 数据整合失败")
        return {
            "current_step": "integrate",
            "current_node": "integrate",
            "error_message": f"数据整合失败: {str(e)}",
            "df": None,
        }


def field_check_node(state: AgentState) -> Dict:
    """字段检查节点"""
    df = state.get("df")
    config = state.get("config", {})
    required_fields = config.get("required_fields", ["doi", "title", "abstract"])

    if df is None:
        return {
            "current_step": "field_check",
            "current_node": "field_check",
            "check_results": {"field": {"passed": False, "error": "无数据"}},
            "error_message": "无数据",
        }

    try:
        # 检查必需字段
        available_fields = list(df.columns)
        missing_fields = [f for f in required_fields if f not in available_fields]

        # 检查每条记录的字段完整性
        failed_indices = []
        issues = []

        for idx, row in df.iterrows():
            row_issues = []
            for field in required_fields:
                if field in row:
                    value = row[field]
                    if pd.isna(value) or str(value).strip() == "":
                        row_issues.append(f"missing_{field}")
            if row_issues:
                failed_indices.append(idx)
                issues.append({"index": idx, "issues": row_issues})

        passed = len(missing_fields) == 0 and len(failed_indices) < len(df) * 0.2  # 允许 20% 缺失

        check_result = {
            "passed": passed,
            "missing_fields": missing_fields,
            "failed_count": len(failed_indices),
            "failed_indices": failed_indices[:50],  # 只返回前 50 个
            "issues": issues[:50],
            "total_count": len(df),
        }

        logger.info(f"[field_check] 检查结果: passed={passed}, failed={len(failed_indices)}")

        return {
            "current_step": "field_check",
            "current_node": "field_check",
            "check_results": {**state.get("check_results", {}), "field": check_result},
            "error_message": "" if passed else f"字段检查未通过：{len(failed_indices)} 条记录缺少必需字段",
        }

    except Exception as e:
        logger.exception(f"[field_check] 字段检查失败")
        return {
            "current_step": "field_check",
            "current_node": "field_check",
            "check_results": {"field": {"passed": False, "error": str(e)}},
            "error_message": f"字段检查失败: {str(e)}",
        }


def data_quality_node(state: AgentState) -> Dict:
    """数据质量评分节点"""
    df = state.get("df")
    config = state.get("config", {})
    quality_threshold = config.get("quality_threshold", 0.6)

    if df is None:
        return {
            "current_step": "data_quality",
            "current_node": "data_quality",
            "check_results": {"quality": {"passed": False, "error": "无数据"}},
        }

    try:
        # 计算每条记录的质量评分
        quality_scores = []
        quality_issues = []

        for idx, row in df.iterrows():
            score = 1.0
            issues = []

            # DOI 检查
            doi = row.get("doi", "")
            if pd.isna(doi) or str(doi).strip() == "":
                score -= 0.2
                issues.append("missing_doi")
            elif not str(doi).startswith("10."):
                score -= 0.1
                issues.append("invalid_doi_format")

            # 标题检查
            title = row.get("title", "")
            if pd.isna(title) or str(title).strip() == "":
                score -= 0.3
                issues.append("missing_title")
            elif len(str(title)) < 10:
                score -= 0.1
                issues.append("short_title")

            # 摘要检查
            abstract = row.get("abstract", "")
            if pd.isna(abstract) or str(abstract).strip() == "":
                score -= 0.3
                issues.append("missing_abstract")
            elif len(str(abstract)) < 50:
                score -= 0.1
                issues.append("short_abstract")

            # 作者检查
            authors = row.get("authors", "")
            if pd.isna(authors) or str(authors).strip() == "":
                score -= 0.1
                issues.append("missing_authors")

            quality_scores.append(max(0.0, score))
            quality_issues.append(issues)

        df["_quality_score"] = quality_scores
        df["_quality_issues"] = quality_issues

        avg_score = np.mean(quality_scores)
        low_score_count = sum(1 for s in quality_scores if s < quality_threshold)

        passed = avg_score >= quality_threshold and low_score_count < len(df) * 0.3

        check_result = {
            "passed": passed,
            "avg_score": float(avg_score),
            "low_score_count": low_score_count,
            "quality_threshold": quality_threshold,
            "score_distribution": {
                "high": sum(1 for s in quality_scores if s >= 0.8),
                "medium": sum(1 for s in quality_scores if 0.6 <= s < 0.8),
                "low": sum(1 for s in quality_scores if s < 0.6),
            },
        }

        logger.info(f"[data_quality] 平均质量评分: {avg_score:.2f}, 低评分记录: {low_score_count}")

        return {
            "current_step": "data_quality",
            "current_node": "data_quality",
            "df": df,
            "check_results": {**state.get("check_results", {}), "quality": check_result},
            "error_message": "" if passed else f"质量评分低于阈值：平均 {avg_score:.2f} < {quality_threshold}",
        }

    except Exception as e:
        logger.exception(f"[data_quality] 质量评分失败")
        return {
            "current_step": "data_quality",
            "current_node": "data_quality",
            "check_results": {"quality": {"passed": False, "error": str(e)}},
            "error_message": f"质量评分失败: {str(e)}",
        }


def filter_node(state: AgentState) -> Dict:
    """数据过滤和去重节点"""
    df = state.get("df")
    config = state.get("config", {})
    quality_threshold = config.get("quality_threshold", 0.6)
    dedup_field = config.get("dedup_field", "doi")
    min_filter_count = config.get("min_filter_count", 5)

    if df is None:
        return {
            "current_step": "filter",
            "current_node": "filter",
            "check_results": {"filter": {"passed": False, "error": "无数据"}},
        }

    try:
        original_count = len(df)

        # 质量过滤
        if "_quality_score" in df.columns:
            df = df[df["_quality_score"] >= quality_threshold]

        after_quality_count = len(df)

        # 去重
        if dedup_field in df.columns:
            df = df.drop_duplicates(subset=[dedup_field], keep="first")

        after_dedup_count = len(df)

        passed = after_dedup_count >= min_filter_count

        check_result = {
            "passed": passed,
            "original_count": original_count,
            "after_quality_count": after_quality_count,
            "after_dedup_count": after_dedup_count,
            "removed_count": original_count - after_dedup_count,
            "remaining_count": after_dedup_count,
            "min_filter_count": min_filter_count,
        }

        logger.info(f"[filter] 过滤结果: {original_count} -> {after_dedup_count} 条")

        return {
            "current_step": "filter",
            "current_node": "filter",
            "df": df,
            "check_results": {**state.get("check_results", {}), "filter": check_result},
            "error_message": "" if passed else f"过滤后数据不足：{after_dedup_count} < {min_filter_count}",
        }

    except Exception as e:
        logger.exception(f"[filter] 数据过滤失败")
        return {
            "current_step": "filter",
            "current_node": "filter",
            "check_results": {"filter": {"passed": False, "error": str(e)}},
            "error_message": f"数据过滤失败: {str(e)}",
        }


# ============================================================================
# Prompt 生成节点
# ============================================================================

def _parse_strategy_with_llm(strategy_content: str) -> Dict:
    """
    使用 LLM 解析策略文档内容
    从 Word 文档段落中智能提取领域字段和关键指标定义
    """
    import asyncio
    from backend.app.services.llm_service import LLMService

    system_message = "你是一个策略文档解析助手。请分析策略文档内容，提取领域字段定义和关键指标定义，并以 JSON 格式返回。"

    user_message = f"""请分析以下策略文档内容，提取其中的字段定义。

策略文档内容：
---
{strategy_content}
---

请按以下规则解析：

1. **domain_fields（领域字段）**：描述研究领域相关的分类字段，如激光类型、增益介质、技术类型等。每个字段有字段名和可选值列表。
2. **key_indicators（关键指标）**：描述具体的技术指标/度量，如脉冲宽度、重复频率、中心波长等。每个指标有指标名和单位。
3. 忽略标准元数据字段（如 DOI、Authors、Title、Abstract、Source Title、Reprint Addresses、Publication Year 等）。
4. 忽略空值字段（值为空或只有占位符的）。
5. 字段名应去除 `_x` 等后缀，保持简洁但有辨识度。
6. 字段的描述/值列表应完整保留，包括所有可选值或单位。

请以以下 JSON 格式返回（不要包含 ```json 标记）：
{{
    "domain_fields": {{
        "字段名1": "字段描述/可选值",
        "字段名2": "字段描述/可选值"
    }},
    "key_indicators": {{
        "指标名1": "指标描述/单位",
        "指标名2": "指标描述/单位"
    }}
}}
"""

    async def _call_llm():
        llm = LLMService()
        try:
            response = await llm.chat(
                user_message=user_message,
                system_message=system_message,
                json_mode=True,
                max_retries=2
            )
            result = llm.parse_json_response(response)
            return result
        finally:
            await llm.close()

    try:
        # 兼容不同事件循环状态
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在已有运行的 loop 中（如 FastAPI），使用 create_task
                logger.warning("检测到运行中的事件循环，使用嵌套任务")
                task = asyncio.ensure_future(_call_llm())
                result = loop.run_until_complete(task)
            else:
                result = loop.run_until_complete(_call_llm())
        except RuntimeError:
            # 没有事件循环或已关闭，创建新的
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(_call_llm())
            finally:
                new_loop.close()

        if result and isinstance(result, dict):
            # 过滤空值字段
            domain_fields = {k: v for k, v in result.get("domain_fields", {}).items() if v and v.strip()}
            key_indicators = {k: v for k, v in result.get("key_indicators", {}).items() if v and v.strip()}
            return {
                "domain_fields": domain_fields,
                "key_indicators": key_indicators,
            }

    except Exception as e:
        logger.warning(f"[_parse_strategy_with_llm] LLM 解析失败: {e}，回退到空结果")

    return {"domain_fields": {}, "key_indicators": {}}


def parse_strategy_node(state: AgentState) -> Dict:
    """解析策略 Word 文档节点（使用 LLM 智能解析）"""
    config = state.get("config", {})
    strategy_docx = config.get("strategy_docx")

    if not strategy_docx or not os.path.exists(strategy_docx):
        logger.info(f"[parse_strategy] 无策略文档，使用默认配置")
        return {
            "current_step": "parse_strategy",
            "current_node": "parse_strategy",
            "strategy_content": None,
            "parsed_strategy": {},
        }

    try:
        from docx import Document

        doc = Document(strategy_docx)

        # 提取文档内容
        content = []
        for para in doc.paragraphs:
            if para.text.strip():
                content.append(para.text.strip())

        strategy_content = "\n".join(content)

        # 使用 LLM 智能解析策略文档
        parsed_strategy = _parse_strategy_with_llm(strategy_content)

        logger.info(
            f"[parse_strategy] 解析完成: "
            f"领域字段 {len(parsed_strategy.get('domain_fields', {}))} 个, "
            f"关键指标 {len(parsed_strategy.get('key_indicators', {}))} 个"
        )

        return {
            "current_step": "parse_strategy",
            "current_node": "parse_strategy",
            "strategy_content": strategy_content,
            "parsed_strategy": parsed_strategy,
            "error_message": "",
        }

    except Exception as e:
        logger.exception(f"[parse_strategy] 解析策略文档失败")
        return {
            "current_step": "parse_strategy",
            "current_node": "parse_strategy",
            "strategy_content": None,
            "parsed_strategy": {},
            "error_message": f"解析策略文档失败: {str(e)}",
        }


def generate_prompt_node(state: AgentState) -> Dict:
    """生成评估 Prompt 节点"""
    config = state.get("config", {})
    parsed_strategy = state.get("parsed_strategy", {})
    domain_fields = parsed_strategy.get("domain_fields", {})
    key_indicators = parsed_strategy.get("key_indicators", {})

    # 合并配置中的字段定义
    config_domain = config.get("domain_fields", {})
    config_indicators = config.get("key_indicators", {})

    all_domain_fields = {**domain_fields, **config_domain}
    all_key_indicators = {**key_indicators, **config_indicators}

    # 生成 Prompt
    prompt = _build_extraction_prompt(all_domain_fields, all_key_indicators, config)

    # 保存 Prompt
    task_name = config.get("task_name", "default")
    save_folder = config.get("prompt_save_folder", "prompts")
    os.makedirs(save_folder, exist_ok=True)
    save_path = os.path.join(save_folder, f"{task_name}_prompt.txt")

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    logger.info(f"[generate_prompt] Prompt 已保存: {save_path}")

    return {
        "current_step": "generate_prompt",
        "current_node": "generate_prompt",
        "generated_prompt": prompt,
        "prompt_saved_path": save_path,
        "error_message": "",
    }


def use_default_prompt_node(state: AgentState) -> Dict:
    """使用默认 Prompt 节点"""
    config = state.get("config", {})

    # 生成默认 Prompt（无领域特定字段）
    prompt = _build_extraction_prompt({}, {}, config)

    # 保存
    task_name = config.get("task_name", "default")
    save_folder = config.get("prompt_save_folder", "prompts")
    os.makedirs(save_folder, exist_ok=True)
    save_path = os.path.join(save_folder, f"{task_name}_default_prompt.txt")

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(prompt)

    logger.info(f"[use_default_prompt] 使用默认 Prompt: {save_path}")

    return {
        "current_step": "use_default_prompt",
        "current_node": "use_default_prompt",
        "generated_prompt": prompt,
        "prompt_saved_path": save_path,
        "error_message": "",
    }


def _build_extraction_prompt(
    domain_fields: Dict[str, str],
    key_indicators: Dict[str, str],
    config: Dict
) -> str:
    """构建评估 Prompt"""
    extract_fields = config.get("extract_fields", ["related", "institution", "summary"])

    # 基础字段定义
    field_defs = {
        "related": "是否与目标研究领域相关 (boolean: true/false)",
        "institution": "通讯作者所属机构 (string)",
        "summary": "论文核心贡献摘要 (string, 200字以内)",
        "key_technologies": "使用的关键技术列表 (array of strings)",
        "application_areas": "应用领域列表 (array of strings)",
    }

    # 添加领域特定字段
    for name, desc in domain_fields.items():
        field_defs[name] = f"{desc} (string)"

    # 添加关键指标字段
    for name, desc in key_indicators.items():
        field_defs[name] = f"{desc} (string)"

    # 只包含要提取的字段
    selected_fields = {}
    for f in extract_fields:
        if f in field_defs:
            selected_fields[f] = field_defs[f]
    for name in domain_fields:
        selected_fields[name] = field_defs[name]
    for name in key_indicators:
        selected_fields[name] = field_defs[name]

    schema_desc = json.dumps(selected_fields, ensure_ascii=False, indent=2)

    prompt = f"""请分析以下论文题录数据，按指定字段提取信息。

## 论文数据
DOI: {{doi}}
标题: {{title}}
作者: {{authors}}
摘要: {{abstract}}

## 提取字段定义
{schema_desc}

## 输出要求
请以 JSON 格式返回结果，确保：
1. 所有字段都有值（无法确定时填 "N/A")
2. related 字段必须是 true 或 false
3. 数组字段即使是空也要返回 []
4. 不要添加额外的解释或说明，直接返回 JSON
"""

    return prompt


# ============================================================================
# 批量评估节点
# ============================================================================

def prepare_eval_node(state: AgentState) -> Dict:
    """准备评估数据节点"""
    df = state.get("df")
    config = state.get("config", {})
    dedup_field = config.get("dedup_field", "doi")

    if df is None:
        return {
            "current_step": "prepare_eval",
            "current_node": "prepare_eval",
            "error_message": "无数据",
            "input_dict": None,
        }

    try:
        # 创建批次保存目录
        task_id = state.get("task_id", "default")
        batch_save_folder = config.get("batch_save_folder", "batch_results")
        batch_save_dir = os.path.join(batch_save_folder, task_id)
        os.makedirs(batch_save_dir, exist_ok=True)

        # 构建输入字典
        input_dict = {}
        for idx, row in df.iterrows():
            key = row.get(dedup_field, f"row_{idx}")
            if pd.isna(key):
                key = f"row_{idx}"
            input_dict[str(key)] = {
                "doi": str(row.get("doi", "N/A")),
                "title": str(row.get("title", "N/A")),
                "authors": str(row.get("authors", "N/A")),
                "abstract": str(row.get("abstract", "N/A")),
                "_row_index": idx,
            }

        # 创建评估模型
        parsed_strategy = state.get("parsed_strategy", {})
        evaluation_model = create_evaluation_model(
            parsed_strategy.get("domain_fields", {}),
            parsed_strategy.get("key_indicators", {}),
            config.get("extract_fields", [])
        )

        logger.info(f"[prepare_eval] 准备评估 {len(input_dict)} 条记录")

        return {
            "current_step": "prepare_eval",
            "current_node": "prepare_eval",
            "input_dict": input_dict,
            "batch_save_dir": batch_save_dir,
            "evaluation_model": evaluation_model,
            "use_structured_output": True,
            "error_message": "",
        }

    except Exception as e:
        logger.exception(f"[prepare_eval] 准备评估失败")
        return {
            "current_step": "prepare_eval",
            "current_node": "prepare_eval",
            "error_message": f"准备评估失败: {str(e)}",
            "input_dict": None,
        }


def batch_eval_node(state: AgentState) -> Dict:
    """批量评估节点（并发处理，支持中间进度通知）"""
    input_dict = state.get("input_dict")
    config = state.get("config", {})
    prompt = state.get("generated_prompt", "")
    batch_save_dir = state.get("batch_save_dir", "")
    progress_cb = state.get("_progress_callback")
    log_cb = state.get("_log_callback")

    if input_dict is None:
        return {
            "current_step": "batch_eval",
            "current_node": "batch_eval",
            "error_message": "无评估数据",
            "results_dict": None,
        }

    # 验证 prompt
    if not prompt or len(prompt.strip()) < 10:
        logger.error(f"[batch_eval] Prompt 无效: {len(prompt) if prompt else 0} 字符")
        return {
            "current_step": "batch_eval",
            "current_node": "batch_eval",
            "error_message": "Prompt 未正确生成或为空",
            "results_dict": None,
        }

    try:
        workers = config.get("max_concurrent", 5)
        batch_size = config.get("batch_size", 50)
        llm_model = config.get("llm_model", settings.MODEL_NAME)

        logger.info(f"[batch_eval] 开始: {len(input_dict)} 条记录, model={llm_model}, workers={workers}")

        results_dict = {}
        failed_dois = []

        items = list(input_dict.items())
        total = len(items)

        if progress_cb:
            progress_cb("batch_eval", 5, f"开始批量评估: {total} 条记录")

        # 分批处理
        for batch_start in range(0, total, batch_size):
            batch_end = min(batch_start + batch_size, total)
            batch_items = items[batch_start:batch_end]
            batch_id = batch_start // batch_size + 1

            logger.info(f"[batch_eval] 处理批次 {batch_id}: {batch_start}-{batch_end}")

            if progress_cb:
                pct = int(5 + 90 * batch_start / total)
                progress_cb("batch_eval", pct, f"处理批次 {batch_id}/{(total // batch_size) + 1}")
            if log_cb:
                log_cb("INFO", "batch_eval", f"开始处理批次 {batch_id} ({batch_start}-{batch_end})")

            # 并发处理批次
            batch_results = _process_batch_concurrent(
                batch_items, prompt, llm_model, workers
            )

            # 合并结果
            batch_success = 0
            batch_fail = 0
            first_error = None
            for doi, result in batch_results.items():
                if result.get("success"):
                    results_dict[doi] = result.get("data", {})
                    batch_success += 1
                else:
                    failed_dois.append(doi)
                    batch_fail += 1
                    if first_error is None:
                        first_error = result.get("error", "")

            logger.info(f"[batch_eval] 批次 {batch_id}: {batch_success} 成功, {batch_fail} 失败, 首个错误: {first_error[:100] if first_error else '无'}")
            if log_cb:
                log_cb("INFO", "batch_eval", f"批次 {batch_id}: {batch_success} 成功, {batch_fail} 失败")

            # 保存批次结果（断点续传）
            batch_file = os.path.join(batch_save_dir, f"batch_{batch_id}.pkl")
            with open(batch_file, "wb") as f:
                pickle.dump(batch_results, f)

        # 计算成功率
        success_count = len(results_dict)
        success_rate = success_count / total if total > 0 else 0

        logger.info(f"[batch_eval] 完成: {success_count}/{total} 成功, {len(failed_dois)} 失败")

        return {
            "current_step": "batch_eval",
            "current_node": "batch_eval",
            "results_dict": results_dict,
            "failed_dois": failed_dois,
            "error_message": "",
            "step_details": {
                "total": total,
                "success_count": success_count,
                "failed_count": len(failed_dois),
                "success_rate": success_rate,
            }
        }

    except Exception as e:
        logger.exception(f"[batch_eval] 批量评估失败")
        return {
            "current_step": "batch_eval",
            "current_node": "batch_eval",
            "error_message": f"批量评估失败: {str(e)}",
            "results_dict": None,
        }


def _process_batch_concurrent(
    batch_items: List,
    prompt: str,
    llm_model: str,
    workers: int
) -> Dict:
    """并发处理一个批次"""
    results = {}

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_call_llm_for_item, doi, data, prompt, llm_model): doi
            for doi, data in batch_items
        }

        for future in as_completed(futures):
            doi = futures[future]
            try:
                result = future.result()
                results[doi] = result
            except Exception as e:
                results[doi] = {"success": False, "error": str(e)}

    return results


def _call_llm_for_item(doi: str, data: Dict, prompt: str, llm_model: str) -> Dict:
    """调用 LLM 处理单条数据（在线程中运行异步函数）"""
    import asyncio
    from backend.app.services.llm_service import LLMService

    try:
        # 构建完整 prompt
        full_prompt = prompt.replace("{doi}", str(data.get("doi", "N/A")))
        full_prompt = full_prompt.replace("{title}", str(data.get("title", "N/A")))
        full_prompt = full_prompt.replace("{authors}", str(data.get("authors", "N/A")))
        full_prompt = full_prompt.replace("{abstract}", str(data.get("abstract", "N/A")))

        # 创建 LLM 服务实例
        llm = LLMService(model=llm_model)

        # 在线程中运行异步函数
        async def _async_call():
            try:
                response = await llm.chat(
                    user_message=full_prompt,
                    system_message="你是学术论文数据提取助手。请严格按照要求的 JSON 格式返回结果。",
                    json_mode=True,
                    max_retries=2
                )
                return response
            finally:
                await llm.close()

        # 创建新的 event loop（线程中必须这样做）
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            response = loop.run_until_complete(_async_call())
        except Exception as api_error:
            logger.error(f"[LLM调用失败] DOI: {doi[:20]}, 错误: {api_error}")
            return {"success": False, "error": f"LLM API 错误: {str(api_error)[:200]}"}
        finally:
            loop.close()

        # 解析响应
        result = llm.parse_json_response(response)
        if result is None:
            return {"success": False, "error": "无法解析 JSON 响应"}

        return {"success": True, "data": result}

    except Exception as e:
        logger.error(f"[LLM调用失败] DOI: {doi[:20]}, 错误: {str(e)[:200]}")
        return {"success": False, "error": str(e)[:200]}


def result_check_node(state: AgentState) -> Dict:
    """结果检查节点"""
    results_dict = state.get("results_dict")
    failed_dois = state.get("failed_dois", [])
    config = state.get("config", {})

    if results_dict is None:
        return {
            "current_step": "result_check",
            "current_node": "result_check",
            "check_results": {"eval": {"passed": False, "error": "无评估结果"}},
        }

    total = len(state.get("input_dict", {}))
    success_count = len(results_dict)
    success_rate = success_count / total if total > 0 else 0

    # 检查解析成功率（related 字段有效性）
    valid_count = 0
    parse_issues = []

    for doi, result in results_dict.items():
        related = result.get("related")
        if related in [True, False]:
            valid_count += 1
        else:
            parse_issues.append(doi)

    parse_rate = valid_count / success_count if success_count > 0 else 0

    # 成功标准：API 成功率 > 80%，解析成功率 > 90%
    passed = success_rate >= 0.8 and parse_rate >= 0.9

    check_result = {
        "passed": passed,
        "success_rate": success_rate,
        "parse_rate": parse_rate,
        "failed_count": len(failed_dois),
        "failed_dois": failed_dois[:50],
        "parse_issues": parse_issues[:50],
    }

    logger.info(f"[result_check] 成功率: {success_rate:.0%}, 解析率: {parse_rate:.0%}")

    return {
        "current_step": "result_check",
        "current_node": "result_check",
        "check_results": {**state.get("check_results", {}), "eval": check_result},
        "error_message": "" if passed else f"评估结果质量不足：成功率 {success_rate:.0%}",
    }


def retry_failed_node(state: AgentState) -> Dict:
    """重试失败记录节点"""
    failed_dois = state.get("failed_dois", [])
    input_dict = state.get("input_dict", {})
    config = state.get("config", {})
    prompt = state.get("generated_prompt", "")
    results_dict = state.get("results_dict", {})
    retry_count = state.get("retry_count", 0)

    max_retry = config.get("max_retry_count", 3)

    if retry_count >= max_retry:
        logger.info(f"[retry_failed] 已达最大重试次数 {max_retry}")
        return {
            "current_step": "retry_failed",
            "current_node": "retry_failed",
            "retry_count": retry_count,
            "error_message": "已达最大重试次数",
        }

    try:
        llm_model = config.get("llm_model", settings.MODEL_NAME)
        retry_items = [(doi, input_dict.get(doi, {})) for doi in failed_dois if doi in input_dict]

        logger.info(f"[retry_failed] 重试 {len(retry_items)} 条失败记录")

        retry_results = _process_batch_concurrent(retry_items, prompt, llm_model, 10)

        # 更新结果
        new_success = 0
        new_failed = []

        for doi, result in retry_results.items():
            if result.get("success"):
                results_dict[doi] = result.get("data", {})
                new_success += 1
            else:
                new_failed.append(doi)

        logger.info(f"[retry_failed] 重试完成: {new_success} 成功, {len(new_failed)} 仍失败")

        return {
            "current_step": "retry_failed",
            "current_node": "retry_failed",
            "results_dict": results_dict,
            "failed_dois": new_failed,
            "retry_count": retry_count + 1,
            "error_message": "",
        }

    except Exception as e:
        logger.exception(f"[retry_failed] 重试失败")
        return {
            "current_step": "retry_failed",
            "current_node": "retry_failed",
            "retry_count": retry_count + 1,
            "error_message": f"重试失败: {str(e)}",
        }


# ============================================================================
# 导出节点
# ============================================================================

def export_result_node(state: AgentState) -> Dict:
    """导出结果节点"""
    df = state.get("original_df")
    results_dict = state.get("results_dict")
    config = state.get("config", {})
    task_id = state.get("task_id", "default")

    if results_dict is None or df is None:
        return {
            "current_step": "export_result",
            "current_node": "export_result",
            "error_message": "无结果数据",
        }

    try:
        output_folder = config.get("output_folder", "outputs")
        os.makedirs(output_folder, exist_ok=True)

        # 合并原始数据和评估结果
        result_rows = []
        dedup_field = config.get("dedup_field", "doi")

        for idx, row in df.iterrows():
            key = str(row.get(dedup_field, f"row_{idx}"))
            result_data = results_dict.get(key, {})

            merged_row = row.to_dict()
            merged_row.update(result_data)
            result_rows.append(merged_row)

        result_df = pd.DataFrame(result_rows)

        # 导出 Excel
        xlsx_path = os.path.join(output_folder, f"{task_id}_results.xlsx")
        result_df.to_excel(xlsx_path, index=False, engine="openpyxl")

        # 导出 PKL
        pkl_path = os.path.join(output_folder, f"{task_id}_results.pkl")
        with open(pkl_path, "wb") as f:
            pickle.dump({
                "df": result_df,
                "results_dict": results_dict,
                "config": config,
            }, f)

        logger.info(f"[export_result] 结果已导出: {xlsx_path}")

        return {
            "current_step": "export_result",
            "current_node": "export_result",
            "output_xlsx_path": xlsx_path,
            "output_pkl_path": pkl_path,
            "error_message": "",
        }

    except Exception as e:
        logger.exception(f"[export_result] 导出失败")
        return {
            "current_step": "export_result",
            "current_node": "export_result",
            "error_message": f"导出失败: {str(e)}",
        }


# ============================================================================
# 注册节点到字典
# ============================================================================
NODES = {
    "load_config_node": load_config_node,
    "integrate_node": integrate_node,
    "field_check_node": field_check_node,
    "data_quality_node": data_quality_node,
    "filter_node": filter_node,
    "parse_strategy_node": parse_strategy_node,
    "generate_prompt_node": generate_prompt_node,
    "use_default_prompt_node": use_default_prompt_node,
    "prepare_eval_node": prepare_eval_node,
    "batch_eval_node": batch_eval_node,
    "result_check_node": result_check_node,
    "retry_failed_node": retry_failed_node,
    "export_result_node": export_result_node,
}