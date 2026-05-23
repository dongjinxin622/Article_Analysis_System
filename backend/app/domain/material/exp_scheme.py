# -*- coding: utf-8 -*-
"""
实验方案分析模块

从 NER 实体中提取实验方案维度信息，生成实验方案文本描述。
"""

import json
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from loguru import logger


# ============ 常量定义 ============

# 子类型到类别的映射（8维度）
SUBTYPE_MAPPING = {
    'Material_Fabrication': '材料准备',
    'Deposition_Techniques': '沉积技术',
    'Process_Parameters': '工艺参数',
    'Post-Processing': '后处理',
    'Characterization_Techniques': '表征技术',
    'System_Constraints': '系统约束',
    'Simulation': '模拟分析',
    'Irradiation': '辐照处理'
}

# 类别顺序
CATEGORIES_ORDER = [
    '材料准备', '沉积技术', '工艺参数', '后处理',
    '辐照处理', '表征技术', '系统约束', '模拟分析'
]


class ExpSchemeAnalyzer:
    """
    实验方案分析器

    从 NER 实体数据生成实验方案文本描述
    """

    def __init__(self):
        """初始化分析器"""
        logger.info("实验方案分析器已初始化")

    def format_entity_text(self, entity: Dict) -> str:
        """
        格式化单个实体为文本

        Args:
            entity: 实体字典

        Returns:
            格式化的实体文本
        """
        entity_parts = []

        # Symbol
        if entity.get('symbol'):
            entity_parts.append(str(entity['symbol']))

        # Name
        if entity.get('name'):
            entity_parts.append(f"- {entity['name']}")

        # Value + Unit
        if entity.get('value'):
            value_str = str(entity['value'])
            if entity.get('unit'):
                entity_parts.append(f": {value_str} {entity['unit']}")
            else:
                entity_parts.append(f": {value_str}")

        # Condition
        if entity.get('condition'):
            entity_parts.append(f"[条件：{entity['condition']}]")

        # Parameters
        if entity.get('parameters'):
            params = entity['parameters']
            if isinstance(params, str):
                try:
                    params = json.loads(params.replace("'", '"'))
                except:
                    params = None

            if params and isinstance(params, list):
                param_strs = []
                for param in params:
                    if isinstance(param, dict) and 'type' in param and 'value' in param:
                        param_str = f"{param['type']}: {param['value']}"
                        if 'unit' in param and param['unit']:
                            param_str += f" {param['unit']}"
                        param_strs.append(param_str)

                if param_strs:
                    entity_parts.append(f"(参数：{'; '.join(param_strs)})")

        if not entity_parts:
            return ""

        return " ".join(entity_parts) + "\n"

    def categorize_entity(self, entity: Dict) -> str:
        """
        将实体归类到对应维度

        Args:
            entity: 实体字典

        Returns:
            类别名称
        """
        subtype = entity.get('subtype', '')

        # 直接匹配
        if subtype in SUBTYPE_MAPPING:
            return SUBTYPE_MAPPING[subtype]

        # 关键词匹配
        subtype_str = str(subtype).lower()
        if any(kw in subtype_str for kw in ['material', 'fabrication', 'preparation']):
            return '材料准备'
        elif any(kw in subtype_str for kw in ['deposition', 'growth', 'coating']):
            return '沉积技术'
        elif any(kw in subtype_str for kw in ['parameter', 'temperature', 'pressure']):
            return '工艺参数'
        elif any(kw in subtype_str for kw in ['processing', 'treatment', 'annealing']):
            return '后处理'
        elif any(kw in subtype_str for kw in ['irradiation', 'radiation']):
            return '辐照处理'
        elif any(kw in subtype_str for kw in ['characterization', 'measurement', 'analysis']):
            return '表征技术'
        elif any(kw in subtype_str for kw in ['constraint', 'system', 'setup']):
            return '系统约束'
        elif any(kw in subtype_str for kw in ['simulation', 'model']):
            return '模拟分析'
        else:
            return '材料准备'  # 默认类别

    def analyze(
        self,
        entities_data: List[Dict],
        technical_route: str = None
    ) -> Dict[str, Any]:
        """
        分析单篇论文的实验方案

        Args:
            entities_data: NER 实体列表
            technical_route: 技术路线标识（可选）

        Returns:
            实验方案分析结果
        """
        if not entities_data:
            return {
                "success": False,
                "message": "实体数据为空",
                "exp_scheme_text": None,
                "dimensions": {}
            }

        # 构建 8 维度框架
        framework = {k: [] for k in CATEGORIES_ORDER}

        # 分类实体
        for entity in entities_data:
            category = self.categorize_entity(entity)
            if category in framework:
                framework[category].append(entity)

        # 生成文本
        text_parts = []
        for category in CATEGORIES_ORDER:
            entities = framework.get(category, [])
            if entities:
                text_parts.append(f'\n"{category}"')
                for entity in entities:
                    entity_text = self.format_entity_text(entity)
                    if entity_text:
                        text_parts.append(f'  • {entity_text}')

        exp_scheme_text = '\n'.join(text_parts)

        # 统计各维度实体数量
        dimensions = {}
        for category, entities in framework.items():
            dimensions[category] = len(entities)

        return {
            "success": True,
            "message": "实验方案分析完成",
            "exp_scheme_text": exp_scheme_text,
            "dimensions": dimensions,
            "technical_route": technical_route,
            "total_entities": len(entities_data)
        }

    def compare_schemes(
        self,
        scheme1: Dict[str, Any],
        scheme2: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        比较两个实验方案

        Args:
            scheme1: 实验方案 1
            scheme2: 实验方案 2

        Returns:
            比较结果
        """
        dims1 = scheme1.get('dimensions', {})
        dims2 = scheme2.get('dimensions', {})

        comparison = {}
        for category in CATEGORIES_ORDER:
            count1 = dims1.get(category, 0)
            count2 = dims2.get(category, 0)
            comparison[category] = {
                'scheme1': count1,
                'scheme2': count2,
                'difference': count2 - count1
            }

        # 计算相似度
        vector1 = [dims1.get(c, 0) for c in CATEGORIES_ORDER]
        vector2 = [dims2.get(c, 0) for c in CATEGORIES_ORDER]

        v1 = np.array(vector1)
        v2 = np.array(vector2)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            similarity = 0.0
        else:
            similarity = np.dot(v1, v2) / (norm1 * norm2)

        return {
            "success": True,
            "message": "实验方案比较完成",
            "comparison": comparison,
            "similarity": similarity,
            "scheme1_text": scheme1.get('exp_scheme_text'),
            "scheme2_text": scheme2.get('exp_scheme_text')
        }

    def find_similar_schemes(
        self,
        query_dimensions: Dict[str, int],
        database: List[Dict],
        threshold: float = 0.5,
        top_k: int = 10
    ) -> List[Dict]:
        """
        检索相似实验方案

        Args:
            query_dimensions: 查询方案的维度统计
            database: 实验方案数据库
            threshold: 相似度阈值
            top_k: 返回前 K 个结果

        Returns:
            相似实验方案列表
        """
        query_vector = np.array([query_dimensions.get(c, 0) for c in CATEGORIES_ORDER])
        query_norm = np.linalg.norm(query_vector)

        similar_schemes = []

        for record in database:
            dims = record.get('dimensions', {})
            db_vector = np.array([dims.get(c, 0) for c in CATEGORIES_ORDER])
            db_norm = np.linalg.norm(db_vector)

            if query_norm == 0 or db_norm == 0:
                similarity = 0.0
            else:
                similarity = np.dot(query_vector, db_vector) / (query_norm * db_norm)

            if similarity >= threshold:
                similar_schemes.append({
                    'paper_id': record.get('paper_id'),
                    'exp_scheme_text': record.get('exp_scheme_text'),
                    'dimensions': dims,
                    'similarity': similarity
                })

        # 按相似度降序排序
        similar_schemes.sort(key=lambda x: x['similarity'], reverse=True)

        return similar_schemes[:top_k] if top_k else similar_schemes