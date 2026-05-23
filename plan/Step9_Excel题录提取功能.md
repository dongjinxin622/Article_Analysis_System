# Excel 题录数据批量提取功能实现计划

> 版本: 1.0 | 创建日期: 2026-04-22 | 从 v2 移植到 v3

---

## 一、功能概述

### 1.1 功能描述

将 v2 的 "Excel 题录数据批量提取" 功能移植到 v3：

**输入**：Excel 文件（包含 DOI、Authors、Title、Abstract 等题录数据）
**处理**：数据整合 → 字段检查 → 质量评分 → 过滤去重 → LLM 批量评估 → [HITL 审核] → 导出 Excel
**输出**：Excel 文件，包含原始数据 + 提取结果（related、institution、summary、关键技术、应用领域等）

### 1.2 与现有功能对比

| 功能 | 现有 BatchExtraction | 新增 Excel 提取 |
|------|---------------------|----------------|
| 输入源 | PDF 文件 | Excel 题录数据 |
| 处理流程 | PDF 解析 → NER → RE | 数据整合 → LLM 评估 |
| 输出 | NER 实体 + RE 关系 | 关键信息字段 |
| HITL | 无 | 有（可选） |
| 前端页面 | `/batch` 路由 | 同页面新增 Tab |

---

## 二、技术方案

### 2.1 设计原则

1. **不引入新框架依赖**：不使用 `langgraph`/`langchain_openai`，复用 v3 现有的 `LLMService`
2. **遵循 v3 架构模式**：
   - 异步函数式服务层（无类封装）
   - `asyncio.create_task` 后台任务
   - `asyncio.Semaphore` 并发控制
   - MySQL 持久化 + WebSocket 进度推送
3. **独立模块设计**：新建 models/schemas/services/api，不修改现有 batch 模块
4. **前端 Tab 化**：在现有 `BatchExtraction.vue` 中添加 Tab，不新建路由

### 2.2 需新增依赖

| 依赖 | 用途 | 是否必须 |
|------|------|----------|
| `python-docx` | 策略 Word 文档解析 | **需要**（可选功能） |
| `xlrd` | 旧版 .xls 支持 | 不需要（openpyxl 已支持 .xlsx） |

---

## 三、文件清单

### 3.1 后端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `backend/app/models/excel_extraction.py` | **新建** | 数据库模型（2张表） |
| `backend/app/schemas/excel_extraction.py` | **新建** | Pydantic Schema（请求/响应/枚举） |
| `backend/app/services/excel_extraction_service.py` | **新建** | 核心服务层（约800行） |
| `backend/app/api/v1/excel_extraction.py` | **新建** | API 路由（9个端点） |
| `backend/app/main.py` | **修改** | 注册新路由 |
| `backend/requirements.txt` | **修改** | 添加 `python-docx` |

### 3.2 前端文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `frontend/src/types/excel_extraction.ts` | **新建** | TypeScript 类型定义 |
| `frontend/src/api/excel_extraction.ts` | **新建** | API 封装（含 blob 下载） |
| `frontend/src/views/BatchExtraction.vue` | **修改** | 添加 `el-tabs` + Excel Tab 内容 |

---

## 四、数据库模型设计

### 4.1 表：`excel_extraction_tasks`

```python
class ExcelExtractionTask(Base):
    __tablename__ = "excel_extraction_tasks"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(255), unique=True, nullable=False, index=True)
    task_name = Column(String(255))
    user_id = Column(Integer, ForeignKey("users.id"))

    # 输入
    original_filenames = Column(JSON)  # ["file1.xlsx", "file2.xlsx"]
    strategy_file_path = Column(String(500))  # 可选

    # 状态: pending -> validating -> processing -> hitl_review -> exporting -> completed/failed/cancelled
    status = Column(String(50), default="pending")

    # 进度
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)
    success_rows = Column(Integer, default=0)
    failed_rows = Column(Integer, default=0)
    progress = Column(Float, default=0.0)
    current_step = Column(String(100))
    error_message = Column(Text)

    # 配置 JSON
    config = Column(JSON)
    # {
    #   "domain_fields": [{"name": "...", "description": "..."}],
    #   "llm_model": "qwen-plus",
    #   "max_concurrent": 5,
    #   "dedup_field": "doi",
    #   "quality_threshold": 0.6,
    #   "enable_hitl": false,
    #   "extract_fields": ["related", "institution", "summary", ...]
    # }

    # 输出
    output_file_path = Column(String(500))

    # 时间戳
    created_at = Column(DateTime)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    updated_at = Column(DateTime)
```

### 4.2 表：`excel_extraction_rows`

```python
class ExcelExtractionRow(Base):
    __tablename__ = "excel_extraction_rows"

    id = Column(Integer, primary_key=True)
    task_id = Column(String(255), ForeignKey("excel_extraction_tasks.task_id", ondelete="CASCADE"))
    row_index = Column(Integer)  # 原始 Excel 行号

    # 原始数据
    raw_data = Column(JSON)  # {"doi": "...", "title": "...", "abstract": "...", ...}
    unique_key = Column(String(255), index=True)  # 用于去重（通常是 DOI）

    # 质量
    quality_score = Column(Float)  # 0.0 - 1.0
    quality_issues = Column(JSON)  # ["missing_abstract", ...]

    # 状态: pending -> processing -> completed -> hitl_pending -> hitl_approved/hitl_rejected/hitl_modified
    status = Column(String(50), default="pending")

    # 结果
    extraction_result = Column(JSON)
    # {
    #   "related": true,
    #   "institution": "清华大学",
    #   "summary": "...",
    #   "key_technologies": ["..."],
    #   "application_areas": ["..."],
    #   "domain_specific": {...}
    # }

    # HITL
    hitl_reviewed = Column(Integer, default=0)
    hitl_action = Column(String(50))  # approve/reject/modify
    hitl_modified_data = Column(JSON)
    reviewer_id = Column(Integer)

    error_message = Column(Text)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

---

## 五、API 端点设计

### 5.1 端点列表

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| POST | `/api/v1/excel-extraction/preview` | 上传 Excel 并预览数据 | Required |
| POST | `/api/v1/excel-extraction/tasks` | 创建任务，启动后台处理 | Required |
| GET | `/api/v1/excel-extraction/tasks` | 用户任务列表（分页） | Required |
| GET | `/api/v1/excel-extraction/tasks/{task_id}` | 任务详情 | Required |
| POST | `/api/v1/excel-extraction/tasks/{task_id}/cancel` | 取消任务 | Required |
| GET | `/api/v1/excel-extraction/tasks/{task_id}/rows` | 行数据列表（分页+过滤） | Required |
| GET | `/api/v1/excel-extraction/tasks/{task_id}/hitl-checkpoint` | HITL 检查点数据 | Required |
| POST | `/api/v1/excel-extraction/tasks/{task_id}/hitl-review` | 审核检查点 | Required |
| GET | `/api/v1/excel-extraction/tasks/{task_id}/download` | 下载结果 Excel | Required |

### 5.2 关键接口详细设计

#### 5.2.1 POST `/excel-extraction/preview`

**请求**：`multipart/form-data`
- `files`: List[UploadFile] - Excel 文件（.xlsx）
- `strategy_file`: UploadFile (可选) - Word 策略文档（.docx）

**响应**：
```json
{
  "success": true,
  "preview_id": "preview_xxx",
  "total_rows": 150,
  "columns": ["DOI", "Authors", "Title", "Abstract", "Year"],
  "preview_data": [
    {"DOI": "10.xxx", "Title": "...", "Abstract": "...", "quality_score": 0.85}
  ],
  "quality_stats": {
    "high_quality": 120,
    "medium_quality": 20,
    "low_quality": 10
  },
  "dedup_stats": {
    "original": 160,
    "after_dedup": 150,
    "duplicates": 10
  },
  "domain_fields": [
    {"name": "材料体系", "description": "研究涉及的材料类型"}
  ],
  "message": "数据预览成功"
}
```

#### 5.2.2 POST `/excel-extraction/tasks`

**请求**：
```json
{
  "preview_id": "preview_xxx",
  "task_name": "文献筛选任务",
  "config": {
    "domain_fields": [...],
    "llm_model": "qwen-plus",
    "max_concurrent": 5,
    "dedup_field": "doi",
    "quality_threshold": 0.6,
    "enable_hitl": false,
    "extract_fields": ["related", "institution", "summary", "key_technologies", "application_areas"]
  }
}
```

**响应**：
```json
{
  "success": true,
  "task_id": "task_xxx",
  "status": "processing",
  "total_rows": 150,
  "message": "任务已创建并开始处理"
}
```

---

## 六、服务层设计

### 6.1 核心函数列表

```python
# excel_extraction_service.py

# === 文件处理 ===
async def upload_and_preview_excel(files, strategy_file) -> Dict
    """上传 Excel，合并数据，质量评分，去重，返回预览"""

async def parse_strategy_word(file) -> Dict
    """解析 Word 策略文档，提取领域字段定义"""

# === 任务管理 ===
async def create_extraction_task(task_name, user_id, preview_data, config) -> Dict
    """创建任务，写入 DB，启动后台处理"""

async def run_extraction_task_background(task_id) -> None
    """后台异步执行任务（asyncio.create_task 启动）"""

# === 核心处理 ===
async def _process_single_row(row, config, semaphore) -> Dict
    """处理单行：构建 prompt → LLM 调用 → 解析结果"""

def _build_extraction_prompt(raw_data, extract_fields, domain_fields) -> str
    """动态构建 LLM 评估 prompt"""

async def _call_llm_structured(prompt, model) -> Dict
    """调用 LLMService，返回结构化 JSON"""

# === HITL ===
async def get_hitl_checkpoint(task_id) -> Dict
    """获取待审核行数据"""

async def review_hitl_checkpoint(task_id, action, row_ids, modified_data, reviewer_id) -> Dict
    """审核检查点：approve/reject/modify"""

# === 导出 ===
async def export_task_results_excel(task_id) -> str
    """生成结果 Excel 文件路径"""

# === CRUD ===
async def get_task_detail(task_id, user_id) -> Dict
async def get_user_tasks(user_id, page, page_size) -> Dict
async def cancel_task(task_id, user_id) -> Dict
async def get_rows_by_task(task_id, page, page_size, status) -> Dict
```

### 6.2 处理流程

```
run_extraction_task_background(task_id):
    1. 更新状态 → validating
    2. 验证数据完整性
    3. 更新状态 → processing
    4. asyncio.Semaphore(max_concurrent) 控制并发
    5. 并行处理每行:
       - 构建 prompt
       - LLMService.chat(json_mode=True)
       - parse_json_response()
       - 更新行状态
       - WebSocket 推送进度
    6. 如 enable_hitl=True:
       - 更新状态 → hitl_review
       - WebSocket 推送 "hitl_checkpoint" 事件
       - 等待人工审核
    7. 更新状态 → exporting
    8. 生成 Excel 结果文件
    9. 更新状态 → completed
```

### 6.3 LLM Prompt 设计

```python
def _build_extraction_prompt(raw_data, extract_fields, domain_fields):
    """构建结构化评估 prompt"""

    field_definitions = {
        "related": "是否与目标研究领域相关（boolean: true/false）",
        "institution": "第一作者所属机构名称（string）",
        "summary": "论文核心内容摘要，200字以内（string）",
        "key_technologies": "使用的关键技术/方法列表（string[]）",
        "application_areas": "应用领域列表（string[]）",
    }

    # 添加领域特定字段
    for f in domain_fields:
        field_definitions[f["name"]] = f["description"]

    prompt = f"""请分析以下论文题录数据，按指定字段提取信息。

论文数据：
- DOI: {raw_data.get('doi', 'N/A')}
- 标题: {raw_data.get('title', 'N/A')}
- 作者: {raw_data.get('authors', 'N/A')}
- 摘要: {raw_data.get('abstract', 'N/A')}

需要提取的字段：
{json.dumps(field_definitions, ensure_ascii=False, indent=2)}

请以 JSON 格式返回结果，所有字段必须有值（无法确定时填 null）。
JSON 格式示例：
{{"related": true, "institution": "xxx大学", "summary": "...", ...}}"""

    return prompt
```

---

## 七、前端页面设计

### 7.1 页面结构（在 BatchExtraction.vue 中添加 Tab）

```
+----------------------------------------------------------+
|  批量处理                                                 |
|  [PDF 批量提取] [Excel 题录提取]  ← el-tabs               |
+----------------------------------------------------------+

Excel 题录提取 Tab 内容:
+----------------------------------------------------------+
|  [el-steps]                                               |
|  1.上传文件 → 2.配置预览 → 3.处理监控 → 4.结果下载         |
+----------------------------------------------------------+
```

### 7.2 步骤详情

#### 步骤 1：上传文件

```
+----------------------------------------------------------+
|  el-upload (拖拽上传，多选 .xlsx 文件)                     |
|                                                           |
|  [可选] 上传策略 Word 文档 (.docx)                         |
|                                                           |
|  [el-button] 上传并预览                                    |
+----------------------------------------------------------+
```

#### 步骤 2：配置与预览

```
+----------------------------------------------------------+
|  左侧（60%）: 数据预览表格                                 |
|    el-table (前10行预览)                                  |
|    列: DOI | Title | Abstract | 质量评分                  |
|    统计: 总行数、高质量、低质量、去重信息                   |
|                                                           |
|  右侧（40%）: 配置面板                                     |
|    - 任务名称 (input)                                     |
|    - LLM 模型 (select: qwen-plus/qwen-max)                |
|    - 提取字段 (checkbox-group)                            |
|    - 领域特定字段 (动态表单，可添加删除)                    |
|    - 质量阈值 (slider 0.0-1.0)                            |
|    - 最大并发 (input-number 1-10)                         |
|    - 启用 HITL (switch)                                   |
|    [el-button type="primary"] 创建任务并开始处理           |
+----------------------------------------------------------+
```

#### 步骤 3：处理监控

```
+----------------------------------------------------------+
|  整体进度                                                 |
|    el-progress (percentage)                              |
|    状态: [el-tag] 处理中                                  |
|    进度: 45/100 行 | 成功: 40 | 失败: 5                    |
|                                                           |
|  [HITL 审核区域 - 仅在 hitl_review 状态显示]               |
|    el-table (可多选)                                      |
|    列: 原始数据 | LLM 结果 | 可编辑修改                    |
|    操作: [全部通过] [全部拒绝] [批量修改]                   |
|                                                           |
|  历史任务列表                                             |
|    el-table (任务列表)                                    |
+----------------------------------------------------------+
```

#### 步骤 4：结果下载

```
+----------------------------------------------------------+
|  任务完成摘要                                             |
|    - 总行数: 150                                          |
|    - 成功: 145                                            |
|    - 失败: 5                                              |
|    - 相关文献: 85                                         |
|                                                           |
|  [el-button type="success"] 下载 Excel 结果文件            |
|  [el-button] 开始新任务                                   |
+----------------------------------------------------------+
```

### 7.3 WebSocket 事件

```typescript
// 监听的事件类型
interface ExcelExtractionProgress {
  event: "excel_extraction_progress"
  data: {
    task_id: string
    step: "validating" | "processing" | "hitl_review" | "exporting" | "completed"
    progress: number
    processed_rows: number
    total_rows: number
    message: string
  }
}

interface ExcelExtractionHITL {
  event: "excel_extraction_hitl"
  data: {
    task_id: string
    pending_count: number
    message: string
  }
}
```

---

## 八、实现顺序

### Phase 1: 基础框架（不依赖 LLM）

| 序号 | 任务 | 预估时间 |
|------|------|----------|
| 1.1 | 创建数据库模型 `excel_extraction.py` | 30分钟 |
| 1.2 | 创建 Schema `excel_extraction.py` | 30分钟 |
| 1.3 | 创建 API 路由骨架（空实现） | 30分钟 |
| 1.4 | 在 `main.py` 注册路由 | 10分钟 |
| 1.5 | 添加 `python-docx` 到 requirements.txt | 5分钟 |
| 1.6 | 创建前端类型定义 `excel_extraction.ts` | 20分钟 |
| 1.7 | 创建前端 API 封装 `excel_extraction.ts` | 30分钟 |

### Phase 2: 文件上传与数据预处理

| 序号 | 任务 | 预估时间 |
|------|------|----------|
| 2.1 | 实现 `upload_and_preview_excel`（pandas 合并+质量评分+去重） | 1小时 |
| 2.2 | 实现 `parse_strategy_word`（python-docx 解析） | 30分钟 |
| 2.3 | 实现预览 API 端点 | 30分钟 |
| 2.4 | 前端步骤 1-2 页面 | 1.5小时 |

### Phase 3: LLM 批量评估

| 序号 | 任务 | 预估时间 |
|------|------|----------|
| 3.1 | 实现 `_build_extraction_prompt`（动态 prompt） | 30分钟 |
| 3.2 | 实现 `_call_llm_structured`（复用 LLMService） | 30分钟 |
| 3.3 | 实现 `run_extraction_task_background`（后台任务） | 1小时 |
| 3.4 | 实现任务创建/详情/取消 API | 30分钟 |
| 3.5 | WebSocket 进度推送集成 | 30分钟 |
| 3.6 | 前端步骤 3 页面（进度监控） | 1小时 |

### Phase 4: HITL 检查点

| 序号 | 任务 | 预估时间 |
|------|------|----------|
| 4.1 | 实现 `get_hitl_checkpoint` | 30分钟 |
| 4.2 | 实现 `review_hitl_checkpoint` | 30分钟 |
| 4.3 | HITL API 端点 | 30分钟 |
| 4.4 | 前端 HITL 审核 UI | 1小时 |

### Phase 5: 结果导出与完善

| 序号 | 任务 | 预估时间 |
|------|------|----------|
| 5.1 | 实现 `export_task_results_excel` | 30分钟 |
| 5.2 | 下载 API 端点 | 20分钟 |
| 5.3 | 前端步骤 4 页面（下载） | 30分钟 |
| 5.4 | 错误处理与边界情况 | 1小时 |
| 5.5 | 完整流程测试 | 1小时 |

---

## 九、风险与应对

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| LLM 返回无效 JSON | 行处理失败 | 3次重试 + 正则兜底提取 |
| 大量数据内存溢出 | 服务崩溃 | 分批处理（每批100行） |
| API 限流 | 处理变慢 | Semaphore + 指数退避重试 |
| Excel 格式不兼容 | 上传失败 | 仅支持 .xlsx，明确错误提示 |
| 后台任务意外终止 | 状态不一致 | 定期持久化到 MySQL |

---

## 十、验证方式

1. **后端单元测试**：
   - 上传示例 Excel（50行数据）
   - 验证质量评分、去重逻辑
   - 验证 LLM 调用返回结构化 JSON

2. **前端流程测试**：
   - 完整走通 4 步流程
   - WebSocket 进度实时更新
   - HITL 审核交互正常
   - 下载 Excel 文件正确

3. **边界情况测试**：
   - 空 Excel 文件
   - 缺少必需列（DOI/Title/Abstract）
   - 重复 DOI 数据
   - LLM API 异常

---

## 十一、关键文件参考

### 需要复用的 v3 现有代码：

| 文件 | 复用内容 |
|------|----------|
| `backend/app/services/llm_service.py` | LLMService.chat(json_mode=True), parse_json_response() |
| `backend/app/services/batch_service.py` | 任务 CRUD 模式、asyncio.create_task 后台任务 |
| `backend/app/api/v1/websocket.py` | ConnectionManager, send_progress() |
| `frontend/src/utils/websocket.ts` | socket.io-client 连接管理 |
| `frontend/src/api/request.ts` | Axios 请求封装模式 |
| `frontend/src/views/BatchExtraction.vue` | 页面布局风格、el-steps 使用方式 |

---

## 十二、审批检查点

在实现前请确认以下问题：

1. **数据库模型设计是否合理？**
   - 两张表的设计是否满足需求？
   - 是否需要调整字段？

2. **API 端点设计是否完整？**
   - 是否有遗漏的端点？
   - 响应格式是否满足前端需求？

3. **前端页面设计是否可行？**
   - Tab 方案是否合适？还是应该新建独立页面？
   - 步骤划分是否合理？

4. **HITL 审核方案是否满足需求？**
   - 批量审核是否足够？还是需要逐条审核？

5. **提取字段列表是否需要调整？**
   - 当前默认: related, institution, summary, key_technologies, application_areas
   - 是否需要添加其他字段？

---

*本文档为 Excel 题录数据批量提取功能的详细实现计划，审批通过后开始实施。*