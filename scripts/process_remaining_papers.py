"""
处理剩余论文的 tech_routes 和 exp_schemes 提取与迁移
基于深度推理方法中的 3A 和 3B 生成逻辑
"""
import sys
import os
import pickle
import json
import time
import logging
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Set, Optional
from openai import OpenAI
from openai import BadRequestError

# 添加 backend 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from pymilvus import MilvusClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIM = 1024

MILVUS_URI = "http://localhost:19530"
MILVUS_DATABASE = "scipdf"

# 数据文件路径
NER_PATH = r"data\results\NER_results_3526_revised.xlsx"
RE_PATH = r"data\results\RE_results_revised.xlsx"
TECHROUTE_PKL = r"data\深度推理方法\technical_route.pkl"
EXPSCHEME_PKL = r"data\深度推理方法\experimemtal_scheme.pkl"
THESAURUS_PATH = r"data\深度推理方法\thesaurus_relation_data.json"

# 输出路径
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
PENDING_EXP_PKL = os.path.join(OUTPUT_DIR, "pending_exp_schemes.pkl")
PENDING_TR_PKL = os.path.join(OUTPUT_DIR, "pending_tech_routes.pkl")

# 速率限制
RATE_LIMIT_DELAY = 0.5
BATCH_SIZE = 100

# 8类实验方案分类
EXPSCHEME_CATEGORIES = ["材料准备", "沉积技术", "工艺参数", "后处理", "表征技术", "系统约束", "模拟分析", "辐照处理"]

# ============================================================
# Milvus 连接
# ============================================================
def connect_milvus():
    client = MilvusClient(uri=MILVUS_URI)
    client.use_database(MILVUS_DATABASE)
    logger.info(f"已连接 Milvus: {MILVUS_URI}/{MILVUS_DATABASE}")
    return client


# ============================================================
# 嵌入向量生成（批量模式）
# ============================================================
# 全局 OpenAI 客户端（复用连接）
_embedding_client = None

def get_embedding_client():
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    return _embedding_client


def batch_text_to_vectors(
    texts: List[str],
    dimensions: int = EMBEDDING_DIM,
    batch_size: int = 10,
) -> List[List[float]]:
    """批量调用 DashScope text-embedding-v4 生成向量，最多25条/请求"""
    if not texts:
        return []

    client = get_embedding_client()
    results = []
    total = len(texts)

    for i in range(0, total, batch_size):
        batch = texts[i : i + batch_size]
        # 过滤空文本，但保持索引
        valid_indices = []
        valid_texts = []
        for j, t in enumerate(batch):
            if t and t.strip():
                valid_indices.append(j)
                valid_texts.append(t)

        # 初始化批次结果为零向量
        batch_vectors = [[0.0] * dimensions for _ in range(len(batch))]

        if valid_texts:
            try:
                response = client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=valid_texts,
                    dimensions=dimensions,
                )
                json_response = json.loads(response.model_dump_json())
                for idx, data_item in enumerate(json_response["data"]):
                    batch_vectors[valid_indices[idx]] = data_item["embedding"]
            except (BadRequestError, Exception) as e:
                logger.warning(f"批量向量化失败 [{i}-{i+len(batch)}]: {e}")
                # 降级为逐个处理
                for idx, text in zip(valid_indices, valid_texts):
                    try:
                        resp = client.embeddings.create(
                            model=EMBEDDING_MODEL,
                            input=[text],
                            dimensions=dimensions,
                        )
                        jr = json.loads(resp.model_dump_json())
                        batch_vectors[idx] = jr["data"][0]["embedding"]
                    except Exception as e2:
                        logger.warning(f"  单个向量化也失败: {e2}")

        results.extend(batch_vectors)

        if (i + batch_size) % 500 == 0 or (i + batch_size >= total):
            logger.info(f"  向量化进度: {min(i+batch_size, total)}/{total}")

        time.sleep(0.2)  # 批次间短暂延迟

    return results


# ============================================================
# 3A: 实验方案生成逻辑
# ============================================================
def parse_parameters(param_str) -> Dict[str, str]:
    """解析参数字符串为字典"""
    if pd.isna(param_str) or str(param_str).strip() in ("", "[]"):
        return {}
    try:
        parsed = json.loads(str(param_str))
        if isinstance(parsed, list):
            result = {}
            for item in parsed:
                if isinstance(item, dict) and "type" in item:
                    result[item["type"]] = item.get("value", "")
            return result
        return {}
    except (json.JSONDecodeError, ValueError):
        return {}


def format_entity_text(row) -> str:
    """格式化单个实体为文本"""
    parts = []
    symbol = str(row.get("symbol", "")) if pd.notna(row.get("symbol")) else ""
    name = str(row.get("name", "")) if pd.notna(row.get("name")) else ""
    value = str(row.get("value", "")) if pd.notna(row.get("value")) else ""
    unit = str(row.get("unit", "")) if pd.notna(row.get("unit")) else ""
    condition = str(row.get("condition", "")) if pd.notna(row.get("condition")) else ""
    parameters = str(row.get("parameters", "")) if pd.notna(row.get("parameters")) else ""

    if symbol:
        parts.append(symbol)

    if name and name != "nan":
        parts.append(f"- {name}")

    val_str = f"{value} {unit}".strip() if value and value != "nan" and value != "[]" else ""
    if val_str:
        parts.append(f": {val_str}")

    cond_str = ""
    if condition and condition != "nan" and condition != "[]":
        try:
            cond_dict = json.loads(condition) if isinstance(condition, str) else condition
            if isinstance(cond_dict, dict):
                cond_parts = [f"{k}: {v}" for k, v in cond_dict.items()]
                cond_str = f"[条件: {', '.join(cond_parts)}]"
        except:
            cond_str = f"[条件: {condition}]"
    if cond_str:
        parts.append(cond_str)

    param_str = ""
    if parameters and parameters != "nan" and parameters != "[]":
        param_dict = parse_parameters(parameters)
        if param_dict:
            param_parts = [f"{k}: {v}" for k, v in param_dict.items()]
            param_str = f"(参数: {', '.join(param_parts)})"
    if param_str:
        parts.append(param_str)

    return " ".join(parts)


def get_entity_category(subtype: str) -> str:
    """根据 subtype 映射到8类实验方案分类"""
    subtype_mapping = {
        "Material_Fabrication": "材料准备",
        "Substrate_Preparation": "材料准备",
        "Target_Preparation": "材料准备",
        "Deposition_Techniques": "沉积技术",
        "Coating_Method": "沉积技术",
        "Deposition": "沉积技术",
        "Process_Parameters": "工艺参数",
        "Processing_Conditions": "工艺参数",
        "Post_Processing": "后处理",
        "Annealing": "后处理",
        "Heat_Treatment": "后处理",
        "Oxygenation": "后处理",
        "Irradiation": "辐照处理",
        "Characterization": "表征技术",
        "Measurement": "表征技术",
        "System_Constraints": "系统约束",
        "Simulation": "模拟分析",
    }

    if subtype in subtype_mapping:
        return subtype_mapping[subtype]

    subtype_lower = str(subtype).lower()
    if "material" in subtype_lower and "preparation" not in subtype_lower:
        return "材料准备"
    if "deposition" in subtype_lower:
        return "沉积技术"
    if "parameter" in subtype_lower or "condition" in subtype_lower:
        return "工艺参数"
    if "anneal" in subtype_lower or "post" in subtype_lower or "heat" in subtype_lower:
        return "后处理"
    if "irradiat" in subtype_lower:
        return "辐照处理"
    if "character" in subtype_lower or "measur" in subtype_lower:
        return "表征技术"
    if "constraint" in subtype_lower or "system" in subtype_lower:
        return "系统约束"
    if "simulat" in subtype_lower:
        return "模拟分析"

    return "材料准备"


def dataframe_to_expscheme(INPUT_data: pd.DataFrame) -> str:
    """将论文的制造工艺实体转换为结构化实验方案文本"""
    if INPUT_data.empty:
        return ""

    doi_set = set(INPUT_data["doi"].dropna().unique())
    if len(doi_set) != 1:
        return ""

    rows = INPUT_data[INPUT_data["type"] == "Manufacturing_Process_Chain"]

    categorized = {cat: [] for cat in EXPSCHEME_CATEGORIES}
    for _, row in rows.iterrows():
        subtype = str(row.get("subtype", ""))
        category = get_entity_category(subtype)
        text = format_entity_text(row)
        if text.strip():
            categorized[category].append(text)

    lines = []
    for cat in EXPSCHEME_CATEGORIES:
        items = categorized[cat]
        if items:
            lines.append(f'\n "{cat}"')
            for item in items:
                lines.append(f"  • {item}")

    return "\n".join(lines).strip()


def build_exp_schemes_for_dois(
    entities_df: pd.DataFrame,
    doi_list: List[str],
) -> List[Dict[str, Any]]:
    """为指定 DOI 列表构建实验方案数据库（批量嵌入）"""
    mfg_entities = entities_df[entities_df["type"] == "Manufacturing_Process_Chain"]

    # 第一阶段：生成所有文本
    logger.info("  生成实验方案文本...")
    texts_and_dois = []
    for idx, doi in enumerate(doi_list):
        paper_entities = mfg_entities[mfg_entities["doi"] == doi]
        expscheme_text = dataframe_to_expscheme(paper_entities)
        texts_and_dois.append((doi, expscheme_text))

        if (idx + 1) % 500 == 0:
            logger.info(f"  文本生成: [{idx+1}/{len(doi_list)}]")

    # 第二阶段：批量向量化
    logger.info("  批量向量化...")
    all_texts = [t for _, t in texts_and_dois]
    all_vectors = batch_text_to_vectors(all_texts)

    # 组装结果
    results = []
    for (doi, text), vector in zip(texts_and_dois, all_vectors):
        results.append({
            "doi": doi,
            "expscheme": text,
            "vector": vector,
        })

    non_empty = sum(1 for r in results if r["expscheme"].strip())
    logger.info(f"exp_scheme 生成完成: {non_empty}/{len(doi_list)} 有文本内容")
    return results


# ============================================================
# 3B: 技术路线生成逻辑
# ============================================================
VALID_ENTITY_TYPES = [
    "Manufacturing_Process_Chain", "Material",
    "Microstructural_Hierarchy", "Transport_Behavior",
]

VALID_RELATION_TYPES = {
    ("Material", "has", "Microstructural_Hierarchy"),
    ("Material", "undergoes", "Manufacturing_Process_Chain"),
    ("Manufacturing_Process_Chain", "produces", "Material"),
    ("Manufacturing_Process_Chain", "controls", "Microstructural_Hierarchy"),
    ("Microstructural_Hierarchy", "affects", "Transport_Behavior"),
    ("Material", "determines", "Transport_Behavior"),
    ("Transport_Behavior", "affects", "Transport_Behavior"),
}


def load_thesaurus(path: str) -> List[Dict]:
    """加载实体同义词表"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def construct_network_from_dataframe(
    entities_df: pd.DataFrame,
    relations_df: pd.DataFrame,
    thesaurus: List[Dict],
) -> Any:
    """从实体和关系构建 NetworkX MultiDiGraph"""
    import networkx as nx

    # 实体过滤和消歧
    entity_list = entities_df[["symbol", "type"]].drop_duplicates().to_dict(orient="records")
    valid_entities = [e for e in entity_list if e["type"] in VALID_ENTITY_TYPES]

    # 同义词消歧
    synonym_map = {}
    for t in thesaurus:
        key = (t["symbol"].lower(), t["type"])
        synonym_map[key] = t["thesaurus"]

    for entity in valid_entities:
        key = (entity["symbol"].lower(), entity["type"])
        if key in synonym_map:
            entity["symbol"] = synonym_map[key]

    # 创建节点索引
    symbol_to_nodes = {}
    for entity in valid_entities:
        sym = entity["symbol"]
        etype = entity["type"]
        if sym not in symbol_to_nodes:
            symbol_to_nodes[sym] = []
        symbol_to_nodes[sym].append(etype)

    # 构建图
    G = nx.MultiDiGraph()
    node_index = 0
    node_map = {}

    for entity in valid_entities:
        key = (entity["symbol"], entity["type"])
        if key not in node_map:
            node_map[key] = node_index
            G.add_node(node_index, object_symbol=entity["symbol"], object_type=entity["type"])
            node_index += 1

    # 关系处理
    for _, rel in relations_df.iterrows():
        s_type = rel["source_type"]
        s_entity = rel["source_entity"]
        t_type = rel["target_type"]
        t_entity = rel["target_entity"]
        r_type = rel["relation_type"]

        # 同义词消歧
        s_key = (s_entity.lower(), s_type)
        if s_key in synonym_map:
            s_entity = synonym_map[s_key]
        t_key = (t_entity.lower(), t_type)
        if t_key in synonym_map:
            t_entity = synonym_map[t_key]

        # 有效性检查
        if s_type not in VALID_ENTITY_TYPES or t_type not in VALID_ENTITY_TYPES:
            continue
        if (s_type, r_type, t_type) not in VALID_RELATION_TYPES:
            continue

        s_node_key = (s_entity, s_type)
        t_node_key = (t_entity, t_type)

        if s_node_key in node_map and t_node_key in node_map:
            G.add_edge(
                node_map[s_node_key], node_map[t_node_key],
                relation_type=r_type,
                source_type=s_type,
                target_type=t_type,
            )

    return G


def find_important_path(
    G: Any,
    set_sinks: Set[str] = None,
    set_keys: Set[str] = None,
) -> List[List[int]]:
    """查找从源节点到汇节点的关键路径"""
    import networkx as nx

    if set_sinks is None:
        set_sinks = {"jc", "ic", "critical_current"}
    if set_keys is None:
        set_keys = {"pinning"}

    if G.number_of_nodes() == 0:
        return []

    # 源节点：入度为0
    G_rev = G.reverse()
    sources = [n for n in G.nodes() if len(G_rev.adj[n]) == 0]
    if not sources:
        sources = [list(G.nodes())[0]]

    # 汇节点：包含汇关键词
    sinks = []
    for n in G.nodes():
        sym = G.nodes[n].get("object_symbol", "").lower()
        if any(sink in sym for sink in set_sinks):
            sinks.append(n)

    # 关键节点：包含关键关键词
    key_nodes = set()
    for n in G.nodes():
        sym = G.nodes[n].get("object_symbol", "").lower()
        if any(k in sym for k in set_keys):
            key_nodes.add(n)

    if not sinks:
        return []

    # 查找所有从源到汇的简单路径，必须经过关键节点
    all_paths = []
    for source in sources:
        for sink in sinks:
            try:
                paths = list(nx.all_simple_paths(G, source, sink, cutoff=15))
                for path in paths:
                    if key_nodes:
                        if any(n in key_nodes for n in path):
                            all_paths.append(path)
                    else:
                        all_paths.append(path)
            except nx.NetworkXNoPath:
                continue

    return all_paths


def path_to_text(paths: List[List[int]], G: Any) -> str:
    """将路径列表转换为可读文本"""
    if not paths:
        return ""

    texts = []
    for idx, path in enumerate(paths):
        if len(path) < 2:
            continue

        parts = []
        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            u_sym = G.nodes[u].get("object_symbol", "?")
            v_sym = G.nodes[v].get("object_symbol", "?")

            # 获取关系类型
            edge_data = G.get_edge_data(u, v)
            if edge_data:
                rel_type = list(edge_data.values())[0].get("relation_type", "-")
            else:
                rel_type = "-"

            if i == 0:
                parts.append(u_sym)
            parts.append(f"- {rel_type} - {v_sym}")

        if parts:
            texts.append(f"Tech Route {idx+1}: {' '.join(parts)}")

    return "\n".join(texts)


def build_tech_routes_for_dois(
    entities_df: pd.DataFrame,
    relations_df: pd.DataFrame,
    doi_list: List[str],
    thesaurus: List[Dict],
) -> List[Dict[str, Any]]:
    """为指定 DOI 列表构建技术路线数据库（批量嵌入）"""
    # 第一阶段：生成所有文本
    logger.info("  生成技术路线文本和知识图谱...")
    texts_and_dois = []
    total = len(doi_list)

    for idx, doi in enumerate(doi_list):
        paper_entities = entities_df[entities_df["doi"] == doi]
        paper_relations = relations_df[relations_df["key"].str.contains(doi, na=False)]

        if paper_entities.empty or paper_relations.empty:
            texts_and_dois.append((doi, ""))
        else:
            try:
                G = construct_network_from_dataframe(paper_entities, paper_relations, thesaurus)
                paths = find_important_path(G)
                techroute_text = path_to_text(paths, G)
                texts_and_dois.append((doi, techroute_text))
            except Exception as e:
                logger.warning(f"DOI={doi} 技术路线生成失败: {e}")
                texts_and_dois.append((doi, ""))

        if (idx + 1) % 500 == 0:
            non_empty = sum(1 for _, t in texts_and_dois if t.strip())
            logger.info(f"  文本生成: [{idx+1}/{total}], 有效路径: {non_empty}")

    # 第二阶段：批量向量化
    logger.info("  批量向量化...")
    all_texts = [t for _, t in texts_and_dois]
    all_vectors = batch_text_to_vectors(all_texts)

    # 组装结果
    results = []
    for (doi, text), vector in zip(texts_and_dois, all_vectors):
        results.append({
            "doi": doi,
            "techroutes": text,
            "vector": vector,
        })

    non_empty = sum(1 for r in results if r["techroutes"].strip())
    logger.info(f"tech_route 生成完成: {non_empty}/{total} 有路径文本")
    return results


# ============================================================
# Milvus 插入
# ============================================================
def insert_to_milvus(
    client: MilvusClient,
    collection_name: str,
    data: List[Dict[str, Any]],
    data_type: str,
) -> int:
    """批量插入数据到 Milvus"""
    total = len(data)
    inserted = 0
    current_time = int(time.time())

    for i in range(0, total, BATCH_SIZE):
        batch = data[i : i + BATCH_SIZE]
        batch_records = []

        for record in batch:
            doi = str(record.get("doi", ""))[:256]

            if data_type == "exp_scheme":
                text = str(record.get("expscheme", ""))
                text_field = "expscheme_text"
            else:
                text = str(record.get("techroutes", ""))
                text_field = "techroute_text"

            if text:
                text_bytes = text.encode("utf-8")
                if len(text_bytes) > 4096:
                    text = text_bytes[:4096].decode("utf-8", errors="ignore")

            vector = record.get("vector", [])
            if not isinstance(vector, list) or len(vector) == 0:
                vector = [0.0] * EMBEDDING_DIM
            elif len(vector) < EMBEDDING_DIM:
                vector = vector + [0.0] * (EMBEDDING_DIM - len(vector))
            elif len(vector) > EMBEDDING_DIM:
                vector = vector[:EMBEDDING_DIM]

            record_dict = {
                "doi": doi,
                "title": "",
                text_field: text,
                "embedding": vector,
                "embedding_time": current_time,
            }
            # exp_schemes 需要 categories_json 字段
            if data_type == "exp_scheme":
                record_dict["categories_json"] = "[]"

            batch_records.append(record_dict)

        try:
            result = client.insert(
                collection_name=collection_name,
                data=batch_records,
            )
            inserted += result.get("insert_count", len(batch_records))
            logger.info(f"  [{data_type}] Milvus 插入: {min(i+BATCH_SIZE, total)}/{total}")
        except Exception as e:
            logger.error(f"  [{data_type}] 批量插入失败: {e}")

    return inserted


# ============================================================
# 主流程
# ============================================================
def main():
    logger.info("=" * 60)
    logger.info("剩余论文处理脚本")
    logger.info("=" * 60)

    # 1. 加载数据
    logger.info("\n[1/6] 加载源数据...")
    ner_df = pd.read_excel(NER_PATH, sheet_name="results")
    re_df = pd.read_excel(RE_PATH)
    all_dois = sorted(set(ner_df["doi"].dropna().unique()))
    logger.info(f"NER 论文数: {len(all_dois)}")

    # 2. 确定剩余论文
    logger.info("\n[2/6] 确定剩余论文...")
    with open(TECHROUTE_PKL, "rb") as f:
        existing_tr = pickle.load(f)
    existing_dois = set(d["doi"] for d in existing_tr)
    pending_dois = [doi for doi in all_dois if doi not in existing_dois]
    logger.info(f"已处理: {len(existing_dois)}, 剩余: {len(pending_dois)}")

    if not pending_dois:
        logger.info("没有剩余论文需要处理！")
        return

    # 3. 加载同义词表
    logger.info("\n[3/6] 加载同义词表...")
    thesaurus = load_thesaurus(THESAURUS_PATH)
    logger.info(f"同义词条目: {len(thesaurus)}")

    # 4. 生成 exp_schemes
    logger.info(f"\n[4/6] 生成实验方案 (exp_schemes) - {len(pending_dois)} 篇论文...")
    pending_exp = build_exp_schemes_for_dois(ner_df, pending_dois)
    with open(PENDING_EXP_PKL, "wb") as f:
        pickle.dump(pending_exp, f)
    logger.info(f"exp_scheme 结果已保存: {PENDING_EXP_PKL}")

    # 5. 生成 tech_routes
    logger.info(f"\n[5/6] 生成技术路线 (tech_routes) - {len(pending_dois)} 篇论文...")
    pending_tr = build_tech_routes_for_dois(ner_df, re_df, pending_dois, thesaurus)
    with open(PENDING_TR_PKL, "wb") as f:
        pickle.dump(pending_tr, f)
    logger.info(f"tech_route 结果已保存: {PENDING_TR_PKL}")

    # 6. 插入 Milvus
    logger.info("\n[6/6] 插入 Milvus...")
    client = connect_milvus()

    # 统计当前状态
    for col in ["exp_schemes", "tech_routes"]:
        stats = client.get_collection_stats(col)
        logger.info(f"  {col} 当前记录数: {stats.get('row_count', 0)}")

    # 插入 exp_schemes
    n_exp = insert_to_milvus(client, "exp_schemes", pending_exp, "exp_scheme")
    logger.info(f"exp_schemes 插入: {n_exp} 条")

    # 插入 tech_routes
    n_tr = insert_to_milvus(client, "tech_routes", pending_tr, "tech_route")
    logger.info(f"tech_routes 插入: {n_tr} 条")

    # 最终统计
    logger.info("\n" + "=" * 60)
    logger.info("处理完成！最终统计：")
    for col in ["exp_schemes", "tech_routes"]:
        stats = client.get_collection_stats(col)
        logger.info(f"  {col}: {stats.get('row_count', 0)} 条")

    # 合并本地 .pkl
    merged_tr = existing_tr + pending_tr
    with open(TECHROUTE_PKL, "wb") as f:
        pickle.dump(merged_tr, f)
    logger.info(f"已更新 technical_route.pkl: {len(merged_tr)} 条")

    with open(EXPSCHEME_PKL, "rb") as f:
        existing_exp = pickle.load(f)
    merged_exp = existing_exp + pending_exp
    with open(EXPSCHEME_PKL, "wb") as f:
        pickle.dump(merged_exp, f)
    logger.info(f"已更新 experimemtal_scheme.pkl: {len(merged_exp)} 条")

    client.close()
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
