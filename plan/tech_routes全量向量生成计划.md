# tech_routes 全量向量生成计划

## 一、背景

当前 `tech_routes` Milvus 集合中 1950 条向量全为零，需重新生成。根源是 v2 阶段只处理了分类为 PLD 的论文，且其中仅 432 条有有效向量。

## 二、现状分析

### 2.1 已有数据

| 文件 | 记录数 | 说明 |
|------|--------|------|
| `cls_final.pkl` | 2898 | 论文分类数据（DOI → 分类标签） |
| `entity_network.pkl` | 1950 | 仅 PLD 分类的实体关系网络 |
| `technical_route.pkl` | 1950 | PLD 的技术路线文本+向量（434有文本/432有向量） |
| v3 数据库 NER | 18 | 当日处理的新论文 |
| v3 数据库 RE | 18 | 当日处理的新论文 |

### 2.2 分类分布（cls_final.pkl）

| 分类 | 论文数 |
|------|--------|
| PLD | 1977 |
| Other | 1359 |
| MOD | 872 |
| MOCVD | 337 |
| **合计** | **2898**（多标签，一篇论文可分属多类） |

### 2.3 关键缺口

- PLD 论文的 `entity_network` 已构建（1950），但 tech_route 文本仅 434 条有内容
- 非 PLD 论文（MOD/MOCVD/Other）的 `entity_network` **从未构建**
- 构建 entity_network 所需的原始 NER/RE 数据（`NER_results_3526_revised.xlsx`、`RE_results_revised.xlsx`）在当前机器上不存在

## 三、处理方案

### 3.1 方案 A：仅处理已有 entity_network 的 1950 篇 PLD 论文（立即可执行）

**流程**：
1. 读取 `entity_network.pkl`（1950 条）
2. 对每条记录用 `find_important_path` 查找关键路径
3. 用 `path_to_text` 文本化路径
4. 用 `text-embedding-v4` 生成 1024 维向量
5. 上传到 Milvus `tech_routes` 集合

**预期结果**：
- 有路径的论文（约 434 篇）：生成向量
- 无路径的论文（约 1516 篇）：文本为空，向量为零（与 v2 一致）
- 新增向量与已有 432 条的余弦相似度应 ≥ 0.99（同模型、同文本）

**文件**：新增 `backend/scripts/generate_tech_route_vectors.py`

**耗时**：约 434 次 embedding API 调用，~7 分钟（1s/条，支持批量）

### 3.2 方案 B：扩展至全部 2898 篇论文（需要源数据）

**前提**：获取 `NER_results_3526_revised.xlsx` 和 `RE_results_revised.xlsx`

**流程**：
1. 读取 NER + RE 原始数据
2. 按分类标签分别构建 entity_network（PLD/MOD/MOCVD/Other）
3. 执行与方案 A 相同的路径提取、文本化、向量化流程
4. 合并后上传到 Milvus

**预期结果**：覆盖全部 2898 篇

**风险**：源数据文件在另一台机器，可能需要迁移

### 3.3 方案 C：混合方案

先执行方案 A（立即可用），源数据到位后再补充方案 B。

## 四、实施步骤（方案 A）

### 步骤 1：编写脚本 `generate_tech_route_vectors.py`

- 位置：`backend/scripts/generate_tech_route_vectors.py`
- 复用 v2 项目的 `find_important_path`、`path_to_text` 逻辑
- 使用 v3 项目的 `.env` 配置（API_KEY、BASE_URL）
- 使用 `text-embedding-v4` 模型（1024维）

### 步骤 2：比对已有向量

- 对 432 条已有有效向量的记录，重新生成并与原向量计算余弦相似度
- 相似度≥0.99 视为一致
- 记录不一致的情况

### 步骤 3：上传到 Milvus

- 先删除 `tech_routes` 中旧向量（id >= 0 或重建集合）
- 批量插入新生成的向量
- 验证随机搜索返回正常距离

### 步骤 4：验证

- 在综合分析页面执行一次完整分析
- 确认相似论文的相似度显示正常（非 0%）

## 五、风险与注意事项

1. `text-embedding-v4` 是否与 v2 时期的模型完全一致？—— API 名称相同，但模型可能有版本更新
2. 1516 条无路径的论文无法生成向量，需要在报告中说明
3. 向量比对基准是 v2 生成的 432 条，新生成的应与之接近
