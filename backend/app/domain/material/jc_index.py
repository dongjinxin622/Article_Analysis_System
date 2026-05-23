# -*- coding: utf-8 -*-
"""
Jc 指标分析模块

从 NER 实体和原文内容中提取 Jc（临界电流密度）指标数据。
"""

import json
import math
import pandas as pd
from typing import List, Dict, Any, Optional
from loguru import logger


class JcIndexAnalyzer:
    """
    Jc 指标分析器

    从 NER 数据中定位 Jc 相关实体，提取 Jc 值和条件参数。
    """

    # Jc 相关关键词
    JC_KEYWORDS = ['jc', 'j_c', 'critical current', 'critical_current', '临界电流', '临界电流密度']

    # 磁场单位换算因子（转换为 Tesla）
    FIELD_UNIT_CONVERSION = {
        't': 1.0,
        'tesla': 1.0,
        'mt': 0.001,
        'g': 1e-4,
        'gauss': 1e-4,
        'oe': 1e-4,
        'koe': 0.1,
    }

    def __init__(self, llm_service: Any = None):
        """
        初始化分析器

        Args:
            llm_service: LLM 服务实例（用于复杂文本提取）
        """
        self.llm_service = llm_service
        logger.info("Jc 指标分析器已初始化")

    def find_jc_entities(self, entities_data: List[Dict]) -> List[Dict]:
        """
        从 NER 数据中找到 Jc 相关实体

        Args:
            entities_data: NER 实体列表

        Returns:
            Jc 相关实体列表
        """
        jc_entities = []

        for entity in entities_data:
            # 检查类型是否为 Transport_Behavior
            if entity.get('type', '') != 'Transport_Behavior':
                continue

            # 检查 symbol 或 name 是否包含 Jc 相关关键词
            symbol = str(entity.get('symbol', '')).lower()
            name = str(entity.get('name', '')).lower()

            for keyword in self.JC_KEYWORDS:
                if keyword in symbol or keyword in name:
                    jc_entities.append(entity)
                    break

        return jc_entities

    def normalize_jc_record(self, record: Dict) -> Dict:
        """
        标准化 Jc 记录的单位和数值

        Args:
            record: 原始 Jc 记录

        Returns:
            标准化后的记录
        """
        normalized = record.copy()

        # 磁场单位换算（统一转换为 T）
        if record.get('magnetic_field') is not None:
            field_value = record['magnetic_field']
            field_unit = str(record.get('magnetic_field_unit', 'T')).lower()

            for u, factor in self.FIELD_UNIT_CONVERSION.items():
                if u in field_unit:
                    normalized['magnetic_field_T'] = float(field_value) * factor
                    break
            else:
                normalized['magnetic_field_T'] = float(field_value)

        # 温度单位换算（统一转换为 K）
        if record.get('temperature') is not None:
            temp_value = record['temperature']
            temp_unit = str(record.get('temperature_unit', 'K')).lower()

            if 'c' in temp_unit and 'k' not in temp_unit:  # Celsius
                normalized['temperature_K'] = float(temp_value) + 273.15
            else:  # Kelvin
                normalized['temperature_K'] = float(temp_value)

        # 角度单位换算（统一转换为 deg）
        if record.get('angle') is not None:
            angle_value = record['angle']
            angle_unit = str(record.get('angle_unit', 'deg')).lower()

            if 'rad' in angle_unit:  # Radian
                normalized['angle_deg'] = float(angle_value) * 180.0 / math.pi
            else:  # Degree
                normalized['angle_deg'] = float(angle_value)

        return normalized

    def extract_from_entity(self, entity: Dict) -> Dict:
        """
        从单个 Jc 实体提取指标数据

        Args:
            entity: Jc 实体字典

        Returns:
            Jc 指标数据
        """
        jc_record = {
            'jc_value': None,
            'jc_unit': None,
            'temperature': None,
            'temperature_unit': None,
            'magnetic_field': None,
            'magnetic_field_unit': None,
            'angle': None,
            'angle_unit': None,
            'condition': None,
            'source_entity': entity.get('symbol'),
            'source_sentence': None
        }

        # 提取值
        if entity.get('value'):
            jc_record['jc_value'] = entity.get('value')
            jc_record['jc_unit'] = entity.get('unit')

        # 提取条件参数
        if entity.get('condition'):
            jc_record['condition'] = entity.get('condition')

        # 提取 parameters 中的条件参数
        if entity.get('parameters'):
            params = entity.get('parameters')
            if isinstance(params, str):
                try:
                    params = json.loads(params.replace("'", '"'))
                except:
                    params = None

            if params and isinstance(params, list):
                for param in params:
                    if isinstance(param, dict):
                        param_type = param.get('type', '').lower()
                        param_value = param.get('value')
                        param_unit = param.get('unit')

                        if param_type in ['temperature', 'temp', 't']:
                            jc_record['temperature'] = param_value
                            jc_record['temperature_unit'] = param_unit
                        elif param_type in ['magnetic_field', 'field', 'b', 'h']:
                            jc_record['magnetic_field'] = param_value
                            jc_record['magnetic_field_unit'] = param_unit
                        elif param_type in ['angle', 'theta']:
                            jc_record['angle'] = param_value
                            jc_record['angle_unit'] = param_unit

        return self.normalize_jc_record(jc_record)

    async def analyze(
        self,
        entities_data: List[Dict],
        content_text: str = None
    ) -> Dict[str, Any]:
        """
        分析单篇论文的 Jc 指标

        Args:
            entities_data: NER 实体列表
            content_text: 原文内容（可选，用于 LLM 提取）

        Returns:
            Jc 指标分析结果
        """
        # 找到 Jc 相关实体
        jc_entities = self.find_jc_entities(entities_data)

        if not jc_entities:
            return {
                "success": False,
                "message": "未找到 Jc 相关实体",
                "jc_indicators": [],
                "count": 0
            }

        # 从实体提取指标
        jc_indicators = []
        for entity in jc_entities:
            jc_record = self.extract_from_entity(entity)
            if jc_record.get('jc_value') is not None:
                jc_indicators.append(jc_record)

        # 如果有 LLM 服务且有原文内容，尝试更精确提取
        if self.llm_service and content_text and len(jc_entities) > 0:
            try:
                # 使用 LLM 提取更详细的条件参数
                llm_results = await self._llm_extract(content_text, jc_entities)
                jc_indicators.extend(llm_results)
            except Exception as e:
                logger.warning(f"LLM 提取失败: {e}")

        return {
            "success": True,
            "message": "Jc 指标分析完成",
            "jc_indicators": jc_indicators,
            "count": len(jc_indicators)
        }

    async def _llm_extract(
        self,
        content_text: str,
        jc_entities: List[Dict]
    ) -> List[Dict]:
        """
        使用 LLM 从原文提取 Jc 指标

        Args:
            content_text: 原文内容
            jc_entities: Jc 实体列表

        Returns:
            LLM 提取的 Jc 指标列表
        """
        if not self.llm_service:
            return []

        prompt = f"""
请从以下文本中提取所有 Jc（临界电流密度）指标数据，包括：
- Jc 值和单位
- 温度条件和单位
- 磁场条件和单位
- 角度条件和单位（如有）

请以 JSON 格式返回，格式如下：
[
    {{
        "jc_value": 数值,
        "jc_unit": "单位",
        "temperature": 数值,
        "temperature_unit": "单位",
        "magnetic_field": 数值,
        "magnetic_field_unit": "单位",
        "angle": 数值,
        "angle_unit": "单位"
    }}
]

原文：
{content_text[:8000]}
"""

        try:
            response = await self.llm_service.chat(prompt)
            result_text = response.get('content', '')

            # 解析 JSON
            if '```json' in result_text:
                result_text = result_text.split('```json')[1].split('```')[0].strip()
            elif '```' in result_text:
                result_text = result_text.split('```')[1].split('```')[0].strip()

            jc_data = json.loads(result_text)

            # 标准化每条记录
            normalized = [self.normalize_jc_record(r) for r in jc_data]

            return normalized

        except Exception as e:
            logger.error(f"LLM 提取失败: {e}")
            return []

    def search_by_conditions(
        self,
        jc_indicators: List[Dict],
        temperature: float = None,
        magnetic_field: float = None,
        angle: float = None,
        tolerance: float = 0.1
    ) -> List[Dict]:
        """
        按条件筛选 Jc 指标

        Args:
            jc_indicators: Jc 指标列表
            temperature: 目标温度（K）
            magnetic_field: 目标磁场（T）
            angle: 目标角度（deg）
            tolerance: 容差范围

        Returns:
            符合条件的 Jc 指标列表
        """
        filtered = []

        for indicator in jc_indicators:
            # 温度筛选
            if temperature is not None:
                temp_k = indicator.get('temperature_K')
                if temp_k is None or abs(temp_k - temperature) > tolerance * temperature:
                    continue

            # 磁场筛选
            if magnetic_field is not None:
                field_t = indicator.get('magnetic_field_T')
                if field_t is None or abs(field_t - magnetic_field) > tolerance * magnetic_field:
                    continue

            # 角度筛选
            if angle is not None:
                angle_deg = indicator.get('angle_deg')
                if angle_deg is None or abs(angle_deg - angle) > tolerance * 180:
                    continue

            filtered.append(indicator)

        return filtered

    def compare_jc(
        self,
        jc_data_list: List[List[Dict]],
        paper_ids: List[str] = None
    ) -> Dict[str, Any]:
        """
        对比多篇论文的 Jc 指标

        Args:
            jc_data_list: 多篇论文的 Jc 指标列表
            paper_ids: 论文标识列表

        Returns:
            Jc 对比结果
        """
        comparison_table = []
        max_jc_values = []

        for idx, jc_indicators in enumerate(jc_data_list):
            paper_id = paper_ids[idx] if paper_ids and idx < len(paper_ids) else f"Paper_{idx}"

            # 提取最大 Jc 值
            valid_jc = [i for i in jc_indicators if i.get('jc_value') is not None]
            if valid_jc:
                max_jc = max(valid_jc, key=lambda x: float(x.get('jc_value', 0)))
                max_jc_values.append({
                    'paper_id': paper_id,
                    'max_jc': max_jc.get('jc_value'),
                    'max_jc_unit': max_jc.get('jc_unit'),
                    'conditions': {
                        'temperature': max_jc.get('temperature'),
                        'magnetic_field': max_jc.get('magnetic_field'),
                        'angle': max_jc.get('angle')
                    }
                })

            # 收集所有指标
            for indicator in jc_indicators:
                comparison_table.append({
                    'paper_id': paper_id,
                    'jc_value': indicator.get('jc_value'),
                    'jc_unit': indicator.get('jc_unit'),
                    'temperature_K': indicator.get('temperature_K'),
                    'magnetic_field_T': indicator.get('magnetic_field_T'),
                    'angle_deg': indicator.get('angle_deg')
                })

        return {
            "success": True,
            "message": "Jc 对比分析完成",
            "comparison_table": comparison_table,
            "max_jc_values": max_jc_values,
            "papers_count": len(jc_data_list)
        }