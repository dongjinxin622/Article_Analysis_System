# Step2: 核心模块迁移 - 详细计划

> 预计周期: 2 周 | 状态: 待开始 | 前置依赖: Step1

---

## 一、任务清单

### 2.1 PDF 解析服务迁移

**目标**：将 v2 PDF 服务迁移为异步版本

**文件**：`backend/app/services/pdf_service.py`

**参考来源**：v2 `backend/services/pdf_service.py`

**核心函数迁移**：

| v2 函数 | v3 异步版本 | 改动说明 |
|---------|------------|---------|
| `extract_doi_from_pdf()` | `async extract_doi_from_pdf()` | 改为异步（fitz 不支持真正异步，用 asyncio.to_thread 包装） |
| `parse_pdf_with_pymupdf()` | `async parse_pdf_with_pymupdf()` | asyncio.to_thread 包装 |
| `parse_pdf_file()` | `async parse_pdf_file()` | 异步调用 |
| `save_result()` | `async save_result()` | aiofiles 替代 |
| `save_to_database()` | `async save_to_database()` | 异步数据库会话 |
| `process_pdf()` | `async process_pdf()` | 全异步流程 |

**新增内容**：
- 异步文件读写（aiofiles）
- 异步数据库操作
- 异步 HTTP 调用（httpx）

---

### 2.2 PDF 上传 API

**目标**：创建 PDF 上传异步 API

**文件**：`backend/app/api/v1/pdf.py`

**参考来源**：v2 `backend/api/upload.py`

**API 接口**：

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/papers` | POST | 上传论文 |
| `/api/v1/papers` | GET | 获取论文列表 |
| `/api/v1/papers/{id}` | GET | 获取论文详情 |
| `/api/v1/papers/{id}` | DELETE | 删除论文 |

---

### 2.3 NER 服务迁移

**目标**：将 v2 NER 服务迁移为异步版本

**文件**：`backend/app/services/ner_service.py`

**参考来源**：v2 `backend/services/ner_service.py`

**核心函数迁移**：

| v2 函数 | v3 异步版本 |
|---------|------------|
| `prepare_sentences_from_pdf()` | `async prepare_sentences_from_pdf()` |
| `group_sentences()` | 同步（纯数据处理） |
| `process_ner_with_llm()` | `async process_ner_with_llm()` |
| `process_ner_for_result()` | `async process_ner_for_result()` |
| `save_ner_results()` | `async save_ner_results()` |
| `save_ner_to_database()` | `async save_ner_to_database()` |

**改动要点**：
- Stanza 句子分割用 asyncio.to_thread 包装
- LLM 批量调用用异步 TaskProcessor
- 文件读写用 aiofiles
- 数据库用异步会话

---

### 2.4 NER API

**目标**：创建 NER 异步 API

**文件**：`backend/app/api/v1/ner.py`

**参考来源**：v2 `backend/api/ner.py`

**API 接口**：

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/ner` | POST | 执行 NER |
| `/api/v1/ner/{ner_id}` | GET | 获取 NER 结果 |
| `/api/v1/ner/{ner_id}/excel` | GET | 下载 Excel |
| `/api/v1/ner/{ner_id}/pkl` | GET | 下载 PKL |
| `/api/v1/ner/{ner_id}/entities` | GET | 获取实体列表 |
| `/api/v1/ner/batch` | POST | 批量 NER |

---

### 2.5 关系抽取服务迁移

**目标**：将 v2 RE 服务迁移为异步版本

**文件**：`backend/app/services/re_service.py`

**参考来源**：v2 `backend/services/re_service.py`

**核心函数迁移**：

| v2 函数 | v3 异步版本 |
|---------|------------|
| `save_re_results()` | `async save_re_results()` |
| `prepare_re_input_from_ner_ner_results()` | 同步（纯数据处理） |
| `process_re_for_ner()` | `async process_re_for_ner()` |

---

### 2.6 RE API

**目标**：创建 RE 异步 API

**文件**：`backend/app/api/v1/re.py`

**参考来源**：v2 `backend/api/re.py`

**API 接口**：

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/re` | POST | 执行 RE |
| `/api/v1/re/{re_id}` | GET | 获取 RE 结果 |
| `/api/v1/re/{re_id}/excel` | GET | 下载 Excel |

---

### 2.7 数据库模型设计

**目标**：创建完整的数据库模型

**文件**：`backend/app/models/*.py`

**参考来源**：v2 `backend/models/db_models.py`

**模型列表**：

| 文件 | 模型 | 说明 |
|------|------|------|
| base.py | Base | 模型基类 |
| paper.py | Paper, ProcessingResult | 论文模型 |
| ner.py | NERResult | NER 结果模型 |
| re.py | REResult | RE 结果模型 |
| batch.py | BatchTask, TaskLog | 批量任务模型 |
| user.py | User | 用户模型 |
| domain.py | DomainConfig | 领域配置模型 |

**新增模型**：
- `User`: 用户表（JWT 认证）
- `DomainConfig`: 领域配置表
- `BatchTask`: 批量任务表（支持 Celery）

---

### 2.8 TaskProcessor 迁移

**目标**：迁移 base_methods.py 中的 TaskProcessor

**文件**：`backend/app/utils/task_processor.py`

**参考来源**：v2 `deep-reasoning-methods/base_methods.py`

**改动要点**：
- 改为异步版本
- 使用 asyncio 和 aiohttp 替代 ThreadPoolExecutor
- 保持批量处理、重试机制等核心逻辑

---

## 二、执行顺序

1. 复制 `scipdf/` 目录（直接可用）
2. 创建 `backend/app/services/pdf_service.py`
3. 创建 `backend/app/api/v1/pdf.py`
4. 创建 `backend/app/services/ner_service.py`
5. 创建 `backend/app/api/v1/ner.py`
6. 创建 `backend/app/services/re_service.py`
7. 创建 `backend/app/api/v1/re.py`
8. 创建数据库模型
9. 创建 `backend/app/utils/task_processor.py`
10. 测试各 API 接口

---

## 三、检查标准

| 检查项 | 标准 |
|--------|------|
| PDF 上传 | 上传 PDF 文件成功返回 result_id |
| PDF 解析 | 返回 title, abstract, sections |
| NER 处理 | 执行 NER 返回实体列表 |
| NER 批量 | 批量 NER 正常执行 |
| RE 处理 | 执行 RE 返回关系列表 |
| 异步性能 | 各接口响应时间合理 |

---

## 四、参考文件列表

| v2 文件 | v3 目标位置 |
|---------|------------|
| `backend/services/pdf_service.py` | `backend/app/services/pdf_service.py` |
| `backend/api/upload.py` | `backend/app/api/v1/pdf.py` |
| `backend/services/ner_service.py` | `backend/app/services/ner_service.py` |
| `backend/api/ner.py` | `backend/app/api/v1/ner.py` |
| `backend/services/re_service.py` | `backend/app/services/re_service.py` |
| `backend/api/re.py` | `backend/app/api/v1/re.py` |
| `backend/models/db_models.py` | `backend/app/models/*.py` |
| `deep-reasoning-methods/base_methods.py` (TaskProcessor) | `backend/app/utils/task_processor.py` |

---

*Step2 完成后进入 Step3: 向量服务开发*