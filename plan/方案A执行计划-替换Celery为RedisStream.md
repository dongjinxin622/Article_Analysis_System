# 方案 A 执行计划：替换 Celery 为 Redis Stream 异步任务引擎

> 基于 case_one Day37 代码直接复用 + 适配性修改  
> 分支：`feature/async-task-engine-upgrade`（已创建 ✅）  
> 状态：待审核

---

## 背景

现有项目使用 Celery + Redis Broker + WebSocket 推送，存在以下核心问题：

1. **任务状态易丢失** — Redis 2小时 TTL，进程重启后无法恢复
2. **缺乏死信机制** — 超过重试上限的任务无法追踪
3. **缺乏心跳检测** — 卡死的任务永远停在 running 状态
4. **WebSocket 跨进程推送失败** — Celery worker 是独立进程，ws_manager 是内存字典
5. **缺乏任务管理 UI** — 用户无法直观查看任务列表、进度、失败原因
6. **`asyncio.run()` 桥接问题** — Celery 同步框架与异步 DB 操作的强制桥接

case_one 项目已实现基于 Redis Stream 的完整异步任务引擎，具备持久化、死信、心跳、孤儿恢复、SSE 推送等能力，代码成熟可直接复用。

---

## 执行策略：直接复制 + 针对性修改

**原则**：尽可能复制 case_one 的代码，只在 ORM 层和项目适配层做修改。

### 可直接复用的代码（60%）

- `backend/app/core/tasks/` — 任务引擎核心（constants/engine/worker/stream/scavenger）
- `backend/app/schemas/tasks.py` — Pydantic Schema
- `backend/app/routers/tasks.py` — FastAPI 路由
- `backend/worker.py` — Worker 入口
- `frontend/src/pages/Tasks.vue` — 任务管理页面
- `frontend/src/components/task/*.vue` — 任务组件（6个）
- `frontend/src/composables/use*.ts` — 组合式函数（4个）
- `frontend/src/api/task.ts` — API 封装

### 必须重写的代码（40%）

- `backend/app/models/tasks.py` — 数据模型（SQLModel → SQLAlchemy）
- `backend/app/services/tasks.py` — 服务层（SQLModel AsyncSession → SQLAlchemy AsyncSession）
- `backend/app/services/task_metrics.py` — 指标服务（同上）
- 所有 Celery 任务 → 任务处理器声明

---

## 分步执行计划

### 步骤 1：复制任务引擎核心（`backend/app/core/tasks/`）

**操作**：直接复制 case_one 的 6 个文件，修改导入路径

**需修改的导入路径映射**：
```
case_one                            → SciPDF
─────────────────────────────────────────────────────
app.core.tasks.constants            → backend.app.core.tasks.constants
app.models.tasks                    → backend.app.models.tasks
app.schemas.tasks                   → backend.app.schemas.tasks
app.services.tasks                  → backend.app.services.tasks
app.core.database.get_session       → backend.app.api.deps.get_db
app.core.config.settings            → backend.app.core.config.settings
sqlmodel.ext.asyncio.session        → sqlalchemy.ext.asyncio
sqlmodel.select                     → sqlalchemy.select
sqlmodel.col                        → sqlalchemy（需重写查询）
```

**文件清单**：
| 源文件（case_one） | 目标文件（SciPDF） | 改动程度 |
|-------------------|-------------------|---------|
| `core/tasks/__init__.py` | `backend/app/core/tasks/__init__.py` | 微改（导入路径） |
| `core/tasks/constants.py` | `backend/app/core/tasks/constants.py` | 无改动 |
| `core/tasks/engine.py` | `backend/app/core/tasks/engine.py` | 中改（导入路径 + ORM 适配） |
| `core/tasks/worker.py` | `backend/app/core/tasks/worker.py` | 中改（导入路径 + ORM 适配） |
| `core/tasks/stream.py` | `backend/app/core/tasks/stream.py` | 中改（导入路径 + ORM 适配） |
| `core/tasks/scavenger.py` | `backend/app/core/tasks/scavenger.py` | 中改（导入路径） |

---

### 步骤 2：重写数据模型（`backend/app/models/tasks.py`）

**操作**：基于 case_one 的 TaskJob/TaskItem/TaskDeadLetter 模型，用 SQLAlchemy 重写

**关键改动**：
- `SQLModel` → `SQLAlchemy` Column 声明式模型
- 继承现有项目的 `Base` 类（`backend/app/models/base.py`）
- 使用现有项目的 `utc_now()` 工具函数（或自定义）
- 表名保持 `task_jobs` / `task_items` / `task_dead_letters`（不加 `af_` 前缀）

**模型对照**：

```
TaskStatus 枚举（直接复制，无改动）
TaskJob（6个→约20个字段，SQLAlchemy Column 声明）
TaskItem（约20个字段，SQLAlchemy Column 声明）
TaskDeadLetter（约10个字段，SQLAlchemy Column 声明）
```

**具体字段定义（从 case_one 复制，转 SQLAlchemy）**：

```python
# TaskJob
id, public_id, task_type, queue_name, status, priority,
total_items, completed_items, failed_items,
payload(JSON), result(JSON), error_code, error_message,
scheduled_at, started_at, finished_at,
created_by, project_public_id,
created_at, updated_at

# TaskItem
id, public_id, job_id(FK→task_jobs.id),
task_type, item_type, item_key, status, priority,
payload(JSON), result(JSON), error_code, error_message,
attempt_count, max_attempts, worker_id,
heartbeat_at, scheduled_at, started_at, finished_at,
stream_id,
created_at, updated_at

# TaskDeadLetter
id, task_type, item_type, item_key,
payload(JSON), error_code, error_message,
attempt_count, max_attempts, original_item_public_id,
worker_id, stream_id,
created_at
```

---

### 步骤 3：重写任务 Schema（`backend/app/schemas/tasks.py`）

**操作**：直接复制 case_one 的 Schema 文件，微改导入路径

**改动**：
- `from app.models.tasks import TaskStatus` → `from backend.app.models.tasks import TaskStatus`
- 其他 Pydantic Schema 无需改动（纯 BaseModel 定义）

---

### 步骤 4：重写任务服务层（`backend/app/services/tasks.py` + `task_metrics.py`）

**操作**：基于 case_one 的服务层代码，适配 SQLAlchemy

**关键改动**：

| case_one 代码 | SciPDF 替换 |
|--------------|------------|
| `sqlmodel.select(TaskJob)` | `sqlalchemy.select(TaskJob)` |
| `sqlmodel.col(TaskJob.status)` | `TaskJob.status`（直接用 Column 属性） |
| `session.exec(select(...))` | `await session.execute(select(...))` |
| `session.add(job)` | `session.add(job)`（不变） |
| `await session.commit()` | `await session.commit()`（不变） |
| `await session.refresh(job)` | `await session.refresh(job)`（不变） |
| `job.model_validate(...)` | 手动属性赋值或 `job.__dict__.update(...)` |

**核心函数清单（从 case_one 复制并适配）**：

```
create_task_job()
append_task_items()
list_task_jobs()
get_task_job()
update_task_job_status()
update_task_item_status()
mark_task_item_running()      ← 条件更新 WHERE status IN (PENDING, QUEUED)
heartbeat_task_item()          ← UPDATE heartbeat_at WHERE worker_id = ...
record_task_item_failure()     ← 指数退避重试 or 死信
pause_task_job()
resume_task_job()
cancel_task_job()
retry_task_item()
recover_stale_running_task_items()
list_due_pending_task_item_public_ids()
create_task_dead_letter()
refresh_task_job_progress()    ← 统计子项状态刷新 Job 计数
```

---

### 步骤 5：适配任务路由（`backend/app/routers/tasks.py`）

**操作**：复制 case_one 的路由文件，修改导入路径和依赖注入

**改动**：
- `from app.core.database import get_session` → `from backend.app.api.deps import get_db`
- `from app.core.tasks.engine import ...` → `from backend.app.core.tasks.engine import ...`
- `from app.middlewares.common import ...` → 使用现有项目的 JWT 认证中间件
- 路由注册方式适配现有项目的 `api_router`

**API 端点（从 case_one 复制）**：

```
POST /api/v1/tasks                    → 创建任务
POST /api/v1/tasks/enqueue            → 创建并投递任务
POST /api/v1/tasks/batch              → 批量创建
GET  /api/v1/tasks                    → 分页查询任务列表
GET  /api/v1/tasks/{id}               → 任务详情
POST /api/v1/tasks/{id}/cancel        → 取消任务
POST /api/v1/tasks/{id}/pause         → 暂停任务
POST /api/v1/tasks/{id}/resume        → 恢复任务
DELETE /api/v1/tasks/{id}             → 删除任务
POST /api/v1/tasks/items/{id}/retry   → 重试子项
GET  /api/v1/tasks/metrics            → 指标统计
```

---

### 步骤 6：迁移 Celery 任务为 Redis Stream 任务处理器

**操作**：将 12 个 Celery 任务函数改写为 `AsyncTaskDefinition` 声明

**现有 Celery 任务 → 新处理器映射**：

| Celery 任务 | 新处理器 task_type | 处理器函数 |
|------------|-------------------|-----------|
| `parse_pdf_task` | `scipdf.pdf.parse` | `parse_pdf_handler()` |
| `extract_figures_task` | `scipdf.pdf.extract_figures` | `extract_figures_handler()` |
| `ner_extraction_task` | `scipdf.ner.extract` | `ner_extraction_handler()` |
| `ner_batch_task` | `scipdf.ner.batch` | `ner_batch_handler()` |
| `re_extraction_task` | `scipdf.re.extract` | `re_extraction_handler()` |
| `re_batch_task` | `scipdf.re.batch` | `re_batch_handler()` |
| `full_pipeline_task` | `scipdf.pipeline.full` | `full_pipeline_handler()` |
| `domain_analysis_batch_task` | `scipdf.domain.batch` | `domain_batch_handler()` |

**迁移模式**（每个任务统一改写）：

```python
# 旧 Celery 任务：
@celery_app.task(bind=True, max_retries=3)
def parse_pdf_task(self, file_path, user_id, options=None):
    task_id = self.request.id
    task_manager.update_task_status(task_id, "processing", ...)
    result = asyncio.run(process_pdf(...))
    task_manager.update_task_status(task_id, "completed", ...)
    asyncio.run(ws_manager.send_progress(...))

# 新 Redis Stream 处理器：
async def parse_pdf_handler(context: Any) -> dict:
    payload = context.message.payload
    result = await process_pdf(
        file_path=payload["file_path"],
        file_name=payload["file_name"],
        user_id=payload["user_id"]
    )
    return result

ASYNC_TASKS = (
    AsyncTaskDefinition("scipdf.pdf.parse", parse_pdf_handler),
)
```

**处理器注册文件**（新建 `backend/app/tasks/pdf.py`）：

```
backend/app/tasks/
├── __init__.py     ← 导入所有模块的 ASYNC_TASKS
├── pdf.py          ← PDF 处理任务声明
├── ner.py          ← NER 任务声明
├── re.py           ← RE 任务声明
├── pipeline.py     ← 流水线任务声明
├── domain.py       ← 领域分析任务声明
```

**定时任务**：保留 Celery Beat 处理清理/健康检查等维护任务（这些不需要 Redis Stream 引擎）

---

### 步骤 7：修改应用入口（`backend/app/main.py`）

**操作**：在 FastAPI 启动时初始化 Redis 客户端，注册任务引擎

**改动**：
- 新增 `lifespan` 事件：启动时创建 Redis 客户端并传给引擎
- 注册新的 `tasks_router`
- 保留 WebSocket 路由（兼容性，后续可逐步替换为 SSE）

```python
# main.py 中的 lifespan
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 初始化 Redis 客户端
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    default_async_task_engine.redis_client = redis_client
    default_async_task_engine.session_maker = AsyncSessionLocal
    default_async_task_engine.register_async_task_modules()
    yield
    await redis_client.aclose()
```

---

### 步骤 8：修改配置文件（`backend/app/core/config.py` + `.env`）

**操作**：新增 Redis Stream 和 Worker 相关配置

**config.py 新增字段**：

```python
# Redis Stream 配置
REDIS_TASK_STREAM_NAME: str = "task:stream"
REDIS_TASK_CONSUMER_GROUP: str = "task-workers"
REDIS_TASK_STREAM_MAX_LEN: int = 10000

# Worker 配置
ASYNC_TASK_MODULES: str = "backend.app.tasks.pdf,backend.app.tasks.ner,backend.app.tasks.re,backend.app.tasks.pipeline,backend.app.tasks.domain"
ASYNC_TASK_WORKER_MAX_CONCURRENCY: int = 4
ASYNC_TASK_WORKER_TASK_TIMEOUT_SECONDS: float = 3600.0
ASYNC_TASK_WORKER_MAX_RETRIES: int = 3
ASYNC_TASK_WORKER_RETRY_BACKOFF_SECONDS: float = 30.0
ASYNC_TASK_WORKER_HEARTBEAT_INTERVAL_SECONDS: float = 30.0
ASYNC_TASK_STALE_RUNNING_TIMEOUT_SECONDS: float = 600.0
ASYNC_TASK_WORKER_LOG_ENABLED: bool = True
ASYNC_TASK_WORKER_BATCH_SIZE: int = 4
ASYNC_TASK_WORKER_BLOCK_MS: int = 2000
ASYNC_TASK_WORKER_SHUTDOWN_TIMEOUT_SECONDS: float = 30.0
```

**.env 新增**：

```bash
# Redis Stream
REDIS_TASK_STREAM_NAME=task:stream
REDIS_TASK_CONSUMER_GROUP=task-workers
REDIS_TASK_STREAM_MAX_LEN=10000

# 异步任务引擎
ASYNC_TASK_MODULES=backend.app.tasks.pdf,backend.app.tasks.ner,backend.app.tasks.re,backend.app.tasks.pipeline,backend.app.tasks.domain
ASYNC_TASK_WORKER_MAX_CONCURRENCY=4
ASYNC_TASK_WORKER_TASK_TIMEOUT_SECONDS=3600
ASYNC_TASK_WORKER_MAX_RETRIES=3
ASYNC_TASK_WORKER_RETRY_BACKOFF_SECONDS=30
ASYNC_TASK_STALE_RUNNING_TIMEOUT_SECONDS=600
```

---

### 步骤 9：更新 Docker 配置（`docker-compose.yml`）

**操作**：将 Celery Worker 容器替换为新的 Task Worker

**改动**：

```yaml
# 旧 Celery Worker：
celery-worker:
  command: celery -A backend.app.tasks worker -B --concurrency=4 -Q default,pdf,ner,re,batch,scheduled

# 新 Task Worker：
task-worker:
  build: ...
  command: python backend/worker.py
  volumes:
    - backend-data:/app/data
    - ./stanza_resources_v112:/app/stanza_resources:ro
    - ./scipdf:/app/scipdf:ro
  env_file: .env
```

**新增 SSE 端点**（Nginx 配置需支持长连接）：

```nginx
# nginx.conf 新增
location /api/v1/tasks/ {
    proxy_pass http://backend:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 3600s;  # SSE 长连接
}
```

---

### 步骤 10：编写数据库迁移脚本（DDL）

**操作**：新增 3 个表的 DDL

```sql
-- 任务主表
CREATE TABLE task_jobs (
    id SERIAL PRIMARY KEY,
    public_id VARCHAR(36) UNIQUE NOT NULL,
    task_type VARCHAR(100) NOT NULL,
    queue_name VARCHAR(100) DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    total_items INTEGER DEFAULT 0,
    completed_items INTEGER DEFAULT 0,
    failed_items INTEGER DEFAULT 0,
    payload JSON DEFAULT '{}',
    result JSON DEFAULT '{}',
    error_code VARCHAR(100) DEFAULT '',
    error_message TEXT DEFAULT '',
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    created_by VARCHAR(36) DEFAULT '',
    project_public_id VARCHAR(36) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_task_jobs_public_id ON task_jobs(public_id);
CREATE INDEX idx_task_jobs_status ON task_jobs(status);
CREATE INDEX idx_task_jobs_task_type ON task_jobs(task_type);

-- 任务子项表
CREATE TABLE task_items (
    id SERIAL PRIMARY KEY,
    public_id VARCHAR(36) UNIQUE NOT NULL,
    job_id INTEGER NOT NULL REFERENCES task_jobs(id) ON DELETE CASCADE,
    task_type VARCHAR(100) NOT NULL,
    item_type VARCHAR(100) DEFAULT '',
    item_key VARCHAR(255) DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    priority INTEGER DEFAULT 0,
    payload JSON DEFAULT '{}',
    result JSON DEFAULT '{}',
    error_code VARCHAR(100) DEFAULT '',
    error_message TEXT DEFAULT '',
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    worker_id VARCHAR(100) DEFAULT '',
    heartbeat_at TIMESTAMP,
    scheduled_at TIMESTAMP,
    started_at TIMESTAMP,
    finished_at TIMESTAMP,
    stream_id VARCHAR(100) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_task_items_public_id ON task_items(public_id);
CREATE INDEX idx_task_items_job_id ON task_items(job_id);
CREATE INDEX idx_task_items_status ON task_items(status);

-- 死信表
CREATE TABLE task_dead_letters (
    id SERIAL PRIMARY KEY,
    task_type VARCHAR(100) NOT NULL,
    item_type VARCHAR(100) DEFAULT '',
    item_key VARCHAR(255) DEFAULT '',
    payload JSON DEFAULT '{}',
    error_code VARCHAR(100) DEFAULT '',
    error_message TEXT DEFAULT '',
    attempt_count INTEGER DEFAULT 0,
    max_attempts INTEGER DEFAULT 3,
    original_item_public_id VARCHAR(36) DEFAULT '',
    worker_id VARCHAR(100) DEFAULT '',
    stream_id VARCHAR(100) DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_task_dead_letters_task_type ON task_dead_letters(task_type);
CREATE INDEX idx_task_dead_letters_created_at ON task_dead_letters(created_at);
```

---

### 步骤 11：复制并适配前端任务管理界面

**操作**：从 case_one 复制前端代码，修改 API 基础路径

**文件清单**：

| 源文件（case_one） | 目标文件（SciPDF） | 改动 |
|-------------------|-------------------|------|
| `frontend/src/pages/Tasks.vue` | `frontend/src/views/Tasks.vue` | API路径、UI风格适配 |
| `frontend/src/components/task/*.vue` (6个) | `frontend/src/components/task/*.vue` | 同上 |
| `frontend/src/api/task.ts` | `frontend/src/api/task.ts` | 基础URL适配 |
| `frontend/src/composables/use*.ts` (4个) | `frontend/src/composables/use*.ts` | 无改动 |

**路由注册**（`frontend/src/router/index.ts`）：

```typescript
{
  path: '/tasks',
  name: 'Tasks',
  component: () => import('@/views/Tasks.vue'),
  meta: { requiresAuth: true }
}
```

**新增依赖**：

```bash
npm install apexcharts vue3-apexcharts
```

---

### 步骤 12：删除 Celery 相关代码

**操作**：清理不再需要的 Celery 代码

**删除的文件**：
- `backend/app/tasks/__init__.py`（Celery app 定义）→ 替换为新引擎注册
- `backend/app/tasks/pdf_tasks.py`
- `backend/app/tasks/ner_tasks.py`
- `backend/app/tasks/re_tasks.py`
- `backend/app/tasks/batch_tasks.py`
- `backend/app/services/task_manager.py`（Redis TaskManager）→ 替换为新引擎服务

**保留的文件**：
- `backend/app/tasks/scheduled_tasks.py` — Celery Beat 定时清理任务（暂时保留）
- `backend/app/api/websocket.py` — WebSocket 推送（暂时保留，后续可替换为 SSE）

---

## 执行顺序和预估时间

| 步骤 | 内容 | 预估时间 |
|------|------|---------|
| 1 | 复制引擎核心代码 | 2h |
| 2 | 重写数据模型 | 1.5h |
| 3 | 重写 Schema | 0.5h |
| 4 | 重写服务层 | 3h |
| 5 | 适配路由 | 1h |
| 6 | 迁移 Celery 任务为处理器 | 4h |
| 7 | 修改应用入口 | 0.5h |
| 8 | 修改配置文件 | 0.5h |
| 9 | 更新 Docker 配置 | 0.5h |
| 10 | 编写数据库迁移 DDL | 0.5h |
| 11 | 复制前端界面 | 2h |
| 12 | 删除 Celery 代码 | 0.5h |
| **总计** | | **~16h** |

---

## 验证计划

### 本地验证

```bash
# 1. 创建数据目录
mkdir -p data/{uploads,results,ner_results,re_results,failed_logs}

# 2. 执行数据库迁移
psql -h localhost -U root -d article_analysis_v3 -f ddl_task_engine.sql

# 3. 启动后端
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

# 4. 启动 Task Worker
python backend/worker.py

# 5. 验证 API
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/tasks

# 6. 验证前端
cd frontend && npm run dev
# 访问 http://localhost:5173/tasks
```

### 集成验证

```bash
# 1. 上传 PDF → 创建 PDF 解析任务
# 2. NER 提取 → 创建 NER 任务
# 3. 查看任务列表和进度
# 4. 测试取消任务
# 5. 测试重试失败任务
# 6. 查看死信记录
```

### 回滚方案

```bash
# 任何步骤失败，立即回滚：
git checkout v0.3
# 或回退到特定提交：
git reset --hard <commit-hash>
```

---

## 待决事项

1. **定时任务策略**：清理/健康检查等维护任务是否也迁移到 Redis Stream，还是继续用 Celery Beat？
   - 推荐：暂时保留 Celery Beat，后续逐步迁移

2. **WebSocket vs SSE**：是否立即替换 WebSocket 为 SSE？
   - 推荐：暂时保留 WebSocket，新增 SSE 端点，后续逐步替换

3. **Excel 提取任务**：是否也迁移到 Redis Stream？
   - 推荐：暂不迁移，Excel 提取用 LangGraph Agent + WebSocket，架构不同

4. **API 路径**：任务管理 API 是否沿用 `/api/v1/tasks`？
   - 推荐：是的，与现有项目风格一致
