"""
综合分析服务
整合 PDF → NER → RE → 技术路线 → 实验方案 → Jc → 报告 的完整流程
"""
import logging
import asyncio
import re
import json
import time
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime

from loguru import logger

from backend.app.core.config import settings
from backend.app.services.milvus_service import get_milvus_service
from backend.app.services.jc_database_service import get_jc_db_service
from backend.app.services.embedding_service import get_embedding_service, text_to_embedding
from backend.app.services.llm_service import get_llm_service


class ComprehensiveAnalysisService:
    """综合分析编排服务"""

    # 8维度名称映射（中文）
    DIM_NAMES = {
        "material_fabrication": "材料准备",
        "deposition_techniques": "沉积技术",
        "process_parameters": "工艺参数",
        "post_processing": "后处理",
        "characterization_techniques": "表征技术",
        "system_constraints": "系统约束",
        "simulation": "模拟分析",
        "irradiation": "辐照处理"
    }

    def __init__(self):
        self.milvus = get_milvus_service()
        self.jc_db = get_jc_db_service()
        self.llm = None  # 懒加载

    async def _get_llm(self):
        """懒加载LLM服务"""
        if self.llm is None:
            self.llm = await get_llm_service()
        return self.llm

    async def run_full_analysis(
        self,
        pdf_path: str,
        ner_entities: List[Dict] = None,
        re_relations: List[Dict] = None,
        pdf_content: Dict = None,
        content_text: str = None,  # 新增：原文内容用于Jc条件补充
        target_doi: str = None,
        top_k: int = 10,
        progress_callback: callable = None,
        task_id: str = None  # 新增：任务ID，用于报告文件命名
    ) -> Dict[str, Any]:
        """
        执行完整综合分析流程

        Args:
            pdf_path: PDF 文件路径
            ner_entities: NER 实体列表（可选，如已提取）
            re_relations: RE 关系列表（可选）
            pdf_content: PDF 解析内容（可选）
            content_text: 原文内容文本（用于LLM补充Jc条件参数）
            target_doi: 目标 DOI（用于Jc排名）
            top_k: 相似论文返回数量
            progress_callback: 进度回调函数

        Returns:
            综合分析结果
        """
        result = {
            "success": False,
            "message": "",
            "pdf_info": {},
            "ner_entities": [],
            "re_relations": [],
            "tech_route": {},
            "exp_scheme": {},
            "jc_analysis": {},
            "llm_comparison": "",
            "report_path": None,
            "timestamp": datetime.now().isoformat()
        }

        try:
            # Step 1-3: 并行执行技术路线、实验方案、Jc分析
            if progress_callback:
                await progress_callback("parallel_analysis", "开始并行分析（技术路线+实验方案+Jc）", 10)

            # 并行执行三个分析任务
            tech_route_task = self._analyze_tech_route(
                ner_entities=ner_entities,
                re_relations=re_relations,
                pdf_content=pdf_content,
                top_k=top_k
            )
            exp_scheme_task = self._analyze_exp_scheme(
                ner_entities=ner_entities,
                pdf_content=pdf_content,
                top_k=top_k
            )
            jc_task = self._analyze_jc(
                ner_entities=ner_entities,
                pdf_content=pdf_content,
                target_doi=target_doi,
                top_k=top_k,
                content_text=content_text,  # 传递原文用于LLM补充
            )

            # 并行等待三个分析完成
            tech_route_result, exp_scheme_result, jc_result = await asyncio.gather(
                tech_route_task, exp_scheme_task, jc_task,
                return_exceptions=True
            )

            # 处理可能的异常
            if isinstance(tech_route_result, Exception):
                logger.error(f"技术路线分析失败: {tech_route_result}")
                tech_route_result = {
                    "success": False, "message": str(tech_route_result),
                    "tech_route_text": "", "similar_papers": [], "similar_count": 0
                }
            if isinstance(exp_scheme_result, Exception):
                logger.error(f"实验方案分析失败: {exp_scheme_result}")
                exp_scheme_result = {
                    "success": False, "message": str(exp_scheme_result),
                    "exp_scheme_text": "", "dimensions": {}, "similar_papers": [], "similar_count": 0
                }
            if isinstance(jc_result, Exception):
                logger.error(f"Jc分析失败: {jc_result}")
                jc_result = {
                    "success": False, "message": str(jc_result),
                    "jc_indicators": [], "conditions": None, "database_search": {}, "ranking": {}
                }

            result["tech_route"] = tech_route_result
            result["exp_scheme"] = exp_scheme_result
            result["jc_analysis"] = jc_result

            if progress_callback:
                await progress_callback("parallel_analysis", "并行分析完成", 80)

            # Step 4: LLM 综合对比分析
            if progress_callback:
                await progress_callback("llm_comparison", "开始LLM综合分析", 85)

            llm_comparison = await self._generate_llm_comparison(
                tech_route_result=tech_route_result,
                exp_scheme_result=exp_scheme_result,
                jc_result=jc_result,
                pdf_content=pdf_content
            )
            result["llm_comparison"] = llm_comparison

            if progress_callback:
                await progress_callback("llm_comparison", "LLM综合分析完成", 95)

            # Step 5: 生成报告（三种格式）
            report_paths = await self._generate_report(result, pdf_path, task_id)
            result["report_paths"] = report_paths
            result["report_path"] = report_paths.get("markdown", "")  # 兼容旧字段

            # 检查各项分析是否成功
            tech_route_ok = tech_route_result.get("success", False)
            exp_scheme_ok = exp_scheme_result.get("success", False)
            jc_ok = jc_result.get("success", False)
            llm_ok = bool(llm_comparison)

            # 区分"全部成功"和"部分成功"
            if tech_route_ok and exp_scheme_ok and jc_ok and llm_ok:
                result["success"] = True
                result["message"] = "综合分析完成"
            elif tech_route_ok or exp_scheme_ok or jc_ok or llm_ok:
                result["success"] = True
                failed_items = []
                if not tech_route_ok:
                    failed_items.append("技术路线")
                if not exp_scheme_ok:
                    failed_items.append("实验方案")
                if not jc_ok:
                    failed_items.append("Jc指标")
                if not llm_ok:
                    failed_items.append("LLM综合分析")
                result["message"] = f"综合分析完成（{','.join(failed_items)}分析未成功）"
            else:
                result["success"] = False
                result["message"] = "综合分析完成，但所有分析项均未成功"

            if progress_callback:
                await progress_callback("complete", "分析完成", 100)

            return result

        except Exception as e:
            logger.error(f"综合分析失败: {e}")
            result["success"] = False
            result["message"] = str(e)
            if progress_callback:
                await progress_callback("error", str(e), 0)
            return result

    async def _analyze_tech_route(
        self,
        ner_entities: List[Dict],
        re_relations: List[Dict],
        pdf_content: Dict,
        top_k: int
    ) -> Dict[str, Any]:
        """
        技术路线分析

        从NER+RE构建技术路线描述，使用向量搜索对比历史论文
        """
        try:
            # 构建技术路线文本
            tech_route_text = self._build_tech_route_text(ner_entities, re_relations)

            if not tech_route_text:
                return {
                    "success": False,
                    "message": "无法构建技术路线文本",
                    "tech_route_text": "",
                    "similar_papers": []
                }

            # 生成向量
            embedding = await text_to_embedding(tech_route_text)

            if not embedding:
                return {
                    "success": False,
                    "message": "向量生成失败",
                    "tech_route_text": tech_route_text,
                    "similar_papers": []
                }

            # 搜索相似论文（过滤空文本记录，设置最低相似度阈值）
            similar_papers = self.milvus.search_similar(
                collection_name="tech_routes",
                query_vector=embedding,
                vector_field="embedding",
                top_k=top_k,
                threshold=0.5,
                filter_expr="techroute_text != \"\"",
                output_fields=["doi", "title", "techroute_text"]
            )

            return {
                "success": True,
                "message": "技术路线分析完成",
                "tech_route_text": tech_route_text,
                "similar_papers": similar_papers,
                "similar_count": len(similar_papers)
            }

        except Exception as e:
            logger.error(f"技术路线分析失败: {e}")
            return {
                "success": False,
                "message": str(e),
                "tech_route_text": "",
                "similar_papers": []
            }

    async def _analyze_exp_scheme(
        self,
        ner_entities: List[Dict],
        pdf_content: Dict,
        top_k: int
    ) -> Dict[str, Any]:
        """
        实验方案分析

        8维度实验方案提取，使用向量搜索对比
        """
        try:
            # 构建8维度实验方案文本
            exp_scheme_text = self._build_exp_scheme_text(ner_entities, pdf_content)

            if not exp_scheme_text:
                return {
                    "success": False,
                    "message": "无法构建实验方案文本",
                    "exp_scheme_text": "",
                    "dimensions": {},
                    "similar_papers": []
                }

            # 生成向量
            embedding = await text_to_embedding(exp_scheme_text)

            if not embedding:
                return {
                    "success": False,
                    "message": "向量生成失败",
                    "exp_scheme_text": exp_scheme_text,
                    "dimensions": {},
                    "similar_papers": []
                }

            # 搜索相似论文（过滤空文本记录，设置最低相似度阈值）
            similar_papers = self.milvus.search_similar(
                collection_name="exp_schemes",
                query_vector=embedding,
                vector_field="embedding",
                top_k=top_k,
                threshold=0.5,
                filter_expr="expscheme_text != \"\"",
                output_fields=["doi", "title", "expscheme_text", "categories_json"]
            )

            # 解析维度
            dimensions = self._parse_dimensions(ner_entities)

            return {
                "success": True,
                "message": "实验方案分析完成",
                "exp_scheme_text": exp_scheme_text,
                "dimensions": dimensions,
                "similar_papers": similar_papers,
                "similar_count": len(similar_papers)
            }

        except Exception as e:
            logger.error(f"实验方案分析失败: {e}")
            return {
                "success": False,
                "message": str(e),
                "exp_scheme_text": "",
                "dimensions": {},
                "similar_papers": []
            }

    async def _analyze_jc(
        self,
        ner_entities: List[Dict],
        pdf_content: Dict,
        target_doi: str,
        top_k: int,
        content_text: str = None,  # 新增：原文内容
    ) -> Dict[str, Any]:
        """
        Jc 指标分析

        提取Jc指标，搜索历史数据，计算排名
        改进：正确过滤异常值，利用原文补充条件参数
        """
        try:
            # 提取Jc条件（改进版）
            jc_conditions = self._extract_jc_conditions_improved(ner_entities, pdf_content)

            if not jc_conditions.get("jc_indicators"):
                return {
                    "success": False,
                    "message": "未找到Jc指标数据",
                    "jc_indicators": [],
                    "conditions": None,
                    "database_search": {},
                    "ranking": {}
                }

            # 检查是否需要LLM补充条件参数
            jc_indicators = jc_conditions.get("jc_indicators", [])
            incomplete_jc = [jc for jc in jc_indicators
                            if jc.get("temperature") is None or jc.get("magnetic_field") is None]

            if incomplete_jc and content_text:
                # LLM补充缺失的条件参数
                jc_indicators = await self._supplement_jc_conditions_with_llm(
                    jc_indicators, content_text
                )
                jc_conditions["jc_indicators"] = jc_indicators

            # 搜索历史数据
            db_search_result = await self.jc_db.search_by_conditions(
                temperature=jc_conditions.get("temperature"),
                magnetic_field=jc_conditions.get("magnetic_field"),
                angle=jc_conditions.get("angle"),
                top_k=top_k
            )

            # 如果有目标DOI，计算排名
            ranking_result = {}
            if target_doi:
                ranking_result = await self.jc_db.rank_by_doi(
                    target_doi=target_doi,
                    temperature=jc_conditions.get("temperature"),
                    magnetic_field=jc_conditions.get("magnetic_field"),
                    angle=jc_conditions.get("angle")
                )

            return {
                "success": True,
                "message": "Jc指标分析完成",
                "jc_indicators": jc_conditions.get("jc_indicators", []),
                "conditions": {
                    "temperature": jc_conditions.get("temperature"),
                    "magnetic_field": jc_conditions.get("magnetic_field"),
                    "angle": jc_conditions.get("angle")
                },
                "database_search": db_search_result,
                "ranking": ranking_result
            }

        except Exception as e:
            logger.error(f"Jc分析失败: {e}")
            return {
                "success": False,
                "message": str(e),
                "jc_indicators": [],
                "conditions": None,
                "database_search": {},
                "ranking": {}
            }

    async def _generate_llm_comparison(
        self,
        tech_route_result: Dict,
        exp_scheme_result: Dict,
        jc_result: Dict,
        pdf_content: Dict
    ) -> str:
        """
        LLM生成综合对比分析报告
        """
        try:
            # 构建prompt
            prompt = self._build_comparison_prompt(
                tech_route_result,
                exp_scheme_result,
                jc_result,
                pdf_content
            )

            # 调用LLM（生成Markdown报告，不需要JSON模式）
            llm = await self._get_llm()
            response = await llm.chat(prompt, json_mode=False)

            return response or ""

        except Exception as e:
            logger.error(f"LLM对比分析失败: {e}")
            return ""

    async def _generate_report(
        self,
        result: Dict[str, Any],
        pdf_path: str,
        task_id: str = None
    ) -> Dict[str, str]:
        """
        生成综合分析报告（Markdown、Excel、PDF三种格式）

        Args:
            result: 分析结果
            pdf_path: PDF 文件路径
            task_id: 任务ID，用于报告文件命名（如不提供则自动生成）

        Returns:
            {'markdown': path, 'excel': path, 'pdf': path}
        """
        try:
            from backend.app.services.report_service import get_report_service

            # 创建报告目录
            from backend.app.core.config import RESULTS_DIR
            report_dir = Path(RESULTS_DIR) / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)

            # 使用 task_id 作为文件名基础（优先使用传入的 task_id）
            if not task_id:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_name = Path(pdf_path).stem if pdf_path else "unknown"
                task_id = f"{pdf_name}_{timestamp}"

            # 使用 ReportService 生成多种格式报告
            report_service = get_report_service(str(report_dir))

            report_paths = {}

            # 生成 Markdown 报告
            try:
                md_path = report_service.generate_markdown_report(result, task_id)
                report_paths['markdown'] = md_path
                logger.info(f"Markdown 报告生成成功: {md_path}")
            except Exception as e:
                logger.warning(f"Markdown 报告生成失败: {e}")
                report_paths['markdown'] = ""

            # 生成 Excel 报告
            try:
                excel_path = report_service.generate_excel_report(result, task_id)
                report_paths['excel'] = excel_path
                logger.info(f"Excel 报告生成成功: {excel_path}")
            except Exception as e:
                logger.warning(f"Excel 报告生成失败: {e}")
                report_paths['excel'] = ""

            # 生成 PDF 报告
            try:
                pdf_path = report_service.generate_pdf_report(result, task_id)
                report_paths['pdf'] = pdf_path
                logger.info(f"PDF 报告生成成功: {pdf_path}")
            except Exception as e:
                logger.warning(f"PDF 报告生成失败: {e}")
                report_paths['pdf'] = ""

            return report_paths

        except Exception as e:
            logger.error(f"报告生成失败: {e}")
            return {'markdown': '', 'excel': '', 'pdf': ''}

    def _build_tech_route_text(self, entities: List[Dict], relations: List[Dict]) -> str:
        """
        构建技术路线文本 - 改进版

        改进：
        1. 区分核心材料、基底、工艺、参数、性能
        2. 仅提取关键实体，避免冗余
        3. 利用RE关系构建实体关系链
        """
        if not entities:
            return ""

        # 分类提取关键实体
        materials = []      # 核心材料（化合物名称）
        substrates = []     # 基底材料
        processes = []      # 工艺方法
        parameters = []     # 工艺参数（数值型）
        performances = []   # 性能指标（Jc, Tc等）

        # 参数类符号（厚度、温度、压力等）
        PARAM_SYMBOLS = [
            "Film_Thickness", "Film_Height", "Film_Dimensions", "Thickness",
            "Growth_Rate", "Deposition_Rate", "Repetition_Rate", "Energy_Density",
            "Substrate_Temperature", "Total_Pressure", "Wavelength"
        ]

        # 性能指标符号
        PERFORMANCE_SYMBOLS = ["Jc", "J_c", "Tc", "T_c", "B_irr", "Birr"]

        # 基底符号
        SUBSTRATE_SYMBOLS = ["LSAT", "LaAlO3", "SrTiO3", "STO", "NdGaO3", "NGO", "Substrate"]

        for entity in entities:
            entity_type = entity.get("type", entity.get("entity_type", ""))
            entity_text = entity.get("symbol", entity.get("entity_text", ""))
            if not entity_text and entity.get("value"):
                entity_text = str(entity.get("value"))
            subtype = entity.get("subtype", "")

            # 跳过参数符号（除非有具体数值）
            if entity_text in PARAM_SYMBOLS:
                # 如果有具体数值，加入参数
                value = entity.get("value")
                unit = entity.get("unit", "")
                if value is not None:
                    try:
                        v = float(value) if not isinstance(value, list) else (value[0] if value else None)
                        if v is not None:
                            parameters.append(f"{entity_text}: {v}{unit}")
                    except:
                        pass
                continue

            # 性能指标单独处理
            if entity_text in PERFORMANCE_SYMBOLS:
                value = entity.get("value")
                unit = entity.get("unit", "")
                if value is not None:
                    performances.append(f"{entity_text}: {value}{unit}")
                continue

            # 基底材料
            if entity_text in SUBSTRATE_SYMBOLS or entity_type == "Substrate":
                substrates.append(entity_text)
                continue

            # 核心材料（化合物名称）
            if entity_type in ["Material", "Chemical_Formula"] or subtype in ["Material_Identification", "Chemical_Formula"]:
                # 排除参数类、基底类、变量名（单个字母）
                if entity_text not in PARAM_SYMBOLS and entity_text not in SUBSTRATE_SYMBOLS:
                    # 排除单字符变量名（如a, b, t等）
                    if len(entity_text) > 1 or entity_text.lower() not in ["a", "b", "c", "t", "x", "y", "z", "n", "m"]:
                        materials.append(entity_text)

            # 工艺方法
            elif entity_type in ["Manufacturing_Process_Chain", "Deposition"] or subtype in ["Deposition_Techniques"]:
                if entity_text not in ["Deposition", "PVD"]:  # 避免太通用的词
                    processes.append(entity_text)
                elif entity_text == "PVD":
                    processes.append("PVD")

            # 其他数值型参数
            elif entity_type in ["Process_Params", "Temperature", "Pressure"]:
                value = entity.get("value")
                unit = entity.get("unit", "")
                if value is not None and entity_text not in PERFORMANCE_SYMBOLS:
                    try:
                        v = float(value) if not isinstance(value, list) else (value[0] if value else None)
                        if v is not None:
                            parameters.append(f"{entity_text}: {v}{unit}")
                    except:
                        pass

        # 构建关系链（利用RE数据）
        relation_chains = []
        if relations:
            for relation in relations[:10]:  # 最多10条关键关系
                source = relation.get("source_entity", "")
                target = relation.get("target_entity", "")
                if source and target:
                    relation_chains.append(f"{source} → {target}")

        # 构建技术路线文本
        parts = []
        if materials:
            # 去重并取前5个
            unique_materials = list(set(materials))[:5]
            parts.append(f"材料: {', '.join(unique_materials)}")
        if substrates:
            unique_substrates = list(set(substrates))[:3]
            parts.append(f"基底: {', '.join(unique_substrates)}")
        if processes:
            unique_processes = list(set(processes))[:5]
            parts.append(f"工艺: {', '.join(unique_processes)}")
        if parameters:
            parts.append(f"参数: {', '.join(parameters[:5])}")
        if performances:
            parts.append(f"性能: {', '.join(performances[:3])}")

        # 添加关系链描述
        if relation_chains:
            parts.append(f"关键路径: {'; '.join(relation_chains[:5])}")

        return "; ".join(parts) if parts else ""

    def _build_exp_scheme_text(self, entities: List[Dict], pdf_content: Dict) -> str:
        """
        构建实验方案文本（8维度） - 改进版

        使用完整的8维度分类映射，与_parse_dimensions保持一致
        """
        if not entities:
            return ""

        # 使用改进的8维度分类
        dimensions = self._parse_dimensions(entities)

        # 构建文本
        parts = []
        for dim_key, values in dimensions.items():
            if values:
                dim_name = self.DIM_NAMES.get(dim_key, dim_key)
                parts.append(f"{dim_name}: {', '.join(values[:3])}")

        return "; ".join(parts) if parts else ""

    def _parse_dimensions(self, entities: List[Dict]) -> Dict[str, List]:
        """
        解析完整8维度 - 参考V2的ExpSchemeRetriever（改进版）

        8维度分类映射：
        1. material_fabrication: Material, Material_Identification, Chemical_Formula, Crystal_Characteristics, Phase_Composition
        2. deposition_techniques: Manufacturing_Process_Chain, Deposition, Deposition_Techniques
        3. process_parameters: Process_Params, Temperature(数值), Pressure, Film_Thickness(数值), Dimensional_Control
        4. post_processing: Post-Processing, Oxygenation
        5. characterization_techniques: Characterization, Measurement, XRD, SEM, TEM, AFM
        6. system_constraints: Substrate, Substrate_Specification, System_Constraints
        7. simulation: Simulation
        8. irradiation: Irradiation

        改进：
        - Jc/Tc等性能指标不归入8维度（单独处理）
        - Film_Thickness等尺寸参数归入工艺参数
        - 更精确的subtype/type映射
        """
        dimensions = {
            "material_fabrication": [],
            "deposition_techniques": [],
            "process_parameters": [],
            "post_processing": [],
            "characterization_techniques": [],
            "system_constraints": [],
            "simulation": [],
            "irradiation": []
        }

        # 性能指标符号（不归入8维度）
        PERFORMANCE_SYMBOLS = ["Jc", "J_c", "Tc", "T_c", "B_irr", "Birr", "B_acc"]

        # V2的SUBTYPE映射
        SUBTYPE_MAPPING = {
            'Material_Fabrication': 'material_fabrication',
            'Material_Identification': 'material_fabrication',
            'Chemical_Formula': 'material_fabrication',
            'Crystal_Characteristics': 'material_fabrication',
            'Phase_Composition': 'material_fabrication',
            'Defect_Network': 'material_fabrication',  # 缺陷网络属于材料结构

            'Deposition_Techniques': 'deposition_techniques',
            'Target_Deposition': 'deposition_techniques',
            'Secondary_Seeding': 'deposition_techniques',

            'Process_Parameters': 'process_parameters',
            'Dimensional_Control': 'process_parameters',  # 尺寸控制归入工艺参数
            'Temperature': 'process_parameters',

            'Post-Processing': 'post_processing',
            'Oxygenation': 'post_processing',

            'Characterization_Techniques': 'characterization_techniques',

            'System_Constraints': 'system_constraints',
            'Substrate_Specification': 'system_constraints',

            'Simulation': 'simulation',
            'Irradiation': 'irradiation'
        }

        # 类型映射（备用）- 更精确
        TYPE_MAPPING = {
            "Material": "material_fabrication",
            "Chemical_Formula": "material_fabrication",

            "Manufacturing_Process_Chain": "deposition_techniques",
            "Deposition": "deposition_techniques",

            "Process_Params": "process_parameters",
            "Pressure": "process_parameters",

            "Characterization": "characterization_techniques",
            "Measurement": "characterization_techniques",

            "Substrate": "system_constraints"
        }

        for entity in entities:
            entity_type = entity.get("type", entity.get("entity_type", ""))
            entity_text = entity.get("symbol", entity.get("entity_text", ""))
            if not entity_text and entity.get("value"):
                entity_text = str(entity.get("value"))
            subtype = entity.get("subtype", "")

            # 跳过性能指标（Jc, Tc等）
            if entity_text in PERFORMANCE_SYMBOLS:
                continue

            # Microstructural_Hierarchy特殊处理
            if entity_type == "Microstructural_Hierarchy":
                # 尺寸参数归入工艺参数
                if subtype in ["Dimensional_Control"] or entity_text in ["Film_Thickness", "Film_Height", "Film_Dimensions", "Thickness"]:
                    dim_key = "process_parameters"
                else:
                    # 其他微结构参数归入材料准备
                    dim_key = "material_fabrication"
            else:
                # 优先使用subtype映射
                dim_key = None
                if subtype in SUBTYPE_MAPPING:
                    dim_key = SUBTYPE_MAPPING[subtype]
                elif entity_type in TYPE_MAPPING:
                    dim_key = TYPE_MAPPING[entity_type]

            if dim_key and entity_text:
                # 提取参数值（如果有）
                params = entity.get("parameters", [])
                if params:
                    param_strs = []
                    for p in params:
                        p_type = p.get("type", "")
                        p_value = p.get("value")
                        p_unit = p.get("unit", "")
                        if p_value is not None:
                            # 处理list类型的value
                            if isinstance(p_value, list):
                                p_value = str(p_value[0]) if p_value else ""
                            else:
                                p_value = str(p_value)
                            if p_value:
                                param_strs.append(f"{p_type}: {p_value}{p_unit}")
                    if param_strs:
                        entity_text = f"{entity_text} ({', '.join(param_strs)})"

                dimensions[dim_key].append(entity_text)

        return dimensions

    def _extract_jc_conditions_improved(
        self,
        entities: List[Dict],
        pdf_content: Dict
    ) -> Dict[str, Any]:
        """
        改进的Jc条件和值提取

        改进点：
        1. 正确过滤异常值（负值、零值）
        2. 从parameters字段提取条件参数
        3. 支持多种Jc实体识别方式
        """
        jc_indicators = []
        temperature = None
        magnetic_field = None
        angle = None

        for entity in entities:
            entity_type = entity.get("type", entity.get("entity_type", ""))
            entity_text = entity.get("symbol", entity.get("entity_text", ""))
            if not entity_text and entity.get("value"):
                entity_text = str(entity.get("value"))
            subtype = entity.get("subtype", "")

            # 非Jc符号列表（排除磁场、温度、系数等参数）
            NON_JC_SYMBOLS = [
                "B_acc", "B_irr", "Birr", "B", "T", "a", "b",  # 磁场/温度/系数
                "Tc", "Tc_shift", "Temperature",  # 温度参数
                "Growth_Rate", "Deposition_Rate",  # 工艺参数
                "Field_Dependence_Coefficient", "Power_Law_Coefficient"
            ]

            # 检查是否是真正的Jc实体（更严格）
            is_jc_entity = False

            # 首先排除已知非Jc符号
            if entity_text in NON_JC_SYMBOLS or entity.get("symbol") in NON_JC_SYMBOLS:
                continue

            # 严格识别Jc
            # 方式1: subtype明确是Jc
            if subtype in ["Jc_Value", "Critical_Current_Density"]:
                is_jc_entity = True
            # 方式2: entity_text/symbol明确包含Jc
            elif entity_text and entity_text.lower() in ["jc", "j_c", "j_c(b)", "j_c(0)"]:
                is_jc_entity = True
            # 方式3: entity_text包含Jc且有数值
            elif entity_text and "jc" in entity_text.lower() and entity.get("value") is not None:
                # 验证是否是Jc的表达式（如"Jc = xxx"）
                is_jc_entity = True
            # 方式4: type是Jc/Critical_Current（但要排除其他Transport_Behavior）
            elif entity_type in ["Jc", "Critical_Current"] and subtype not in ["Temperature", "Magnetic_Field"]:
                is_jc_entity = True

            if is_jc_entity:
                # 从 value 字段获取数值（优先）
                jc_value = None
                unit = entity.get("unit", "A/cm²")

                # 方式1: 直接从value字段
                raw_value = entity.get("value")
                if raw_value is not None:
                    try:
                        jc_float = float(raw_value)
                        # Jc值合理范围验证：
                        # - A/cm²单位: 1e3 ~ 1e8 (1000 ~ 100,000,000)
                        # - MA/cm²单位: 0.001 ~ 100 (转换为A/cm²: 1e3 ~ 1e8)
                        # - kA/cm²单位: 1 ~ 1e5 (转换为A/cm²: 1e3 ~ 1e8)
                        # 过滤：负值、零值、过小值(<1000 A/cm²可能是其他参数)
                        # 也过滤过小值<0.001可能是单位错误或非Jc值
                        if jc_float > 0.001:
                            # 根据单位判断合理范围
                            if unit in ["MA/cm²", "MA/cm2"]:
                                # MA/cm²: 合理范围 0.001 ~ 100
                                if 0.001 <= jc_float <= 100:
                                    jc_value = jc_float * 1e6  # 转换为A/cm²
                                    unit = "A/cm²"
                                elif jc_float > 100:
                                    # 可能单位是A/cm²但标记为MA
                                    jc_value = jc_float
                            elif unit in ["kA/cm²", "kA/cm2"]:
                                # kA/cm²: 合理范围 1 ~ 1e5
                                if 1 <= jc_float <= 1e5:
                                    jc_value = jc_float * 1000  # 转换为A/cm²
                                    unit = "A/cm²"
                            else:
                                # A/cm²: 合理范围 1e3 ~ 1e8
                                if 1e3 <= jc_float <= 1e8:
                                    jc_value = jc_float
                                elif jc_float > 1e8:
                                    # 可能单位错了，也接受
                                    jc_value = jc_float
                    except (ValueError, TypeError):
                        pass

                # 方式2: 从entity_text解析数值
                if jc_value is None and entity_text:
                    # 提取数字部分
                    numbers = re.findall(r'[\d.]+(?:e[+-]?\d+)?', entity_text)
                    if numbers:
                        try:
                            jc_float = float(numbers[0])
                            if jc_float > 0.001:
                                jc_value = jc_float
                        except ValueError:
                            pass

                if jc_value is not None:
                    # 提取单位
                    unit = entity.get("unit", "A/cm²")
                    if not unit or unit == "":
                        # 从entity_text推断单位
                        if "MA/cm" in entity_text or "MA" in entity_text:
                            unit = "MA/cm²"
                        elif "kA/cm" in entity_text or "kA" in entity_text:
                            unit = "kA/cm²"
                        else:
                            unit = "A/cm²"

                    # 提取条件参数（温度、磁场、角度）
                    params = entity.get("parameters", [])
                    jc_temp = None
                    jc_field = None
                    jc_angle = None

                    for p in params:
                        p_type = p.get("type", "").lower()
                        p_value = p.get("value")
                        # p_value可能是list、dict或其他类型，需要处理
                        if p_value is not None:
                            try:
                                # 如果是list，取第一个元素
                                if isinstance(p_value, list):
                                    p_value = p_value[0] if p_value else None
                                if p_value is not None:
                                    p_float = float(p_value)
                                    if p_type in ["temp", "temperature", "t"]:
                                        jc_temp = p_float
                                    elif p_type in ["field", "magnetic_field", "b"]:
                                        jc_field = p_float
                                    elif p_type in ["angle", "theta"]:
                                        jc_angle = p_float
                            except (ValueError, TypeError):
                                pass

                    # 同时检查condition字段（真实数据格式）
                    condition = entity.get("condition", {})
                    if condition:
                        temp_val = condition.get("temp")
                        field_val = condition.get("field")
                        if temp_val is not None:
                            if isinstance(temp_val, list):
                                temp_val = temp_val[0] if temp_val else None
                            if temp_val is not None and jc_temp is None:
                                try:
                                    jc_temp = float(temp_val)
                                except (ValueError, TypeError):
                                    pass
                        if field_val is not None:
                            if isinstance(field_val, list):
                                field_val = field_val[0] if field_val else None
                            if field_val is not None and jc_field is None:
                                try:
                                    jc_field = float(field_val)
                                except (ValueError, TypeError):
                                    pass

                    jc_indicators.append({
                        "jc_value": jc_value,
                        "entity_text": entity_text,
                        "unit": unit,
                        "temperature": jc_temp,
                        "magnetic_field": jc_field,
                        "angle": jc_angle
                    })

                    # 更新全局条件参数（取第一个有效值）
                    if temperature is None and jc_temp is not None:
                        temperature = jc_temp
                    if magnetic_field is None and jc_field is not None:
                        magnetic_field = jc_field
                    if angle is None and jc_angle is not None:
                        angle = jc_angle

            # 单独的温度实体
            elif entity_type in ["Temperature"] or subtype in ["Temperature", "temp"]:
                params = entity.get("parameters", [])
                for p in params:
                    if p.get("type") in ["temp", "temperature", "T"]:
                        try:
                            temp_val = p.get("value")
                            if temp_val:
                                temperature = float(temp_val)
                        except:
                            pass
                if not temperature and entity_text:
                    try:
                        temperature = float(entity_text.replace("K", "").replace("k", "").strip())
                    except:
                        pass

            # 单独的磁场实体
            elif entity_type in ["Magnetic_Field", "Field"] or subtype in ["Magnetic_Field", "field"]:
                params = entity.get("parameters", [])
                for p in params:
                    if p.get("type") in ["field", "magnetic_field", "B"]:
                        try:
                            field_val = p.get("value")
                            if field_val:
                                magnetic_field = float(field_val)
                        except:
                            pass
                if not magnetic_field and entity_text:
                    try:
                        magnetic_field = float(entity_text.replace("T", "").replace("t", "").strip())
                    except:
                        pass

            # 单独的角度实体
            elif entity_type in ["Angle"] or subtype in ["Angle", "angle"]:
                if entity_text:
                    try:
                        angle = float(entity_text.replace("deg", "").replace("°", "").strip())
                    except:
                        pass

        logger.info(f"[Jc提取改进] 找到 {len(jc_indicators)} 个有效Jc指标")
        if jc_indicators:
            logger.info(f"[Jc提取改进] Jc值范围: {min(j['jc_value'] for j in jc_indicators):.2f} - {max(j['jc_value'] for j in jc_indicators):.2f}")

        return {
            "jc_indicators": jc_indicators,
            "temperature": temperature,
            "magnetic_field": magnetic_field,
            "angle": angle
        }

    async def _supplement_jc_conditions_with_llm(
        self,
        jc_indicators: List[Dict],
        content_text: str
    ) -> List[Dict]:
        """
        使用LLM从原文补充Jc条件参数

        参考：V2的JcService._supplement_conditions_with_llm()
        """
        if not content_text or not jc_indicators:
            return jc_indicators

        # 找出缺失条件的Jc指标
        incomplete_jc = [jc for jc in jc_indicators
                        if jc.get("temperature") is None or jc.get("magnetic_field") is None]

        if not incomplete_jc:
            logger.info("[LLM补充] 所有Jc指标已包含条件参数，无需补充")
            return jc_indicators

        logger.info(f"[LLM补充] 需补充 {len(incomplete_jc)} 个Jc指标的条件参数")

        try:
            llm = await self._get_llm()

            # 批量处理：一次LLM调用补充所有缺失条件
            jc_values_str = ", ".join([f"{jc['jc_value']} {jc.get('unit', 'A/cm²')}"
                                       for jc in incomplete_jc[:5]])  # 最多5个

            prompt = f"""从以下原文中提取Jc（临界电流密度）测量的条件参数。

Jc值列表: {jc_values_str}

原文内容:
{content_text[:3000]}

请提取每个Jc值对应的：
1. 测试温度 (temperature, 单位K)
2. 磁场强度 (magnetic_field, 单位T)
3. 测试角度 (angle, 单位deg，如无明确提及则为0)

请以JSON格式返回，格式如下：
{
    "conditions": [
        {"jc_value": xxx, "temperature": xxx, "magnetic_field": xxx, "angle": xxx},
        ...
    ]
}

如果原文中未明确提及某个条件参数，请根据上下文推断或使用常见值：
- 温度默认: 77K (液氮温度) 或 65K
- 磁场默认: 0T (自场) 或根据上下文
- 角度默认: 0deg
"""

            response = await llm.chat(prompt, json_mode=True)

            if response:
                # 解析LLM返回的条件参数
                try:
                    result = json.loads(response) if isinstance(response, str) else response
                    llm_conditions = result.get("conditions", [])

                    # 匹配并更新Jc指标
                    for llm_cond in llm_conditions:
                        llm_jc_val = llm_cond.get("jc_value")
                        if llm_jc_val is None:
                            continue
                        for jc in jc_indicators:
                            # 数值近似匹配（考虑浮点精度）
                            if jc.get("jc_value") and abs(jc["jc_value"] - llm_jc_val) < jc["jc_value"] * 0.01:
                                if jc.get("temperature") is None:
                                    jc["temperature"] = llm_cond.get("temperature")
                                if jc.get("magnetic_field") is None:
                                    jc["magnetic_field"] = llm_cond.get("magnetic_field")
                                if jc.get("angle") is None:
                                    jc["angle"] = llm_cond.get("angle", 0)
                                break

                    logger.info(f"[LLM补充] 成功补充 {len(llm_conditions)} 个条件参数")

                except json.JSONDecodeError as e:
                    logger.warning(f"[LLM补充] JSON解析失败: {e}")

        except Exception as e:
            logger.error(f"[LLM补充] 失败: {e}")

        return jc_indicators

    def _build_comparison_prompt(
        self,
        tech_route_result: Dict,
        exp_scheme_result: Dict,
        jc_result: Dict,
        pdf_content: Dict
    ) -> str:
        """
        构建详细LLM对比分析Prompt - 参考V2深度推理模块

        改进：
        1. 添加完整的8维度对比分析要求
        2. 包含相似论文的详细信息
        3. 添加技术趋势分析要求
        """
        prompt = """你是超导材料领域的专家，请基于以下分析结果生成一份详细的综合对比分析报告。

## 目标论文信息
"""
        # 添加PDF基本信息
        doi = pdf_content.get("doi", "N/A")
        title = pdf_content.get("title", "N/A")
        prompt += f"- DOI: {doi}\n"
        prompt += f"- 标题: {title}\n\n"

        # 技术路线分析结果
        prompt += "## 1. 技术路线分析结果\n\n"
        tech_route_text = tech_route_result.get('tech_route_text', 'N/A')
        prompt += f"**技术路线描述**: {tech_route_text}\n\n"

        similar_papers = tech_route_result.get('similar_papers', [])
        prompt += f"**相似论文数量**: {tech_route_result.get('similar_count', 0)}\n\n"

        if similar_papers:
            prompt += "**相似论文列表**:\n\n"
            prompt += "| 序号 | DOI | 标题 | 相似度 |\n"
            prompt += "|------|-----|------|--------|\n"
            for i, paper in enumerate(similar_papers[:10]):
                paper_doi = paper.get('doi', 'N/A')
                paper_title = paper.get('title', 'N/A')[:40]
                score = paper.get('score', 0)
                prompt += f"| {i+1} | {paper_doi} | {paper_title} | {score:.3f} |\n"
            prompt += "\n"

        # 实验方案分析结果（8维度）
        prompt += "## 2. 实验方案分析结果\n\n"
        exp_scheme_text = exp_scheme_result.get('exp_scheme_text', 'N/A')
        prompt += f"**实验方案描述**: {exp_scheme_text}\n\n"

        dimensions = exp_scheme_result.get('dimensions', {})
        prompt += "**8维度分析**:\n\n"
        for dim_key, values in dimensions.items():
            if values:
                prompt += f"- **{self.DIM_NAMES.get(dim_key, dim_key)}**: {', '.join(values[:5])}\n"
        prompt += "\n"

        # Jc指标分析结果
        prompt += "## 3. Jc指标分析结果\n\n"
        jc_indicators = jc_result.get('jc_indicators', [])
        if jc_indicators:
            prompt += "**Jc值列表**:\n\n"
            for jc in jc_indicators[:5]:
                jc_val = jc.get('jc_value', 'N/A')
                unit = jc.get('unit', 'A/cm²')
                temp = jc.get('temperature', 'N/A')
                field = jc.get('magnetic_field', 'N/A')
                prompt += f"- {jc_val} {unit} (温度: {temp}K, 磁场: {field}T)\n"
            prompt += "\n"

        ranking = jc_result.get('ranking', {})
        if ranking.get('success'):
            prompt += "**排名分析**:\n\n"
            prompt += f"- 目标DOI: {ranking.get('target_doi', 'N/A')}\n"
            prompt += f"- 目标Jc最大值: {ranking.get('target_jc_max', 'N/A')} A/cm²\n"
            prompt += f"- 排名: 第{ranking.get('target_rank', 'N/A')}名 / 共{ranking.get('total_papers', 0)}篇论文\n"
            percentile = ranking.get('rank_percentile')
            if percentile is not None:
                prompt += f"- 百分位: {percentile}（前{100-percentile*100:.1f}%）\n\n"
            else:
                prompt += "- 百分位: N/A\n\n"

        # 详细对比分析要求
        prompt += """## 4. 请进行以下详细对比分析

### 4.1 技术路线对比
请分析目标论文与相似论文在技术路线上的异同点，包括：
- 材料选择差异
- 工艺流程差异
- 关键技术路径差异

### 4.2 实验方案对比（8个维度）

请分别从以下8个维度分析目标论文与相似论文在实验方案上的异同点：

1. **材料准备**: 原材料选择、预处理、合成方法
2. **沉积技术**: 薄膜沉积方法（CVD, PLD, MOD, Sputtering等）
3. **工艺参数**: 温度、时间、气氛、压力等参数设置
4. **后处理**: 热处理、退火、轧制等后处理工艺
5. **表征技术**: 使用的测试和表征方法（XRD, SEM, TEM等）
6. **系统约束**: 设备限制、基底选择、架构设计
7. **模拟分析**: 理论计算和模拟研究
8. **辐照处理**: 粒子辐照、掺杂等特殊处理

### 4.3 Jc性能对比
请分析目标论文的Jc性能表现：
- 与相似论文的性能差距分析
- 高性能原因分析（如工艺优势、材料优势）
- 性能优化潜力评估

### 4.4 关键差异总结
请总结目标论文与最相似论文的关键差异，以及该差异对性能的影响。

### 4.5 技术趋势分析
基于对比结果，请分析该领域的技术发展趋势，包括：
- 主流技术路线演变
- 性能提升的关键因素
- 未来研究方向建议

---

请以专业学术论文风格撰写分析报告，使用Markdown格式输出。

**格式要求：**
- 报告开头只需列出DOI和标题
- 不要添加"分析日期"、"日期"、"报告撰写人"等任何日期或元信息字段
- 不要推断或添加论文发表日期、撰写日期等任何日期信息
- 直接开始正文内容，无需额外的报告头部信息"""
        return prompt

    def _build_markdown_report(self, result: Dict[str, Any]) -> str:
        """
        构建Markdown报告 - 改进版

        改进：
        1. Jc值输出包含条件参数
        2. 8维度使用中文名称
        3. 技术路线包含关键路径
        """
        # 构建报告内容
        report = f"""# 综合分析报告

## 1. 分析概述

- 分析时间: {result.get('timestamp', 'N/A')}
- 分析状态: {'成功' if result.get('success', False) else '失败'}
- 消息: {result.get('message', '')}

## 2. 技术路线分析

### 2.1 技术路线描述

{result.get('tech_route', {}).get('tech_route_text', 'N/A')}

### 2.2 相似论文对比

"""
        similar_papers = result.get('tech_route', {}).get('similar_papers', [])
        if similar_papers:
            report += "| 序号 | DOI | 标题 | 相似度 |\n"
            report += "|------|-----|------|--------|\n"
            for i, paper in enumerate(similar_papers[:10]):
                doi = paper.get('doi', 'N/A')
                title = paper.get('title', 'N/A')[:50]
                score = paper.get('score', 0)
                report += f"| {i+1} | {doi} | {title} | {score:.3f} |\n"
        else:
            report += "无相似论文数据\n"

        report += "\n## 3. 实验方案分析\n\n"
        exp_scheme = result.get('exp_scheme', {})
        exp_scheme_text = exp_scheme.get('exp_scheme_text', 'N/A')
        report += f"### 3.1 实验方案描述\n\n{exp_scheme_text}\n\n"

        report += "### 3.2 8维度分析\n\n"
        dimensions = exp_scheme.get('dimensions', {})
        for dim_key, values in dimensions.items():
            if values:
                dim_name = self.DIM_NAMES.get(dim_key, dim_key)
                report += f"- **{dim_name}**: {', '.join(values)}\n"

        report += "\n## 4. Jc指标分析\n\n"
        jc_analysis = result.get('jc_analysis', {})
        jc_indicators = jc_analysis.get('jc_indicators', [])
        if jc_indicators:
            report += "### 4.1 Jc值\n\n"
            report += "| Jc值 | 单位 | 温度(K) | 磁场(T) | 角度(deg) |\n"
            report += "|------|------|---------|---------|----------|\n"
            for jc in jc_indicators[:10]:
                jc_val = jc.get('jc_value', 'N/A')
                unit = jc.get('unit', 'A/cm²')
                temp = jc.get('temperature', 'N/A')
                field = jc.get('magnetic_field', 'N/A')
                angle = jc.get('angle', 'N/A')
                jc_str = f"{jc_val:.2e}" if isinstance(jc_val, (int, float)) else str(jc_val)
                report += f"| {jc_str} | {unit} | {temp} | {field} | {angle} |\n"

        ranking = jc_analysis.get('ranking', {})
        if ranking.get('success'):
            report += f"\n### 4.2 排名分析\n\n"
            report += f"- 目标DOI: {ranking.get('target_doi', 'N/A')}\n"
            report += f"- 目标Jc最大值: {ranking.get('target_jc_max', 'N/A')} A/cm²\n"
            report += f"- 排名: 第{ranking.get('target_rank', 'N/A')}名 / 共{ranking.get('total_papers', 0)}篇论文\n"
            percentile = ranking.get('rank_percentile')
            if percentile is not None:
                report += f"- 百分位: {percentile}（前{100-percentile*100:.1f}%）\n"

        report += "\n## 5. LLM综合分析\n\n"
        llm_comparison = result.get('llm_comparison', '')
        if llm_comparison:
            report += llm_comparison
        else:
            report += "无LLM分析结果\n"

        report += "\n## 6. 结论\n\n"
        if result.get('success'):
            report += "综合分析完成，详细结果见上述各部分。\n"
        else:
            report += f"综合分析失败: {result.get('message', '未知错误')}\n"

        return report


# 全局服务实例
_comprehensive_service: Optional[ComprehensiveAnalysisService] = None


def get_comprehensive_service() -> ComprehensiveAnalysisService:
    """获取综合分析服务实例"""
    global _comprehensive_service
    if _comprehensive_service is None:
        _comprehensive_service = ComprehensiveAnalysisService()
    return _comprehensive_service