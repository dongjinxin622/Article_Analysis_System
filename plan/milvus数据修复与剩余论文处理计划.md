# Milvus 数据修复与剩余论文处理计划

## 一、项目背景与现状

### 1.1 数据来源

| 数据 | 文件 | 规模 |
|---|---|---|
| 命名实体识别 | `NER_results_3526_revised.xlsx` | 3,522 篇论文，341,617 行实体 |
| 关系抽取 | `RE_results_revised.xlsx` | 3,518 篇论文，217,119 行关系 |
| 论文分类 | `cls_final.pkl` | DOI→技术路线分类（PLD/MOD/MOCVD等） |
| 实体同义词表 | `thesaurus_relation_data.json` | 548 条同义映射 |

### 1.2 原始生成数据（.pkl 文件）

| 文件 | 记录数 | 文本非空 | 向量非空 |
|---|---|---|---|
| `technical_route.pkl` | 1,950 | **434** | 1,950 |
| `experimemtal_scheme.pkl` | 1,950 | **1,950** | 1,950 |

### 1.3 Milvus 现状（`scipdf` 数据库）

| Collection | 记录数 | 文本非空 | 问题 |
|---|---|---|---|
| `tech_routes` | 1,950 | 434 | 与源数据一致（正确） |
| `exp_schemes` | 1,950 | **0** | **全部丢失**（应为1,950条） |
| `paper_embeddings` | 0 | — | 未使用 |
| `entity_embeddings` | 0 | — | 未使用 |
| `sentence_embeddings` | 0 | — | 未使用 |

### 1.4 剩余论文

- NER 覆盖 3,522 篇，已处理 1,950 篇
- **剩余 1,572 篇**需要提取 tech_routes 和 exp_schemes
- 其中 1,568 篇同时具有 NER + RE 数据（4 篇仅有 NER 无 RE）

---

## 二、任务目标

### 任务一：修复 exp_schemes 文本数据

将 `experimemtal_scheme.pkl` 中的 1,950 条实验方案文本重新迁移到 Milvus。

### 任务二：提取剩余论文的技术路线和实验方案

对 1,572 篇剩余论文，基于 NER 和 RE 数据生成：
- 实验方案向量（插入 Milvus `exp_schemes`）
- 技术路线向量（插入 Milvus `tech_routes`）

### 技术约束

- 向量模型：`text-embedding-v4`，维度 1024
- 向量数据库：Milvus `scipdf`，云端 8.147.69.101:19530
- API 端点：`https://dashscope.aliyuncs.com/compatible-mode/v1`
- 复用以 `深度推理方法/` 目录中的生成逻辑

---

## 三、实施方案

### 3.1 任务一：修复 exp_schemes（预计时间：10分钟）

#### 步骤 1.1：从 .pkl 读取数据
- 读取 `深度推理方法/experimemtal_scheme.pkl`（1,950条，每条 `{doi, expscheme, vector}`）

#### 步骤 1.2：清空并重建 Milvus exp_schemes
- 删除 Milvus `exp_schemes` 中全部现有记录：`client.delete(collection_name="exp_schemes", filter="id >= 0")`
- 从 .pkl 批量重新插入，映射关系：
  ```
  doi        → doi
  expscheme  → expscheme_text (按字节截断4096)
  vector     → embedding (padding/truncate到1024维)
  title      → "" (空，源数据无此字段)
  categories → "[]" (源数据无分类信息)
  ```

#### 步骤 1.3：验证
- 查询 `exp_schemes` 中 `expscheme_text != ""` 的记录数，预期 **1,950**
- 抽样展示 3-5 条文本内容确认可读

#### 涉及文件
- 新建脚本：`scripts/fix_exp_schemes_migration.py`

---

### 3.2 任务二：处理剩余论文（预计时间：数小时，取决于API速率）

#### 步骤 2.1：确定剩余论文列表
- 从 `NER_results_3526_revised.xlsx` 提取全部 3,522 个 DOI
- 从 `technical_route.pkl` 提取已处理的 1,950 个 DOI
- 计算差集，得到 1,572 个待处理 DOI
- 保存到 `data/pending_dois.txt`

#### 步骤 2.2：准备剩余论文的输入数据
- 从 `NER_results_3526_revised.xlsx`（`results` 表）筛选剩余 DOI 的实体数据
- 从 `RE_results_revised.xlsx` 筛选剩余 DOI 的关系数据
- 从 `cls_final.pkl` 获取剩余论文的分类信息
- 保存中间数据到 `data/pending_ner_data.pkl`、`data/pending_re_data.pkl`

#### 步骤 2.3：生成 exp_scheme（复用 3A 逻辑）
- 对每篇剩余论文：
  1. 筛选 `type == 'Manufacturing_Process_Chain'` 的实体
  2. 调用 `dataframe_to_expscheme()` 生成 8 类结构化文本
  3. 调用 `Qianwen_text2vector()` 生成 1024 维向量
- 输出：`data/pending_exp_schemes.pkl`（列表，每条 `{doi, expscheme, vector}`）

#### 步骤 2.4：生成 tech_route（复用 3B 逻辑）
- 对每篇剩余论文：
  1. 筛选有效实体类型（4 种）和关系类型（7 种）
  2. 使用 `construct_network_from_dataframe()` 构建 NetworkX 知识图谱
  3. 调用 `find_important_path()` 提取源→pinning→Jc 关键路径
  4. 调用 `path_to_text()` 生成路线文本
  5. 调用 `Qianwen_text2vector()` 生成 1024 维向量
- 注意：仅约 434/1950 ≈ 22% 的论文能提取出完整路径，剩余论文将存储空文本+零向量
- 输出：`data/pending_tech_routes.pkl`（列表，每条 `{doi, techroutes, vector}`）

#### 步骤 2.5：插入 Milvus
- 将新生成的 exp_schemes 和 tech_routes 批量插入对应 Collection
- 批量大小：100 条/批
- 插入时包含当前时间戳 `embedding_time`

#### 步骤 2.6：更新本地 .pkl 文件
- 将新数据合并到 `technical_route.pkl` 和 `experimemtal_scheme.pkl`

#### 涉及文件
- 新建脚本：`scripts/process_remaining_papers.py`
- 复用的核心逻辑来源：
  - `深度推理方法/3A_expscheme_extraction.py`：exp_scheme 生成和向量化
  - `深度推理方法/3B_techroute_extraction.py`：tech_route 生成和向量化
  - `深度推理方法/thesaurus_relation_data.json`：实体同义词表

---

## 四、关键技术细节

### 4.1 嵌入模型配置

```python
EMBEDDING_MODEL = "text-embedding-v4"
EMBEDDING_DIM = 1024
API_KEY = "sk-93b1c3640da64870b81f430e1495f73e"
BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

### 4.2 Milvus 连接配置

```python
MILVUS_URI = "http://8.147.69.101:19530"
MILVUS_DATABASE = "scipdf"
COLLECTION_EXP_SCHEMES = "exp_schemes"
COLLECTION_TECH_ROUTES = "tech_routes"
```

### 4.3 exp_schemes Collection Schema

| 字段 | 类型 | 约束 |
|---|---|---|
| id | INT64 | 主键，自增 |
| doi | VARCHAR(256) | |
| title | VARCHAR(512) | |
| expscheme_text | VARCHAR(4096) | 按 UTF-8 字节截断 |
| categories_json | VARCHAR(1024) | |
| embedding | FLOAT_VECTOR(1024) | COSINE 索引 |
| embedding_time | INT64 | |

### 4.4 tech_routes Collection Schema

| 字段 | 类型 | 约束 |
|---|---|---|
| id | INT64 | 主键，自增 |
| doi | VARCHAR(256) | |
| title | VARCHAR(512) | |
| techroute_text | VARCHAR(4096) | 按 UTF-8 字节截断 |
| embedding | FLOAT_VECTOR(1024) | COSINE 索引 |
| embedding_time | INT64 | |

### 4.5 8 类实验方案分类（exp_scheme）

`材料准备 → 沉积技术 → 工艺参数 → 后处理 → 表征技术 → 系统约束 → 模拟分析 → 辐照处理`

### 4.6 技术路线关键路径（tech_route）

- 源节点：入度为零的节点
- 汇节点：`symbol` 匹配 `{jc, ic, critical_current}`
- 关键节点：`symbol` 匹配 `{pinning}`
- 约束：路径必须经过至少一个关键节点

---

## 五、验证方案

### 5.1 任务一验证
- [ ] `exp_schemes` 中 `expscheme_text != ""` 的记录数 = 1,950
- [ ] 随机抽查 5 条文本内容可正常阅读
- [ ] 向量维度正确（1024）

### 5.2 任务二验证
- [ ] `tech_routes` 总记录数 = 1,950 + 新插入数
- [ ] `exp_schemes` 总记录数 = 1,950 + 新插入数
- [ ] 新 `tech_routes` 中 `techroute_text` 非空比例约 22%
- [ ] 新 `exp_schemes` 中 `expscheme_text` 全部非空
- [ ] 所有新记录的向量维度 = 1024
- [ ] 随机抽查可正常阅读

### 5.3 验证脚本
- 运行 `scripts/query_milvus.py`（已有的查询脚本）查看最终统计

---

## 六、风险与注意事项

1. **API 速率限制**：DashScope embedding API 有速率限制，脚本需加入速率控制（20 条/秒，参考原脚本的 `rate_limit_delay=20`）
2. **内存占用**：NER 数据 341,617 行、RE 数据 217,119 行，需注意 DataFrame 操作的内存管理
3. **网络稳定性**：云端 Milvus 和 DashScope API 均需网络连接，脚本需具备重试机制
4. **4 篇无 RE 的论文**：仅能生成 exp_scheme，无法生成 tech_route（tech_route 需要 RE 数据构建图谱）
5. **cls_final.pkl 缺失**：原始脚本使用分类筛选论文（仅处理 PLD 类），剩余论文需确认分类数据可用性；若不可用，可跳过分类筛选，直接处理全部剩余论文

---

## 七、交付物

| 文件 | 说明 |
|---|---|
| `scripts/fix_exp_schemes_migration.py` | 任务一修复脚本 |
| `scripts/process_remaining_papers.py` | 任务二处理脚本 |
| `.claude/operations-log.md` | 操作日志 |
| `.claude/verification-report.md` | 验证报告 |
