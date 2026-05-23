# -*- coding: utf-8 -*-
"""
技术路线分析模块

从 NER+RE 构建实体网络，提取关键路径，生成技术路线文本描述。
"""

import copy
import networkx as nx
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Set, Optional, Tuple
from loguru import logger


# ============ 常量定义 ============

# 有效实体类型
VALID_OBJECT_TYPES = {
    'Manufacturing_Process_Chain',
    'Material',
    'Microstructural_Hierarchy',
    'Transport_Behavior'
}

# 有效关系类型配置
VALID_RELATION_TYPES = [
    {'relation_type': 'has', 'source_type': 'Material', 'target_type': 'Microstructural_Hierarchy'},
    {'relation_type': 'undergoes', 'source_type': 'Material', 'target_type': 'Manufacturing_Process_Chain'},
    {'relation_type': 'produces', 'source_type': 'Manufacturing_Process_Chain', 'target_type': 'Material'},
    {'relation_type': 'controls', 'source_type': 'Manufacturing_Process_Chain', 'target_type': 'Microstructural_Hierarchy'},
    {'relation_type': 'affects', 'source_type': 'Microstructural_Hierarchy', 'target_type': 'Transport_Behavior'},
    {'relation_type': 'determines', 'source_type': 'Material', 'target_type': 'Transport_Behavior'},
    {'relation_type': 'affects', 'source_type': 'Transport_Behavior', 'target_type': 'Transport_Behavior'}
]

# 默认汇点集合（路径终点）
DEFAULT_SINKS = {'jc', 'ic', 'critical_current'}

# 默认关键点集合（路径必须包含）
DEFAULT_KEYS = {'pinning'}


class NetworkBuilder:
    """
    实体网络构建器

    根据 NER 实体和 RE 关系构建 NetworkX 多图
    """

    def __init__(self, thesaurus: List[Dict[str, str]] = None):
        """
        初始化网络构建器

        Args:
            thesaurus: 同义词表，用于实体消歧
        """
        self.thesaurus = thesaurus or []
        logger.debug(f"网络构建器已初始化，同义词表：{len(self.thesaurus)} 条")

    def _filter_objects(self, df_objects: pd.DataFrame) -> List[Dict[str, Any]]:
        """筛选有效实体"""
        valid_types = VALID_OBJECT_TYPES

        list_object = list(df_objects[['symbol', 'type']].drop_duplicates().to_dict(orient='records'))

        return [obj for obj in list_object if obj.get('type') in valid_types]

    def _filter_relations(self, df_relations: pd.DataFrame) -> List[Dict[str, Any]]:
        """筛选有效关系"""
        valid_relation_configs = VALID_RELATION_TYPES

        list_relation = list(df_relations[['source_type', 'source_entity',
                                           'target_type', 'target_entity', 'relation_type']].drop_duplicates().to_dict(orient='records'))

        list_relation_valid = []
        for relation in list_relation:
            for relation_valid in valid_relation_configs:
                if (relation['relation_type'] == relation_valid['relation_type'] and
                    relation['source_type'] == relation_valid['source_type'] and
                    relation['target_type'] == relation_valid['target_type']):
                    list_relation_valid.append(relation)
                    break

        return list_relation_valid

    def _disambiguate_symbol(self, symbol: str, entity_type: str) -> str:
        """根据同义词表消歧"""
        for thesaurus in self.thesaurus:
            if symbol == thesaurus.get('symbol') and entity_type == thesaurus.get('type'):
                return thesaurus.get('thesaurus', symbol)
        return symbol

    def build_network(self, df_objects: pd.DataFrame, df_relations: pd.DataFrame) -> nx.MultiDiGraph:
        """
        构建实体网络

        Args:
            df_objects: NER 实体 DataFrame
            df_relations: RE 关系 DataFrame

        Returns:
            nx.MultiDiGraph: 构建的网络图
        """
        # 筛选有效实体
        list_object_valid = self._filter_objects(df_objects)

        # 筛选有效关系
        list_relation_valid = self._filter_relations(df_relations)

        # 实体消歧
        list_object_disambiguated = []
        for obj in list_object_valid:
            obj_disambiguated = copy.deepcopy(obj)
            obj_disambiguated['symbol'] = self._disambiguate_symbol(obj['symbol'], obj['type'])
            list_object_disambiguated.append(obj_disambiguated)

        # 关系消歧
        list_relation_disambiguated = []
        for relation in list_relation_valid:
            relation_disambiguated = copy.deepcopy(relation)
            relation_disambiguated['source_entity'] = self._disambiguate_symbol(
                relation['source_entity'], relation['source_type'])
            relation_disambiguated['target_entity'] = self._disambiguate_symbol(
                relation['target_entity'], relation['target_type'])
            list_relation_disambiguated.append(relation_disambiguated)

        # 构建网络
        network = nx.MultiDiGraph()

        # 添加节点
        for idx, node in enumerate(list_object_disambiguated):
            network.add_node(idx,
                           object_symbol=node['symbol'],
                           object_type=node['type'])

        # 添加边
        for relation in list_relation_disambiguated:
            node_source = None
            node_target = None

            for node_idx in range(len(network.nodes)):
                node_data = network.nodes[node_idx]
                if (relation['source_type'] == node_data['object_type'] and
                    relation['source_entity'] == node_data['object_symbol']):
                    node_source = node_idx

                if (relation['target_type'] == node_data['object_type'] and
                    relation['target_entity'] == node_data['object_symbol']):
                    node_target = node_idx

            if node_source is None or node_target is None:
                continue

            network.add_edge(node_source, node_target, relation=relation['relation_type'])

        return network


class PathExtractor:
    """
    关键路径提取器

    从实体网络中提取从源点到汇点的关键路径
    """

    def __init__(self, set_sinks: Set[str] = None, set_keys: Set[str] = None):
        """
        初始化路径提取器

        Args:
            set_sinks: 汇点集合（路径终点需包含这些关键词）
            set_keys: 关键点集合（路径必须包含这些关键词）
        """
        self.set_sinks = set_sinks or DEFAULT_SINKS
        self.set_keys = set_keys or DEFAULT_KEYS

    def _text_contain_keyword(self, text: str, keyword_set: Set[str]) -> bool:
        """判断文本是否包含关键词集合中的任意词"""
        if isinstance(text, str):
            return any(keyword in text.lower() for keyword in keyword_set)
        elif isinstance(text, (set, list, tuple)):
            return any(any(keyword in t.lower() for keyword in keyword_set) for t in text)
        return False

    def _find_source_nodes(self, network: nx.MultiDiGraph) -> Set[int]:
        """找到网络的源点（入度为 0 的节点）"""
        source_nodes = set()

        for node in network.nodes:
            if network.in_degree(node) == 0:
                source_nodes.add(node)

        return source_nodes

    def _find_sink_nodes(self, network: nx.MultiDiGraph) -> Set[int]:
        """找到汇点节点（symbol 包含 set_sinks 中的关键词）"""
        sink_nodes = set()

        for node in network.nodes:
            node_symbol = network.nodes[node].get('object_symbol', '')
            if self._text_contain_keyword(node_symbol, self.set_sinks):
                sink_nodes.add(node)

        return sink_nodes

    def _find_key_nodes(self, network: nx.MultiDiGraph) -> Set[int]:
        """找到关键点节点（symbol 包含 set_keys 中的关键词）"""
        key_nodes = set()

        for node in network.nodes:
            node_symbol = network.nodes[node].get('object_symbol', '')
            if self._text_contain_keyword(node_symbol, self.set_keys):
                key_nodes.add(node)

        return key_nodes

    def extract_paths(self, network: nx.MultiDiGraph) -> List[List[int]]:
        """
        提取关键路径

        Args:
            network: NetworkX 多图

        Returns:
            关键路径列表，每个路径为节点索引列表
        """
        # 找到源点、汇点、关键点
        source_nodes = self._find_source_nodes(network)
        sink_nodes = self._find_sink_nodes(network)
        key_nodes = self._find_key_nodes(network)

        if not source_nodes or not sink_nodes:
            return []

        # 收集所有候选路径
        candidate_paths = []

        for source in source_nodes:
            for sink in sink_nodes:
                try:
                    all_paths = nx.all_simple_paths(network, source=source, target=sink)
                    for path in all_paths:
                        if path not in candidate_paths:
                            candidate_paths.append(path)
                except nx.NetworkXNoPath:
                    continue

        # 筛选包含关键点的路径
        important_paths = []
        for path in candidate_paths:
            if set(path) & key_nodes:
                important_paths.append(path)

        return important_paths


class RouteTextGenerator:
    """
    路径文本化生成器

    将 NetworkX 路径转换为可读的技术路线文本
    """

    def path_to_text(self, path: List[int], network_dict: Dict[str, Any]) -> str:
        """
        将单个路径转换为文本

        Args:
            path: 节点索引列表
            network_dict: nx.node_link_data() 转换后的网络字典

        Returns:
            路径文本字符串
        """
        nodes = network_dict['nodes']
        links = network_dict.get('links', [])

        if not path:
            return ""

        # 构建路径文本
        text_parts = []

        # 添加源点信息
        source_idx = path[0]
        source_symbol = nodes[source_idx].get('object_symbol', 'Unknown')
        text_parts.append(source_symbol)

        # 添加路径中的边和目标节点
        for i in range(1, len(path)):
            source_idx = path[i - 1]
            target_idx = path[i]
            target_symbol = nodes[target_idx].get('object_symbol', 'Unknown')

            # 查找边的关系
            relations = []
            for link in links:
                if link['source'] == source_idx and link['target'] == target_idx:
                    relations.append(link.get('relation', 'unknown'))

            relation_str = relations[0] if relations else 'links_to'
            text_parts.append(f" - {relation_str} - {target_symbol}")

        return ''.join(text_parts)

    def paths_to_text(self, paths: List[List[int]], network_dict: Dict[str, Any]) -> str:
        """
        将多个路径转换为文本

        Args:
            paths: 路径列表
            network_dict: 网络字典

        Returns:
            技术路线文本
        """
        if not paths:
            return ""

        path_texts = []
        for idx, path in enumerate(paths):
            path_text = self.path_to_text(path, network_dict)
            if path_text:
                path_texts.append(f"Tech Route {idx + 1}: {path_text}")

        return '\n'.join(path_texts)


class TechRouteAnalyzer:
    """
    技术路线分析器

    整合网络构建、路径提取和文本生成功能
    """

    def __init__(self, thesaurus: List[Dict] = None, set_sinks: Set[str] = None, set_keys: Set[str] = None):
        """
        初始化分析器

        Args:
            thesaurus: 同义词表
            set_sinks: 汇点集合
            set_keys: 关键点集合
        """
        self.network_builder = NetworkBuilder(thesaurus)
        self.path_extractor = PathExtractor(set_sinks, set_keys)
        self.text_generator = RouteTextGenerator()
        logger.info("技术路线分析器已初始化")

    def analyze(
        self,
        entities_data: List[Dict],
        relations_data: List[Dict]
    ) -> Dict[str, Any]:
        """
        分析单篇论文的技术路线

        Args:
            entities_data: NER 实体列表
            relations_data: RE 关系列表

        Returns:
            技术路线分析结果
        """
        # 构建 DataFrame
        if not entities_data:
            return {
                "success": False,
                "message": "实体数据为空",
                "tech_route_text": None,
                "paths_count": 0
            }

        df_objects = pd.DataFrame(entities_data)

        # 检查必要的列是否存在
        if 'symbol' not in df_objects.columns or 'type' not in df_objects.columns:
            return {
                "success": False,
                "message": "实体数据缺少必要字段",
                "tech_route_text": None,
                "paths_count": 0
            }

        # 处理关系数据
        if relations_data:
            df_relations = pd.DataFrame(relations_data)
            # 检查必要的列是否存在
            required_cols = ['source_type', 'source_entity', 'target_type', 'target_entity', 'relation_type']
            if not all(col in df_relations.columns for col in required_cols):
                df_relations = pd.DataFrame(columns=required_cols)
        else:
            df_relations = pd.DataFrame(columns=['source_type', 'source_entity', 'target_type', 'target_entity', 'relation_type'])

        if df_objects.empty:
            return {
                "success": False,
                "message": "实体数据为空",
                "tech_route_text": None,
                "paths_count": 0
            }

        # 构建网络
        network = self.network_builder.build_network(df_objects, df_relations)

        if len(network.nodes) == 0:
            return {
                "success": False,
                "message": "无法构建实体网络",
                "tech_route_text": None,
                "paths_count": 0
            }

        # 提取路径
        paths = self.path_extractor.extract_paths(network)

        if not paths:
            return {
                "success": True,
                "message": "未找到关键路径",
                "tech_route_text": None,
                "paths_count": 0
            }

        # 生成文本
        network_dict = nx.node_link_data(network)
        tech_route_text = self.text_generator.paths_to_text(paths, network_dict)

        return {
            "success": True,
            "message": "技术路线分析完成",
            "tech_route_text": tech_route_text,
            "paths_count": len(paths),
            "network_nodes": len(network.nodes),
            "network_edges": len(network.edges)
        }

    def calculate_similarity(self, vector1: List[float], vector2: List[float]) -> float:
        """
        计算余弦相似度

        Args:
            vector1: 向量 1
            vector2: 向量 2

        Returns:
            余弦相似度
        """
        if len(vector1) != len(vector2):
            return 0.0

        v1 = np.array(vector1)
        v2 = np.array(vector2)

        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return np.dot(v1, v2) / (norm1 * norm2)

    def find_similar_routes(
        self,
        query_vector: List[float],
        database: List[Dict],
        threshold: float = 0.5,
        top_k: int = 10
    ) -> List[Dict]:
        """
        检索相似技术路线

        Args:
            query_vector: 查询向量
            database: 技术路线数据库
            threshold: 相似度阈值
            top_k: 返回前 K 个结果

        Returns:
            相似技术路线列表
        """
        similar_routes = []

        for record in database:
            db_vector = record.get('vector', [])
            if not db_vector:
                continue

            similarity = self.calculate_similarity(query_vector, db_vector)

            if similarity >= threshold:
                similar_routes.append({
                    'paper_id': record.get('paper_id'),
                    'tech_route': record.get('tech_route_text'),
                    'similarity': similarity
                })

        # 按相似度降序排序
        similar_routes.sort(key=lambda x: x['similarity'], reverse=True)

        return similar_routes[:top_k] if top_k else similar_routes