# Step3: 向量服务开发 - 详细计划

> 预计周期: 2 周 | 状态: 待开始 | 前置依赖: Step2

---

## 一、任务清单

### 3.1 Milvus Collection 初始化

**目标**：创建 Milvus Collections 初始化脚本

**文件**：`scripts/init_milvus.py`

**参考来源**：架构设计文档 Milvus Collection 设计

**Collections**：

| Collection | 字段 | 索引 |
|------------|------|------|
| `paper_vectors` | paper_id, user_id, vector_type, embedding(768), metadata | IVF_FLAT, COSINE |
| `entity_vectors` | entity_id, paper_id, entity_type, entity_name, embedding(768), source_sentence | IVF_FLAT |
| `tech_route_vectors` | profile_id, paper_id, profile_text, embedding(768), domain | HNSW |

**初始化脚本**：
```python
from pymilvus import MilvusClient, DataType

def init_collections():
    client = MilvusClient(uri=settings.MILVUS_URI)

    # 创建 paper_vectors
    if not client.has_collection("paper_vectors"):
        client.create_collection(...)

    # 创建 entity_vectors
    if not client.has_collection("entity_vectors"):
        client.create_collection(...)

    # 创建 tech_route_vectors
    if not client.has_collection("tech_route_vectors"):
        client.create_collection(...)
```

---

### 3.2 Embedding 服务开发

**目标**：开发文本向量化服务

**文件**：`backend/app/services/embedding_service.py`

**参考来源**：v2 `deep-reasoning-methods/base_methods.py` VectorTools

**核心功能**：

| 方法 | 功能 |
|------|------|
| `embed_text(text)` | 单文本向量化 |
| `embed_batch(texts)` | 批量文本向量化（异步并行） |
| `embed_paper_abstract(paper)` | 向量化论文摘要 |
| `embed_paper_full_text(paper)` | 向量化论文全文 |
| `embed_entity(entity_name, context)` | 向量化实体 |

**API 配置**：
- 支持 OpenAI / 通义千问 embedding API
- 默认维度 768 或 1024
- 异步批量处理（控制并发数）

---

### 3.3 Vector 服务开发

**目标**：开发 Milvus CRUD 服务

**文件**：`backend/app/services/vector_service.py`

**参考来源**：架构设计文档向量服务设计

**核心方法**：

| 方法 | 功能 |
|------|------|
| `insert_paper_vector()` | 插入论文向量 |
| `search_similar_papers()` | 检索相似论文 |
| `insert_entity_vector()` | 插入实体向量 |
| `search_similar_entities()` | 检索相似实体 |
| `insert_tech_route_vector()` | 插入技术路线向量 |
| `search_similar_tech_routes()` | 检索相似技术路线 |
| `delete_paper_vectors()` | 删除论文相关向量 |

**检索参数**：
- top_k: 返回数量
- threshold: 相似度阈值
- filter_expr: 过滤表达式

---

### 3.4 向量存储接口

**目标**：创建向量存储 API

**文件**：`backend/app/api/v1/vector.py`

**API 接口**：

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/vectors/papers` | POST | 存储论文向量 |
| `/api/v1/vectors/papers/search` | POST | 搜索相似论文 |
| `/api/v1/vectors/entities` | POST | 存储实体向量 |
| `/api/v1/vectors/entities/search` | POST | 搜索相似实体 |
| `/api/v1/vectors/techroutes` | POST | 存储技术路线向量 |
| `/api/v1/vectors/techroutes/search` | POST | 搜索相似技术路线 |

---

### 3.5 NER 向量存储集成

**目标**：在 NER 服务中集成向量存储

**改动文件**：`backend/app/services/ner_service.py`

**集成逻辑**：
- NER 完成后自动向量化实体
- 存储到 Milvus entity_vectors
- 支持实体相似度检索

---

### 3.6 论文向量存储集成

**目标**：在 PDF 服务中集成向量存储

**改动文件**：`backend/app/services/pdf_service.py`

**集成逻辑**：
- PDF 解析完成后向量化摘要
- 存储到 Milvus paper_vectors
- 支持论文相似度检索

---

## 二、执行顺序

1. 创建 `scripts/init_milvus.py`
2. 运行初始化脚本创建 Collections
3. 创建 `backend/app/services/embedding_service.py`
4. 创建 `backend/app/services/vector_service.py`
5. 创建 `backend/app/api/v1/vector.py`
6. 修改 NER 服务集成向量存储
7. 修改 PDF 服务集成向量存储
8. 测试向量存储和检索

---

## 三、检查标准

| 检查项 | 标准 |
|--------|------|
| Milvus Collections | 3 个 Collection 创建成功 |
| 向量化 | 单文本向量化返回正确维度向量 |
| 批量向量化 | 批量向量化正常完成 |
| 向量存储 | 数据写入 Milvus 成功 |
| 相似度检索 | 检索返回正确结果 |
| 论文向量集成 | PDF 解析后自动存储向量 |
| 实体向量集成 | NER 完成后自动存储向量 |

---

## 四、参考文件列表

| 来源 | v3 目标位置 |
|------|------------|
| 架构设计文档 Milvus Collection 设计 | `scripts/init_milvus.py` |
| 架构设计文档 Embedding 服务设计 | `backend/app/services/embedding_service.py` |
| 架构设计文档 Vector 服务设计 | `backend/app/services/vector_service.py` |
| v2 VectorTools | 参考向量化逻辑 |

---

*Step3 完成后进入 Step4: 前端开发*