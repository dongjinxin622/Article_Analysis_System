# V2项目后端功能详细分析文档

> 本文档记录Article_Analysis_System_v2项目所有后端功能，用于v3项目重构参考

---

## 一、项目整体结构

### 1.1 目录结构概览

```
Article_Analysis_System_v2/
├── backend/                          # FastAPI 后端核心
│   ├── main.py                       # 应用入口
│   ├── config.py                     # 配置管理
│   ├── api/                          # API 路由层
│   │   ├── upload.py                 # PDF 上传 API
│   │   ├── ner.py                    # NER 处理 API
│   │   ├── re.py                     # 关系抽取 API
│   │   ├── analysis.py               # 分析 API
│   │   ├── batch.py                  # 批量处理 API
│   │   ├── batch_extraction.py       # 批量提取 API
│   │   ├── chat_extraction.py        # 对话式提取 API
│   │   ├── deep_reasoning.py         # 深度推理 API
│   │   ├── prompt.py                 # Prompt 管理 API
│   │   ├── results.py                # 结果查询 API
│   │   └── pages.py                  # 页面路由
│   ├── services/                     # 业务逻辑层
│   │   ├── pdf_service.py            # PDF 解析服务
│   │   ├── ner_service.py            # NER 服务
│   │   ├── re_service.py             # 关系抽取服务
│   │   ├── batch_service.py          # 批量处理服务
│   │   ├── batch_extraction_service.py # 批量提取服务
│   │   ├── deep_reasoning_service.py # 深度推理服务
│   │   ├── jc_service.py             # Jc 指标服务
│   │   ├── jc_batch_processor.py     # Jc 批量处理器
│   │   ├── task_manager.py           # 任务管理器
│   │   └── report_service.py         # 报告服务
│   ├── models/                       # 数据库模型
│   │   ├── db_models.py              # SQLAlchemy 模型
│   │   └── database.py               # 数据库连接管理
│   └── schemas/                      # Pydantic 模型
│       ├── schemas.py                # 基础 Schema
│       ├── batch_schemas.py          # 批量处理 Schema
│       ├── batch_extraction_schemas.py # 批量提取 Schema
│       ├── deep_reasoning_schemas.py # 深度推理 Schema
│       └── chat_schemas.py           # 对话 Schema
├── deep-reasoning-methods/           # 深度推理方法模块
│   ├── base_methods.py               # 基础工具类（VectorTools, TaskProcessor）
│   ├── tech_route/                   # 技术路线分析
│   │   ├── techroute_builder.py      # 技术路线构建
│   │   ├── techroute_common.py       # 共享组件
│   │   ├── techroute_querier.py      # 技术路线查询
│   │   └── compare_techroute.py      # 技术路线比较
│   ├── exp_scheme/                   # 实验方案分析
│   │   ├── exp_scheme_builder.py     # 实验方案构建
│   │   └── exp_scheme_retriever.py   # 实验方案检索
│   └── jc_index/                     # Jc 指标分析
│       ├── jc_index_extractor.py     # Jc 指标提取
│       ├── jc_retrieval.py           # Jc 检索
│       ├── search_Jc.py              # Jc 搜索
│       └── extract_keyindices_v2.py  # 关键指标提取
├── scipdf/                           # PDF 解析库
│   ├── pdf/parse_pdf.py              # PDF 解析核心（GROBID集成）
│   └── features/text_utils.py        # 文本工具
├── batch_extraction_refactored/      # 批量提取重构模块
│   ├── agent.py                      # LangGraph Agent
│   └── utils/                        # 工具函数
│       ├── models.py                 # 模型定义
│       ├── tools.py                  # 工具函数
│       └── state.py                  # 状态管理
├── data/                             # 数据存储目录
│   ├── uploads/                      # 上传的 PDF 文件
│   ├── results/                      # PDF 解析结果
│   ├── ner_results/                  # NER 结果
│   ├── re_results/                   # RE 结果
│   ├── failed_logs/                  # 失败日志
│   └── REBCO_database/               # REBCO 领域数据库
└── scripts/                          # 初始化脚本
```

---

## 二、核心配置模块

### 2.1 配置文件 (backend/config.py)

**位置**: `.\backend\config.py`

**功能说明**:
- 使用 Pydantic Settings 进行配置管理
- 支持 SQLite 和 MySQL 双数据库配置
- 支持 GROBID 服务配置
- 文件上传和处理的各项参数配置

**核心类**: `Settings`

**配置项**:
| 配置项 | 默认值 | 说明 |
|-------|--------|------|
| `APP_NAME` | "SciPDF AI论文处理系统" | 应用名称 |
| `DATABASE_TYPE` | "sqlite" | 数据库类型 |
| `GROBID_URL` | "http://localhost:8070" | GROBID 服务地址 |
| `MAX_UPLOAD_SIZE` | 100MB | 最大上传文件大小 |
| `PDF_MAX_RETRIES` | 3 | PDF 解析最大重试次数 |
| `PDF_RETRY_DELAY` | 2 | PDF 解析重试延迟(秒) |

**复制要点**: v3项目中可直接复制此配置结构，需添加 Milvus 和 Redis 配置。

---

## 三、数据库模块

### 3.1 数据库连接 (backend/models/database.py)

**位置**: `.\backend\models\database.py`

**功能说明**:
- SQLAlchemy 数据库引擎创建
- 会话工厂管理
- 数据库初始化函数
- 上下文管理器模式的数据库会话

**核心函数**:
```python
def get_db() -> Generator[Session, None, None]  # 依赖注入用的会话获取
def get_db_context() -> Generator[Session, None, None]  # 上下文管理器
def init_db()  # 创建所有表
```

**复制要点**: v3项目可直接复制，但需要改为异步版本（使用 aiomysql/aiosqlite）。

### 3.2 数据模型 (backend/models/db_models.py)

**位置**: `.\backend\models\db_models.py`

**数据表设计**:

| 表名 | 说明 | 核心字段 |
|------|------|---------|
| `processing_results` | PDF 处理结果 | result_id, doi, title, abstract, status |
| `ner_results` | NER 结果 | ner_id, result_id, entity_count, ner_json_path |
| `re_results` | 关系抽取结果 | re_id, ner_id, relation_count |
| `analysis_results` | 分析结果 | analysis_id, ner_id, methods_extracted |
| `failed_logs` | 失败日志 | log_id, error_type, error_message |

**复制要点**: v3项目需要扩展模型，添加领域配置表、批量任务表、用户表等。

---

## 四、PDF 处理模块

### 4.1 PDF 上传 API (backend/api/upload.py)

**位置**: `.\backend\api\upload.py`

**API 接口**:
- `POST /api/upload` - 上传 PDF 文件并触发解析

**处理流程**:
1. 验证文件扩展名（仅支持 PDF）
2. 检查文件大小限制
3. 生成唯一文件名并保存
4. 调用 PDF 服务进行解析
5. 返回处理结果（包含 result_id）

**复制要点**: v3项目可直接复制逻辑，添加异步处理支持。

### 4.2 PDF 解析服务 (backend/services/pdf_service.py)

**位置**: `.\backend\services\pdf_service.py`

**核心函数**:

| 函数名 | 功能 |
|--------|------|
| `extract_doi_from_pdf()` | 从 PDF 前两页提取 DOI |
| `parse_pdf_with_pymupdf()` | PyMuPDF 备用解析方案 |
| `parse_pdf_file()` | 主解析函数（优先 GROBID，备用 PyMuPDF） |
| `save_result()` | 保存解析结果到 pkl/json 文件 |
| `save_to_database()` | 保存到数据库 |
| `process_pdf()` | 完整处理流程（带重试机制） |

**处理流程**:
1. 提取 DOI（用于生成唯一 result_id）
2. 尝试 GROBID 解析（需要 GROBID 服务）
3. GROBID 失败时使用 PyMuPDF 备用
4. 保存 pkl 和 json 结果文件
5. 写入数据库记录

**复制要点**: v3项目可直接复制，需调整为异步版本。

### 4.3 scipdf PDF 解析库 (scipdf/pdf/parse_pdf.py)

**位置**: `.\scipdf\pdf\parse_pdf.py`

**核心功能**:
- GROBID 服务集成（调用 GROBID API 进行 PDF 解析）
- 解析输出转换为结构化字典
- 提取标题、作者、摘要、章节、参考文献、图表等

**核心函数**:
| 函数名 | 功能 |
|--------|------|
| `parse_pdf()` | 调用 GROBID API 解析 PDF |
| `parse_pdf_to_dict()` | 解析并返回结构化字典 |
| `parse_authors()` | 解析作者列表 |
| `parse_abstract()` | 解析摘要 |
| `parse_sections()` | 解析章节 |
| `parse_references()` | 解析参考文献 |
| `parse_figure_caption()` | 解析图表 |

**复制要点**: v3项目可直接复制此模块。

---

## 五、NER 处理模块

### 5.1 NER API (backend/api/ner.py)

**位置**: `.\backend\api\ner.py`

**API 接口**:

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/ner` | POST | 执行 NER 处理 |
| `/api/ner/{ner_id}` | GET | 获取 NER 结果 |
| `/api/ner/{ner_id}/excel` | GET | 下载 Excel 结果 |
| `/api/ner/{ner_id}/pkl` | GET | 下载 PKL 结果 |
| `/api/ner/{ner_id}/json` | GET | 下载 JSON 结果 |
| `/api/ner/{ner_id}/entities` | GET | 获取实体列表（可按类型筛选） |
| `/api/ner/batch` | POST | 批量执行 NER |
| `/api/results/{result_id}/ner` | GET | 根据 result_id 获取 NER |

**请求参数 (NERRequest)**:
```python
class NERRequest:
    result_id: str           # 处理结果 ID（必填）
    skip_introduction: bool  # 是否跳过 introduction（默认 True）
    sentence_group_size: int # 每组句子数量（默认 5，范围 1-20）
    query_file: str          # Prompt 模板文件路径（必填）
    task_name: str           # 任务名称（默认 NER_task）
```

**复制要点**: v3项目可直接复制 API 结构，添加异步任务支持。

### 5.2 NER 服务 (backend/services/ner_service.py)

**位置**: `.\backend\services\ner_service.py`

**核心函数**:

| 函数名 | 功能 |
|--------|------|
| `prepare_sentences_from_pdf()` | 从 PDF 解析结果准备句子数据 |
| `group_sentences()` | 将句子按指定数量分组拼接 |
| `process_ner_with_llm()` | 使用 LLM API 进行 NER 处理 |
| `process_ner_for_result()` | 为指定结果执行完整 NER 流程 |
| `save_ner_results()` | 保存 NER 结果到文件 |
| `save_ner_to_database()` | 保存到数据库 |

**处理流程**:
1. 从 PDF 解析的 JSON 文件加载内容
2. 提取 abstract 和章节文本（可跳过 introduction）
3. 使用 Stanza 进行句子分割
4. 按 sentence_group_size 分组拼接句子
5. 调用 LLM API（通过 TaskProcessor）进行实体识别
6. 解析 LLM 返回的实体列表
7. 保存结果（json/excel/pkl 格式）
8. 写入数据库

**关键依赖**:
- Stanza: 用于句子分割
- TaskProcessor: 来自 base_methods.py，用于批量 LLM 调用

**复制要点**: v3项目可直接复制核心逻辑，需调整为异步版本。

---

## 六、关系抽取(RE)模块

### 6.1 RE API (backend/api/re.py)

**位置**: `.\backend\api\re.py`

**API 接口**:

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/re` | POST | 执行关系抽取 |
| `/api/re/{re_id}` | GET | 获取 RE 结果 |

**请求参数 (RERequest)**:
```python
class RERequest:
    ner_id: str       # NER 结果 ID（必填）
    query_file: str   # Prompt 模板文件路径（必填）
    task_name: str    # 任务名称（默认 RE_task）
```

### 6.2 RE 服务 (backend/services/re_service.py)

**位置**: `.\backend\services\re_service.py`

**核心函数**:

| 函数名 | 功能 |
|--------|------|
| `save_re_results()` | 保存 RE 结果到文件 |
| `prepare_re_input_from_ner_ner_results()` | 从 NER 结果准备 RE 输入 |
| `process_re_for_ner()` | 为指定 NER 执行关系抽取 |

**处理流程**:
1. 从 NER 的 PKL/JSON 文件加载数据
2. 按 (doi, section_idx, group_idx) 整合 NER 实体和对应原文
3. 构建 LLM 输入（实体列表 + 原文句子）
4. 调用 TaskProcessor 进行批量 LLM 处理
5. 解析返回的关系数据
6. 保存结果并写入数据库

**复制要点**: v3项目可直接复制核心逻辑。

---

## 七、深度推理模块

### 7.1 深度推理 API (backend/api/deep_reasoning.py)

**位置**: `.\backend\api\deep_reasoning.py`

**API 接口**:

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/deep-reasoning/techroute/compare` | POST | 技术路线比较 |
| `/api/deep-reasoning/expscheme/compare` | POST | 实验方案比较 |
| `/api/deep-reasoning/jc/compare` | POST | Jc 指标比较 |
| `/api/deep-reasoning/jc/search` | POST | Jc 条件搜索 |
| `/api/deep-reasoning/upload-excel` | POST | 上传 Excel 文件 |
| `/api/deep-reasoning/comprehensive` | POST | 综合分析（后台异步） |
| `/api/deep-reasoning/status/{task_id}` | GET | 查询任务状态 |
| `/api/deep-reasoning/report/{task_id}` | GET | 获取分析报告 |

**综合分析流程**:
1. 从 Excel 或 result_id 加载 NER/RE/content 数据
2. 并行执行技术路线分析、实验方案分析、Jc指标分析
3. 计算综合评分
4. 调用 LLM 生成详细对比分析报告
5. 生成 Markdown/Excel/PDF 报告

**复制要点**: v3项目可直接复制 API 结构，整合 Milvus 向量检索。

### 7.2 深度推理服务 (backend/services/deep_reasoning_service.py)

**位置**: `.\backend\services\deep_reasoning_service.py`

**核心类**: `DeepReasoningService`

**核心方法**:

| 方法名 | 功能 |
|--------|------|
| `compare_techroute()` | 技术路线比较 |
| `compare_expscheme()` | 实验方案比较 |
| `comprehensive_comparison()` | 综合分析 |
| `_build_techroute_from_ner_re()` | 从 NER+RE 构建技术路线 |
| `_generate_expscheme_from_ner()` | 从 NER 生成实验方案 |
| `_generate_llm_comparison()` | LLM 对比分析 |

**数据库连接**:
- 连接 SQLite 数据库 (REBCO_database/rebco.db)
- 查询 tech_routes 和 exp_schemes 表

**复制要点**: v3项目需改用 Milvus 进行向量检索，而非本地 SQLite。

### 7.3 基础工具类 (deep-reasoning-methods/base_methods.py)

**位置**: `.\deep-reasoning-methods\base_methods.py`

**核心类**:

#### VectorTools 类
```python
class VectorTools:
    def __init__(api_key, base_url, embedding_model='text-embedding-v4', dimensions=1024)
    def text_to_vector(input_text) -> List[float]  # 文本向量化
    def cosine_similarity(vector1, vector2) -> float  # 计算余弦相似度
    def find_similar(query_vector, database, threshold, top_k)  # 检索相似向量
```

#### TaskProcessor 类
```python
class TaskProcessor:
    def __init__(task_name, workers=50, model="qwen-plus", save_folder="results")
    def load_data(excel_path)  # 从 Excel 加载数据
    def load_query(query_file_path)  # 加载 Prompt 模板
    def call_api(paragraph, query_template)  # 调用 LLM API
    def parse_response(response_text)  # 解析 JSON 响应
    def process_batch(data_list, query_file_path, batch_size)  # 批量处理（带重试）
    def merge_results(batch_dir)  # 合并批次结果
    def save_to_excel(result_dict)  # 保存为 Excel
```

**复制要点**:
- VectorTools 功能需迁移到 v3 的 EmbeddingService + VectorService(Milvus)
- TaskProcessor 可直接复制，用于批量 LLM 调用

### 7.4 技术路线构建 (deep-reasoning-methods/tech_route/techroute_builder.py)

**位置**: `.\deep-reasoning-methods\tech_route\techroute_builder.py`

**核心功能**:
- 从 NER+RE 数据构建实体关系网络
- 提取从工艺参数到 Jc 指标的关键路径
- 生成技术路线文本描述
- 批量向量化并存储

**关键函数**:
| 函数名 | 功能 |
|--------|------|
| `process_single_network_with_timeout()` | 处理单个网络（带超时保护） |
| `construct_networks_from_data()` | 批量构建实体网络 |
| `Qianwen_text2vector()` | 文本向量化 |
| `find_related_articles()` | 检索相似论文 |

**复制要点**: v3项目可复用核心算法，向量存储改用 Milvus。

### 7.5 Jc 指标提取 (deep-reasoning-methods/jc_index/jc_index_extractor.py)

**位置**: `.\deep-reasoning-methods\jc_index\jc_index_extractor.py`

**核心类**: `JcIndexExtractor`

**核心方法**:
| 方法名 | 功能 |
|--------|------|
| `find_jc_entities()` | 从 NER 数据定位 Jc 相关实体 |
| `locate_content_segments()` | 定位 content 中的原文段落 |
| `extract_from_content()` | 从单文本提取 Jc 指标 |
| `extract_from_content_batch()` | 批量并行提取 |
| `extract_from_excel()` | 从 Excel 文件提取 |

**提取内容**:
- Jc 值（临界电流密度）
- 温度条件
- 磁场强度
- 角度参数

**复制要点**: v3项目可直接复制核心逻辑，整合到领域分析器。

---

## 八、批量提取模块

### 8.1 批量提取 API (backend/api/batch_extraction.py)

**位置**: `.\backend\api\batch_extraction.py`

**API 接口**:

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/batch-extraction/upload` | POST | 上传数据文件 |
| `/api/batch-extraction/start` | POST | 启动提取任务 |
| `/api/batch-extraction/status/{task_id}` | GET | 查询任务状态 |
| `/api/batch-extraction/action/{task_id}` | POST | 处理用户操作(HITL) |
| `/api/batch-extraction/result/{task_id}` | GET | 获取结果文件 |

### 8.2 批量提取服务 (backend/services/batch_extraction_service.py)

**位置**: `.\backend\services\batch_extraction_service.py`

**核心类**: `BatchExtractionService`, `BatchExtractionTask`

**工作流步骤**:
```python
STEPS = [
    "load_config",      # 加载配置
    "integrate",        # 数据整合
    "field_check",      # 字段检查（HITL）
    "data_quality",     # 数据质量检查（HITL）
    "filter",           # 数据过滤（HITL）
    "parse_strategy",   # 解析策略文档
    "generate_prompt",  # 生成 Prompt（HITL）
    "prompt_check",     # Prompt 检查
    "prepare_eval",     # 准备评估
    "batch_eval",       # 批量评估
    "result_check",     # 结果检查（HITL）
    "export_result"     # 导出结果
]
```

**HITL (Human-in-the-loop) 检查点**:
- 字段检查：验证必要字段是否存在
- 数据质量检查：计算完整率和重复率
- 数据过滤检查：验证过滤后数据量
- Prompt 检查：确认生成的 Prompt
- 结果检查：验证处理成功率

**复制要点**: v3项目可参考此 LangGraph 工作流设计，整合 HITL 机制。

---

## 九、任务管理模块

### 9.1 任务管理器 (backend/services/task_manager.py)

**位置**: `.\backend\services\task_manager.py`

**功能**:
- 创建和管理异步分析任务
- 任务状态跟踪
- 后台线程执行
- WebSocket 进度通知

**复制要点**: v3项目需整合 Celery 异步任务系统。

---

## 十、报告服务模块

### 10.1 报告服务 (backend/services/report_service.py)

**位置**: `.\backend\services\report_service.py`

**功能**:
- 生成 Markdown 分析报告
- 生成 Excel 报告
- 生成 PDF 报告

**复制要点**: v3项目可直接复制。

---

## 十一、Schema 定义

### 11.1 基础 Schema (backend/schemas/schemas.py)

**位置**: `.\backend\schemas\schemas.py`

**核心模型**:
| 模型名 | 用途 |
|--------|------|
| `ProcessingStatus` | 处理状态枚举 |
| `UploadedFile` | 上传文件信息 |
| `UploadResponse` | 上传响应 |
| `NERRequest` | NER 请求参数 |
| `NERResponse` | NER 响应 |
| `RERequest` | RE 请求参数 |
| `REResponse` | RE 响应 |
| `AnalysisRequest` | 分析请求 |
| `ErrorResponse` | 错误响应 |

**复制要点**: v3项目可扩展这些 Schema，添加用户、领域配置等模型。

---

## 十二、关键代码片段

### 12.1 DOI 提取

```python
# 来自 backend/services/pdf_service.py
def extract_doi_from_pdf(file_path: str) -> Optional[str]:
    doc = fitz.open(file_path)
    text = ""
    for i in range(min(2, len(doc))):
        text += doc[i].get_text()
    doi_pattern = r'10\.\d{4,9}/[-._;():/A-Za-z0-9]+'
    matches = re.search(doi_pattern, text)
    return matches.group(0) if matches else None
```

### 12.2 句子分割 (Stanza)

```python
# 来自 backend/services/ner_service.py
nlp_stanza = stanza.Pipeline(
    lang='en',
    processors='tokenize',
    use_gpu=False,
    verbose=False
)
doc = nlp_stanza(content)
sentences = [sentence.text for sentence in doc.sentences]
```

### 12.3 LLM 批量调用

```python
# 来自 base_methods.py TaskProcessor
with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
    futures = {
        executor.submit(self.process_single_item, item, query_template, key_list, retry_queue): idx
        for idx, item in enumerate(batch_data)
    }
    for future in tqdm(as_completed(futures), total=len(batch_data)):
        future.result(timeout=self.request_timeout + 10)
```

### 12.4 向量相似度计算

```python
# 来自 base_methods.py VectorTools
def cosine_similarity(self, vector1, vector2):
    v1 = np.array([float(x) for x in vector1])
    v2 = np.array([float(x) for x in vector2])
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    return float(np.dot(v1, v2) / (norm1 * norm2))
```

---

## 十三、v3项目迁移建议

### 13.1 可直接复制的模块

| 模块 | 复制建议 |
|------|---------|
| config.py | 扩展配置（添加 Milvus、Redis） |
| database.py | 改为异步版本 |
| db_models.py | 扩展模型 |
| pdf_service.py | 改为异步版本 |
| ner_service.py | 改为异步版本 |
| re_service.py | 改为异步版本 |
| scipdf/pdf/parse_pdf.py | 直接复制 |
| base_methods.py | TaskProcessor 直接复制，VectorTools 改用 Milvus |
| jc_index_extractor.py | 整合到领域分析器 |
| batch_extraction_service.py | 参考工作流设计 |

### 13.2 需要重构的部分

| 模块 | 重构方向 |
|------|---------|
| 向量存储 | 从 SQLite 改为 Milvus |
| 向量检索 | 集成 Milvus SDK |
| 任务管理 | 改用 Celery + Redis |
| WebSocket | 添加实时进度推送 |
| 用户认证 | 添加 JWT 认证 |
| 前端 | Vue 3 重构 |

### 13.3 新增功能

| 功能 | 说明 |
|------|------|
| 用户系统 | JWT 认证，权限管理 |
| 领域配置 | 可扩展的领域分析器注册机制 |
| Milvus 向量检索 | 替代本地向量存储 |
| Celery 异步任务 | 替代当前线程池方案 |
| WebSocket 进度推送 | 实时任务进度更新 |

---

*本文档记录了 v2 项目所有核心后端功能，用于 v3 项目重构参考。*