# -*- coding: utf-8 -*-
"""
全量技术路线向量生成脚本
为所有分类（PLD/MOD/MOCVD/Other）的论文生成 tech_route 向量并上传到 Milvus

数据源见下方配置常量。目标：Milvus tech_routes collection
"""
import pickle
import os
import json
import copy
import time
import sys
from pathlib import Path
from collections import Counter
import pandas as pd
import numpy as np
import networkx as nx
from openai import OpenAI
from pymilvus import Collection, connections, utility, DataType

# ========== 配置 ==========
NER_PATH = r"data\results\NER_results_3526_revised.xlsx"
RE_PATH = r"data\results\RE_results_revised.xlsx"
CLS_PATH = r".\data\cls_final.pkl"
THESAURUS_PATH = r"data\深度推理方法\thesaurus_relation_data.json"
EXISTING_TR_PATH = r"data\深度推理方法\technical_route.pkl"

API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIM = 1024

MILVUS_HOST = "localhost"
MILVUS_PORT = 19530

# 分类 → tech_route 关键词映射（构建网络时的分类标签）
CATEGORY_KEYWORDS = ['PLD', 'MOD', 'MOCVD', 'Other']

# ========== LLM 和 Embedding ==========
client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def text_to_vector(text: str, dim: int = EMBEDDING_DIM) -> list:
    """用 text-embedding-v4 生成向量"""
    if not text or not text.strip():
        return [0.0] * dim
    try:
        resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[text], dimensions=dim)
        return resp.data[0].embedding
    except Exception as e:
        print(f"  向量生成失败: {e}")
        return [0.0] * dim


# ========== 实体网络构建（复用 v2 逻辑）==========

LIST_TYPE_OBJECT_VALID = [
    'Manufacturing_Process_Chain', 'Material',
    'Microstructural_Hierarchy', 'Transport_Behavior'
]

LIST_TYPE_RELATION_VALID = [
    {'relation_type': 'has', 'source_type': 'Material', 'target_type': 'Microstructural_Hierarchy'},
    {'relation_type': 'undergoes', 'source_type': 'Material', 'target_type': 'Manufacturing_Process_Chain'},
    {'relation_type': 'produces', 'source_type': 'Manufacturing_Process_Chain', 'target_type': 'Material'},
    {'relation_type': 'controls', 'source_type': 'Manufacturing_Process_Chain', 'target_type': 'Microstructural_Hierarchy'},
    {'relation_type': 'affects', 'source_type': 'Microstructural_Hierarchy', 'target_type': 'Transport_Behavior'},
    {'relation_type': 'determines', 'source_type': 'Material', 'target_type': 'Transport_Behavior'},
    {'relation_type': 'affects', 'source_type': 'Transport_Behavior', 'target_type': 'Transport_Behavior'},
]


def text_contain_keyword(text, keywords_set):
    if isinstance(text, str):
        return any(kw in text.lower() for kw in keywords_set)
    elif isinstance(text, (set, list, tuple)):
        return any(any(kw in t.lower() for kw in keywords_set) for t in text if isinstance(t, str))
    return False


def construct_network(data_objects, data_relations, thesaurus):
    """从实体和关系构建 NetworkX 图"""
    # 实体筛选和消歧
    list_objects = data_objects[['symbol', 'type']].drop_duplicates().to_dict(orient='records')
    list_objects_valid = [o for o in list_objects if o['type'] in LIST_TYPE_OBJECT_VALID]

    # 关系筛选
    list_relations = data_relations[
        ['source_type', 'source_entity', 'target_type', 'target_entity', 'relation_type']
    ].drop_duplicates().to_dict(orient='records')

    list_relations_valid = []
    for rel in list_relations:
        for rv in LIST_TYPE_RELATION_VALID:
            if (rel['relation_type'] == rv['relation_type']
                    and rel['source_type'] == rv['source_type']
                    and rel['target_type'] == rv['target_type']):
                list_relations_valid.append(rel)
                break

    # 实体消歧
    list_objects_disambiguited = []
    for obj in list_objects_valid:
        obj_d = copy.deepcopy(obj)
        for th in thesaurus:
            if obj['symbol'] == th['symbol'] and obj['type'] == th['type']:
                obj_d['symbol'] = th['thesaurus']
                break
        list_objects_disambiguited.append(obj_d)

    # 关系消歧
    list_relations_disambiguited = []
    for rel in list_relations_valid:
        rel_d = copy.deepcopy(rel)
        for th in thesaurus:
            if rel['source_entity'] == th['symbol'] and rel['source_type'] == th['type']:
                rel_d['source_entity'] = th['thesaurus']
                break
        for th in thesaurus:
            if rel['target_entity'] == th['symbol'] and rel['target_type'] == th['type']:
                rel_d['target_entity'] = th['thesaurus']
                break
        list_relations_disambiguited.append(rel_d)

    # 构建网络
    network = nx.MultiDiGraph()
    for idx, obj in enumerate(list_objects_disambiguited):
        network.add_node(idx, object_symbol=obj['symbol'], object_type=obj['type'])

    for rel in list_relations_disambiguited:
        node_source = node_target = None
        for node in range(len(network._node)):
            nd = network._node[node]
            if rel['source_type'] == nd['object_type'] and rel['source_entity'] == nd['object_symbol']:
                node_source = node
            if rel['target_type'] == nd['object_type'] and rel['target_entity'] == nd['object_symbol']:
                node_target = node
        if node_source is not None and node_target is not None:
            network.add_edge(node_source, node_target, relation=rel['relation_type'])

    return network


# ========== 技术路线提取 ==========

def find_important_path(network, sinks=None, keys=None):
    """找到从源点到 sink 经过关键节点的路径"""
    if sinks is None:
        sinks = {'jc', 'ic', 'critical_current'}
    if keys is None:
        keys = {'pinning'}

    reversed_net = network.reverse()
    nodes_source = {n for n in network._node if len(reversed_net._adj[n]) == 0}
    nodes_sink = {n for n in network._node if text_contain_keyword(network._node[n]['object_symbol'], sinks)}
    nodes_key = {n for n in network._node if text_contain_keyword(network._node[n]['object_symbol'], keys)}

    if not nodes_sink or not nodes_source:
        return []

    candidates = []
    for src in nodes_source:
        for snk in nodes_sink:
            try:
                for path in nx.all_simple_paths(network, source=src, target=snk):
                    if path not in candidates:
                        candidates.append(path)
            except nx.NetworkXNoPath:
                continue

    return [p for p in candidates if set(p) & nodes_key]


def path_to_text(paths, network):
    """将路径转为文本描述"""
    lines = []
    for idx1, path in enumerate(paths):
        text = f'Tech Route {idx1 + 1}: '
        text += network['nodes'][path[0]]['object_symbol']
        for i in range(1, len(path)):
            src_idx, tgt_idx = path[i - 1], path[i]
            tgt_symbol = network['nodes'][tgt_idx]['object_symbol']
            for link in network['links']:
                if link['source'] == src_idx and link['target'] == tgt_idx:
                    text += f' - {link["relation"]} - {tgt_symbol}'
                    break
        lines.append(text)
    return '\n'.join(lines)


def calculate_cosine(v1, v2):
    """计算余弦相似度"""
    a = np.array([float(x) for x in v1])
    b = np.array([float(x) for x in v2])
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


# ========== 主流程 ==========

def process_all_categories():
    """为所有分类生成技术路线向量"""

    # 加载数据
    print("加载数据...")
    data_objects = pd.read_excel(NER_PATH, sheet_name='results')
    data_relations = pd.read_excel(RE_PATH, sheet_name='Sheet1')
    with open(CLS_PATH, 'rb') as f:
        dict_doi_classes = pickle.load(f)
    with open(THESAURUS_PATH, 'r', encoding='utf-8') as f:
        thesaurus = json.load(f)

    # RE 的 key 格式：(doi, section_idx, group_idx) — 用字符串匹配
    def doi_in_key(doi, key_str):
        return doi in str(key_str)

    # 不消歧
    thesaurus = []

    all_dois = data_objects['doi'].dropna().unique().tolist()
    print(f"NER 总记录: {len(data_objects)}, 唯一 DOI: {len(all_dois)}")
    print(f"RE 总记录: {len(data_relations)}")
    print(f"分类数据 DOI: {len(dict_doi_classes)}")

    all_tech_routes = []
    total_processed = 0
    total_with_route = 0
    total_embedded = 0
    total_failed = 0

    for category in CATEGORY_KEYWORDS:
        print(f"\n{'=' * 60}")
        print(f"处理分类: {category}")
        print(f"{'=' * 60}")

        # 筛选该分类的 DOI
        dois = []
        for doi in all_dois:
            if isinstance(doi, str) and doi in dict_doi_classes:
                try:
                    classification = dict_doi_classes[doi]['parsed']['classification']
                    if category in classification:
                        dois.append(doi)
                except (KeyError, TypeError):
                    continue

        print(f"  该分类 DOI 数: {len(dois)}")

        if not dois:
            print(f"  跳过（无数据）")
            continue

        cat_processed = 0
        cat_with_route = 0
        cat_embedded = 0

        for i, doi in enumerate(dois):
            if (i + 1) % 100 == 0:
                print(f"  进度: {i + 1}/{len(dois)} (有路线:{cat_with_route}, 已嵌入:{cat_embedded})")

            # 筛选单篇论文的实体和关系
            obj_filtered = data_objects[data_objects['doi'] == doi]
            rel_filtered = data_relations[
                data_relations['key'].apply(lambda k, d=doi: doi_in_key(d, k))
            ]

            if obj_filtered.empty:
                continue

            try:
                network = construct_network(obj_filtered, rel_filtered, thesaurus)
                network_data = nx.node_link_data(network)

                paths = find_important_path(network)
                if not paths:
                    text = ''
                    vector = [0.0] * EMBEDDING_DIM
                else:
                    text = path_to_text(paths, network_data)
                    vector = text_to_vector(text)
                    if any(v != 0 for v in vector):
                        cat_embedded += 1
                        total_embedded += 1
                    else:
                        total_failed += 1

                all_tech_routes.append({
                    'doi': doi,
                    'category': category,
                    'techroutes': text,
                    'vector': vector
                })

                cat_processed += 1
                total_processed += 1
                if text:
                    cat_with_route += 1
                    total_with_route += 1

            except Exception as e:
                print(f"  处理 {doi} 失败: {e}")
                all_tech_routes.append({
                    'doi': doi,
                    'category': category,
                    'techroutes': '',
                    'vector': [0.0] * EMBEDDING_DIM
                })
                continue

        print(f"  分类完成: 处理{cat_processed}, 有路线{cat_with_route}, 已嵌入{cat_embedded}")

    print(f"\n{'=' * 60}")
    print(f"全部分类处理完成")
    print(f"  总数: {len(all_tech_routes)}")
    print(f"  有路线文本: {total_with_route}")
    print(f"  已嵌入: {total_embedded}")
    print(f"  嵌入失败: {total_failed}")

    return all_tech_routes


def compare_with_existing(new_routes):
    """比对已有向量"""
    print(f"\n{'=' * 60}")
    print("比对已有向量...")

    if not Path(EXISTING_TR_PATH).exists():
        print("  无已有数据文件，跳过比对")
        return

    with open(EXISTING_TR_PATH, 'rb') as f:
        existing = pickle.load(f)

    existing_dict = {d['doi']: d for d in existing if any(v != 0 for v in d.get('vector', []))}
    print(f"  已有非零向量: {len(existing_dict)}")

    new_dict = {d['doi']: d for d in new_routes if any(v != 0 for v in d.get('vector', []))}
    print(f"  新生成非零向量: {len(new_dict)}")

    overlap = set(existing_dict.keys()) & set(new_dict.keys())
    print(f"  重叠 DOI: {len(overlap)}")

    if not overlap:
        return

    sims = []
    diffs = []
    for doi in overlap:
        sim = calculate_cosine(existing_dict[doi]['vector'], new_dict[doi]['vector'])
        sims.append(sim)
        if sim < 0.99:
            diffs.append((doi, sim))

    print(f"  平均余弦相似度: {np.mean(sims):.4f}")
    print(f"  最小: {np.min(sims):.4f}, 最大: {np.max(sims):.4f}")
    print(f"  高度一致 (>=0.99): {sum(1 for s in sims if s >= 0.99)}/{len(sims)}")
    if diffs:
        print(f"  不一致 (<0.99): {len(diffs)}")
        for doi, sim in diffs[:5]:
            print(f"    {doi}: {sim:.4f}")


def upload_to_milvus(tech_routes):
    """上传非零向量到 Milvus"""
    print(f"\n{'=' * 60}")
    print("上传到 Milvus...")

    connections.connect(host=MILVUS_HOST, port=MILVUS_PORT, timeout=30)

    # 筛选非零向量
    non_zero = [d for d in tech_routes if any(v != 0 for v in d.get('vector', []))]
    print(f"  非零向量: {len(non_zero)}/{len(tech_routes)}")

    if not non_zero:
        print("  无数据可上传")
        return

    # 删除旧向量
    if utility.has_collection('tech_routes'):
        c = Collection('tech_routes')
        c.load()
        old_count = c.num_entities
        if old_count > 0:
            c.delete('id >= 0')
            c.flush()
            print(f"  已标记删除 {old_count} 条旧记录")
        c.release()

    # 批量插入
    c = Collection('tech_routes')
    batch_size = 100
    for i in range(0, len(non_zero), batch_size):
        batch = non_zero[i:i + batch_size]
        entities = [{
            'vector': d['vector'],
            'doi': d.get('doi', ''),
            'title': d.get('title', ''),
            'techroute_text': d.get('techroutes', ''),
            'category': d.get('category', '')
        } for d in batch]
        c.insert(entities)
        print(f"  已插入 {min(i + batch_size, len(non_zero))}/{len(non_zero)}")

    c.flush()
    c.load()
    print(f"  上传完成，集合记录数: {c.num_entities}")
    c.release()
    connections.disconnect("default")


def save_results(tech_routes):
    """保存结果到本地"""
    output_dir = Path(__file__).parent.parent.parent / "data" / "tech_routes"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "tech_routes_all.pkl"
    with open(output_path, 'wb') as f:
        pickle.dump(tech_routes, f)
    print(f"结果已保存: {output_path}")

    # 统计报告
    report = {
        'total': len(tech_routes),
        'with_text': sum(1 for d in tech_routes if d['techroutes'].strip()),
        'with_vector': sum(1 for d in tech_routes if any(v != 0 for v in d['vector'])),
        'by_category': dict(Counter(d['category'] for d in tech_routes)),
        'with_text_by_category': dict(Counter(
            d['category'] for d in tech_routes if d['techroutes'].strip()
        )),
        'with_vector_by_category': dict(Counter(
            d['category'] for d in tech_routes if any(v != 0 for v in d['vector'])
        ))
    }
    report_path = output_dir / "tech_routes_report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"报告已保存: {report_path}")
    print(f"\n=== 统计 ===")
    print(f"总数: {report['total']}")
    print(f"有文本: {report['with_text']}")
    print(f"有向量: {report['with_vector']}")
    for cat in CATEGORY_KEYWORDS:
        t = report['by_category'].get(cat, 0)
        tv = report['with_vector_by_category'].get(cat, 0)
        print(f"  {cat}: 总计{t}, 有向量{tv}")


if __name__ == '__main__':
    t0 = time.time()

    # 1. 生成全部技术路线向量
    tech_routes = process_all_categories()

    # 2. 比对已有向量
    compare_with_existing(tech_routes)

    # 3. 保存结果
    save_results(tech_routes)

    # 4. 上传到 Milvus
    upload_to_milvus(tech_routes)

    print(f"\n总耗时: {time.time() - t0:.1f}s")
