# -*- coding: utf-8 -*-
"""
REBCO 超导材料领域分析器

整合技术路线、实验方案和 Jc 指标分析功能。
"""

from typing import Dict, List, Any, Optional
from loguru import logger

from ..base import DomainAnalyzerBase
from ..registry import register_domain
from .tech_route import TechRouteAnalyzer
from .exp_scheme import ExpSchemeAnalyzer
from .jc_index import JcIndexAnalyzer


# REBCO 领域 Prompt 模板
REBCO_NER_PROMPT = """
请从以下学术论文内容中提取 REBCO 超导材料相关的实体信息。

实体类型包括：
1. Material（材料）：如 YBCO, REBCO, coated conductor 等
2. Manufacturing_Process_Chain（制备工艺链）：如 PLD, MOCVD, sputtering 等
3. Microstructural_Hierarchy（微观结构层级）：如 grain boundary, pinning center 等
4. Transport_Behavior（传输行为）：如 Jc, Ic, critical current 等

请以 JSON 格式返回，每条实体包含：
{
    "symbol": "实体符号",
    "name": "完整名称",
    "type": "实体类型",
    "subtype": "子类型（如有）",
    "value": "数值（如有）",
    "unit": "单位（如有）",
    "condition": "条件描述（如有）"
}
"""


@register_domain('rebco')
class REBCOAnalyzer(DomainAnalyzerBase):
    """
    REBCO 超导材料领域分析器

    整合三种分析功能：
    - 技术路线分析：从 NER+RE 构建实体网络，提取关键路径
    - 实验方案分析：从 NER 实体生成 8 维度实验方案文本
    - Jc 指标分析：提取临界电流密度数据和条件参数
    """

    def __init__(
        self,
        embedding_service: Any = None,
        vector_service: Any = None,
        llm_service: Any = None,
        thesaurus: List[Dict] = None
    ):
        """
        初始化 REBCO 分析器

        Args:
            embedding_service: 向量化服务
            vector_service: Milvus 向量存储服务
            llm_service: LLM 服务
            thesaurus: 同义词表
        """
        super().__init__(embedding_service, vector_service, llm_service)

        # 初始化子分析器
        self.tech_route_analyzer = TechRouteAnalyzer(thesaurus)
        self.exp_scheme_analyzer = ExpSchemeAnalyzer()
        self.jc_index_analyzer = JcIndexAnalyzer(llm_service)

        logger.info("REBCO 分析器已初始化")

    def get_name(self) -> str:
        """返回领域名称"""
        return "rebco"

    def get_entity_types(self) -> Dict[str, str]:
        """
        返回 REBCO 领域实体类型定义

        Returns:
            {entity_type: description} 字典
        """
        return {
            "Material": "超导材料，如 YBCO、REBCO、coated conductor 等",
            "Manufacturing_Process_Chain": "制备工艺链，如 PLD、MOCVD、sputtering 等",
            "Microstructural_Hierarchy": "微观结构层级，如 grain boundary、pinning center 等",
            "Transport_Behavior": "传输行为，如 Jc、Ic、critical current 等"
        }

    def get_relation_types(self) -> Dict[str, str]:
        """
        返回 REBCO 领域关系类型定义

        Returns:
            {relation_type: description} 字典
        """
        return {
            "has": "材料具有微观结构特征",
            "undergoes": "材料经历制备工艺",
            "produces": "工艺产生材料",
            "controls": "工艺控制微观结构",
            "affects": "微观结构影响传输行为",
            "determines": "材料决定传输行为"
        }

    def get_prompt_template(self) -> str:
        """返回 NER Prompt 模板"""
        return REBCO_NER_PROMPT

    async def build_profile(self, ner_result: Dict) -> str:
        """
        构建 REBCO 领域特征描述

        Args:
            ner_result: NER 结果数据

        Returns:
            特征描述文本
        """
        # 从技术路线和实验方案构建综合特征描述
        tech_route_result = self.tech_route_analyzer.analyze(
            ner_result.get('entities', []),
            ner_result.get('relations', [])
        )

        exp_scheme_result = self.exp_scheme_analyzer.analyze(
            ner_result.get('entities', [])
        )

        # 组合特征描述
        profile_parts = []

        if tech_route_result.get('tech_route_text'):
            profile_parts.append(f"技术路线：{tech_route_result['tech_route_text']}")

        if exp_scheme_result.get('exp_scheme_text'):
            profile_parts.append(f"实验方案：{exp_scheme_result['exp_scheme_text']}")

        profile_text = '\n'.join(profile_parts)

        return profile_text

    async def analyze(self, input_data: Dict) -> Dict:
        """
        执行 REBCO 领域分析

        Args:
            input_data: 分析输入数据，包含：
                - analysis_type: 分析类型（tech_route/exp_scheme/jc）
                - entities: NER 实体列表
                - relations: RE 关系列表
                - content: 原文内容（可选）

        Returns:
            分析结果字典
        """
        analysis_type = input_data.get('analysis_type', 'all')

        entities = input_data.get('entities', [])
        relations = input_data.get('relations', [])
        content = input_data.get('content')

        result = {
            "success": True,
            "message": "REBCO 领域分析完成",
            "analysis_type": analysis_type
        }

        # 技术路线分析
        if analysis_type in ['tech_route', 'all']:
            tech_route_result = self.tech_route_analyzer.analyze(entities, relations)
            result['tech_route'] = tech_route_result

        # 实验方案分析
        if analysis_type in ['exp_scheme', 'all']:
            exp_scheme_result = self.exp_scheme_analyzer.analyze(entities)
            result['exp_scheme'] = exp_scheme_result

        # Jc 指标分析
        if analysis_type in ['jc', 'all']:
            jc_result = await self.jc_index_analyzer.analyze(entities, content)
            result['jc_indicators'] = jc_result

        return result

    async def analyze_tech_route(
        self,
        entities: List[Dict],
        relations: List[Dict],
        top_k: int = 10
    ) -> Dict:
        """
        执行技术路线分析并检索相似论文

        Args:
            entities: NER 实体列表
            relations: RE 关系列表
            top_k: 返回前 K 个相似论文

        Returns:
            技术路线分析结果
        """
        # 分析技术路线
        tech_route_result = self.tech_route_analyzer.analyze(entities, relations)

        if not tech_route_result.get('success') or not tech_route_result.get('tech_route_text'):
            return tech_route_result

        # 检索相似论文
        profile_text = tech_route_result['tech_route_text']
        similar_papers = await self.retrieve_similar(profile_text, collection_name="tech_routes", top_k=top_k)

        tech_route_result['similar_papers'] = similar_papers

        return tech_route_result

    async def analyze_exp_scheme(
        self,
        entities: List[Dict],
        top_k: int = 10
    ) -> Dict:
        """
        执行实验方案分析并检索相似论文

        Args:
            entities: NER 实体列表
            top_k: 返回前 K 个相似论文

        Returns:
            实验方案分析结果
        """
        # 分析实验方案
        exp_scheme_result = self.exp_scheme_analyzer.analyze(entities)

        if not exp_scheme_result.get('success') or not exp_scheme_result.get('exp_scheme_text'):
            return exp_scheme_result

        # 检索相似论文
        profile_text = exp_scheme_result['exp_scheme_text']
        similar_papers = await self.retrieve_similar(profile_text, collection_name="exp_schemes", top_k=top_k)

        exp_scheme_result['similar_papers'] = similar_papers

        return exp_scheme_result

    async def search_jc_indicators(
        self,
        jc_indicators: List[Dict],
        temperature: float = None,
        magnetic_field: float = None,
        angle: float = None
    ) -> Dict:
        """
        按条件搜索 Jc 指标

        Args:
            jc_indicators: Jc 指标列表
            temperature: 目标温度（K）
            magnetic_field: 目标磁场（T）
            angle: 目标角度（deg）

        Returns:
            搜索结果
        """
        filtered = self.jc_index_analyzer.search_by_conditions(
            jc_indicators,
            temperature=temperature,
            magnetic_field=magnetic_field,
            angle=angle
        )

        return {
            "success": True,
            "message": "Jc 指标搜索完成",
            "indicators": filtered,
            "count": len(filtered),
            "search_conditions": {
                "temperature": temperature,
                "magnetic_field": magnetic_field,
                "angle": angle
            }
        }

    async def compare_jc(
        self,
        ner_ids: List[str],
        jc_data_list: List[List[Dict]]
    ) -> Dict:
        """
        对比多篇论文的 Jc 指标

        Args:
            ner_ids: NER 结果 ID 列表
            jc_data_list: 多篇论文的 Jc 指标列表

        Returns:
            Jc 对比结果
        """
        comparison_result = self.jc_index_analyzer.compare_jc(jc_data_list, ner_ids)

        return comparison_result