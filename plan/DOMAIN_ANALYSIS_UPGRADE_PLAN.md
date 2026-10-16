# 领域分析与论文对比模块升级计划（最终版）

## 一、数据现状分析

### 1.1 v2 SQLite数据库（rebco.db）- 完整历史数据

```
路径: Article_Analysis_System_v2/data/REBCO_database/rebco.db
大小: 184MB

表数据量:
- tech_routes: 1950条 (技术路线 + 向量BLOB)
- exp_schemes: 1950条 (实验方案 + 向量BLOB)
- jc_indices: 42132条 (Jc指标数据)
- jc_indices_raw: 386712条 (Jc原始数据)
```

### 1.2 云端MySQL（localhost）- 数据迁移不完整

```
数据库: article_analysis_v3

表状态:
- tech_routes: 1949条 (但 profile_text 为空)
- exp_schemes: 1950条 (但 scheme_text 为空)
- 无Jc相关表
```

**问题**：向量数据以pickle BLOB格式存储在SQLite中，无法直接导入MySQL TEXT字段。

### 1.3 云端Milvus（localhost:19530）

```
Collections:
- paper_embeddings: 0条
- entity_embeddings: 0条
- sentence_embeddings: 0条
- 无 tech_routes / exp_schemes Collection
```

---

## 二、正确的迁移方案

### 2.1 数据迁移策略

| 数据类型 | v2来源 | v3目标 | 格式转换 |
|---------|--------|--------|----------|
| 技术路线向量 | SQLite BLOB(pickle) | Milvus `tech_routes` | pickle → float vector |
| 实验方案向量 | SQLite BLOB(pickle) | Milvus `exp_schemes` | pickle → float vector |
| Jc指标数据 | SQLite jc_indices | MySQL `jc_indices` | 直接导入 |
| Jc原始数据 | SQLite jc_indices_raw | MySQL `jc_indices_raw` | 直接导入 |

### 2.2 Milvus新增Collection

```python
# 技术路线Collection
tech_routes:
- id: INT64 (主键)
- doi: VARCHAR(256)
- title: VARCHAR(512)
- techroute_text: VARCHAR(4096)
- embedding: FLOAT_VECTOR(1024)
- created_at: INT64

# 实验方案Collection
exp_schemes:
- id: INT64 (主键)
- doi: VARCHAR(256)
- title: VARCHAR(512)
- expscheme_text: VARCHAR(4096)
- categories: JSON
- embedding: FLOAT_VECTOR(1024)
- created_at: INT64
```

### 2.3 MySQL新增表

```sql
-- Jc指标表
CREATE TABLE jc_indices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doi VARCHAR(255),
    Jc TEXT,
    Jc_unit VARCHAR(50),
    temperature FLOAT,
    temperature_unit VARCHAR(20),
    magneticfield FLOAT,
    magnetic_field_unit VARCHAR(20),
    angle FLOAT,
    angle_unit VARCHAR(20),
    error_bar TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_doi (doi),
    INDEX idx_temp (temperature),
    INDEX idx_field (magneticfield)
);

-- Jc原始数据表
CREATE TABLE jc_indices_raw (
    id INT AUTO_INCREMENT PRIMARY KEY,
    doi VARCHAR(255),
    raw_text TEXT,
    source_section VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_doi (doi)
);
```

---

## 三、v3已有功能（可直接使用）

| 功能 | 状态 | 说明 |
|------|------|------|
| PDF解析 | ✅ 已有 | PDFProcessor.vue + pdf_service.py |
| NER提取 | ✅ 已有 | NERProcessor.vue + ner_service.py |
| RE抽取 | ✅ 已有 | REProcessor.vue + re_service.py |
| 技术路线分析 | ✅ 已有 | DomainAnalysis.vue + tech_route.py |
| 实验方案分析(8维度) | ✅ 已有 | DomainAnalysis.vue + exp_scheme.py |
| Jc指标提取 | ✅ 已有 | DomainAnalysis.vue + jc_index.py |
| 向量搜索 | ✅ 已有 | PaperCompare.vue + milvus_service.py |
| 任务管理+WebSocket | ✅ 已有 | task_manager.py + websocket.py |

---

## 四、需新增的功能

### 4.1 数据迁移脚本

```python
# backend/scripts/migrate_deep_reasoning_data.py

async def migrate_tech_routes_to_milvus():
    """从SQLite迁移技术路线向量到Milvus"""
    # 1. 连接SQLite
    # 2. 读取tech_routes表（包含BLOB向量）
    # 3. unpickle向量数据
    # 4. 创建Milvus tech_routes Collection
    # 5. 批量插入向量

async def migrate_exp_schemes_to_milvus():
    """从SQLite迁移实验方案向量到Milvus"""

async def migrate_jc_to_mysql():
    """从SQLite迁移Jc数据到MySQL"""
```

### 4.2 Jc数据库搜索API

```python
# backend/app/api/v1/jc.py

@router.post("/jc/database/search")
async def search_jc_database(request: JcDatabaseSearchRequest):
    """
    搜索云端MySQL中的Jc历史数据
    - 无需NER ID
    - 按温度/磁场/角度条件匹配
    - 返回排名结果
    """
```

### 4.3 综合分析服务

```python
# backend/app/services/comprehensive_service.py

class ComprehensiveAnalysisService:
    """综合分析编排服务"""

    async def run_full_analysis(pdf_path, target_doi):
        """
        1. PDF解析 (复用现有)
        2. NER提取 (复用现有)
        3. RE抽取 (复用现有)
        4. 技术路线对比 (复用domain + Milvus检索)
        5. 实验方案对比 (复用domain + Milvus检索)
        6. Jc指标对比 (复用jc_index + MySQL排名)
        7. LLM综合分析
        8. 报告生成
        """
```

---

## 五、实施步骤

### Phase 1: 数据迁移（2天）

**Day 1: Milvus向量迁移**
1. 创建 `tech_routes` 和 `exp_schemes` Collection
2. 编写迁移脚本，从SQLite BLOB提取pickle向量
3. 批量导入到Milvus

**Day 2: MySQL Jc数据迁移**
1. 创建 `jc_indices` 和 `jc_indices_raw` 表
2. 从SQLite导入Jc数据
3. 验证数据完整性

### Phase 2: 服务开发（2天）

**Day 3: Jc数据库搜索服务**
1. 创建 `jc_database_service.py`
2. 实现条件搜索和排名计算
3. 创建API路由

**Day 4: 综合分析服务**
1. 创建 `comprehensive_service.py`
2. 整合现有服务流程
3. 报告生成服务（从v2复制）

### Phase 3: 前端开发（1天）

**Day 5: 前端页面修改**
1. DomainAnalysis.vue 新增"Jc数据库搜索"Tab
2. 创建 ComprehensiveAnalysis.vue
3. WebSocket进度追踪

---

## 六、迁移脚本示例

### 6.1 Milvus向量迁移

```python
import sqlite3
import pickle
from pymilvus import MilvusClient

def migrate_tech_routes():
    # 连接SQLite
    conn = sqlite3.connect('v2/data/REBCO_database/rebco.db')
    cursor = conn.cursor()

    # 读取数据
    cursor.execute('SELECT doi, title, techroutes, vector FROM tech_routes')
    rows = cursor.fetchall()

    # 连接Milvus
    client = MilvusClient(uri='http://localhost:19530')
    client.use_database('scipdf')

    # 创建Collection
    # ... schema定义

    # 批量插入
    data = []
    for row in rows:
        doi, title, techroutes, vector_blob = row
        vector = pickle.loads(vector_blob) if vector_blob else [0.0] * 1024
        data.append({
            'doi': doi,
            'title': title or '',
            'techroute_text': techroutes or '',
            'embedding': vector
        })

    client.insert('tech_routes', data)
```

---

## 七、验收标准

### 7.1 数据迁移完成
- Milvus tech_routes: ~1950条向量
- Milvus exp_schemes: ~1950条向量
- MySQL jc_indices: ~42132条
- MySQL jc_indices_raw: ~386712条

### 7.2 Jc数据库搜索
- 能按温度/磁场/角度条件搜索
- 返回排名结果（含历史论文对比）

### 7.3 综合分析流程
- PDF上传 → NER → RE → 技术路线 → 实验方案 → Jc → 报告
- 实时进度显示
- 报告下载（MD/Excel/PDF）

---

## 八、文件清单

### 新增文件

```
backend/
├── scripts/
│   └── migrate_deep_reasoning_data.py  # 数据迁移脚本
├── app/
│   ├── api/v1/
│   │   ├── jc.py                       # Jc数据库搜索API
│   │   └── comprehensive.py            # 综合分析API
│   ├── services/
│   │   ├── jc_database_service.py      # Jc数据库服务
│   │   ├── comprehensive_service.py    # 综合分析编排
│   │   └── report_service.py           # 报告生成（从v2复制）
│   ├── schemas/
│   │   ├── jc.py
│   │   └── comprehensive.py

frontend/src/
├── views/
│   ├── ComprehensiveAnalysis.vue       # 综合分析页面
├── api/
│   ├── jc.ts
│   ├── comprehensive.ts
```

### 修改文件

```
frontend/src/
├── views/DomainAnalysis.vue            # 新增Jc数据库搜索Tab
├── router/index.ts                     # 新增路由
├── App.vue                             # 导航菜单

backend/app/
├── api/v1/__init__.py                  # 注册新路由
├── services/milvus_service.py          # 新增tech_routes/exp_schemes Collection创建方法
```

---

## 九、总结

**核心任务**：
1. ✅ v3已有PDF/NER/RE/技术路线/实验方案/Jc提取功能
2. ❌ 需迁移SQLite向量数据到云端Milvus
3. ❌ 需迁移Jc数据到云端MySQL
4. ❌ 需新增Jc数据库搜索功能（无需NER ID）
5. ❌ 需新增综合分析一键流程页面

**工作量**：约5天（原计划6天，数据迁移更清晰后可优化）