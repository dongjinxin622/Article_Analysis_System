# Step6: 异步任务系统 - 详细计划

> 预计周期: 1 周 | 状态: 待开始 | 前置依赖: Step5

---

## 一、任务清单

### 6.1 Celery Worker 配置

**目标**：配置 Celery 任务队列

**文件**：`backend/app/tasks/__init__.py`

**配置内容**：
```python
from celery import Celery

celery_app = Celery(
    "scipdf_tasks",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
)
```

---

### 6.2 PDF 处理任务

**目标**：创建 PDF 异步处理任务

**文件**：`backend/app/tasks/pdf_tasks.py`

**任务设计**：
```python
@celery_app.task(bind=True, max_retries=3)
def parse_pdf_task(self, file_path: str, user_id: int):
    """Celery 异步 PDF 解析任务"""
    try:
        result = pdf_service.parse_pdf_sync(file_path)
        update_paper_status(user_id, result)
        send_progress_notification(user_id, "pdf_completed", result)
    except Exception as e:
        self.retry(countdown=60, exc=e)
```

---

### 6.3 NER 处理任务

**目标**：创建 NER 异步处理任务

**文件**：`backend/app/tasks/ner_tasks.py`

**任务设计**：
```python
@celery_app.task(bind=True, max_retries=3)
def ner_task(self, result_id: str, config_id: int, user_id: int):
    """Celery 异步 NER 任务"""
    try:
        result = ner_service.process_ner_sync(result_id, config_id)
        update_ner_status(result)
        send_progress_notification(user_id, "ner_completed", result)
    except Exception as e:
        self.retry(countdown=60, exc=e)
```

---

### 6.4 批量处理任务

**目标**：创建批量处理任务

**文件**：`backend/app/tasks/batch_tasks.py`

**任务设计**：
```python
@celery_app.task(bind=True)
def batch_extraction_task(self, task_id: str, config: dict):
    """Celery 批量提取任务"""
    # 更新进度
    self.update_state(state='PROCESSING', meta={'progress': 0})

    # 执行各步骤
    for step in workflow_steps:
        # 执行步骤
        self.update_state(state='PROCESSING', meta={'progress': step_progress})

    return {'status': 'completed', 'result': results}
```

---

### 6.5 任务进度追踪

**目标**：实现任务进度追踪

**文件**：`backend/app/services/task_manager.py`

**功能**：
- 任务状态存储（Redis）
- 进度百分比更新
- 子任务进度
- 错误记录

---

### 6.6 WebSocket 实时推送

**目标**：实现 WebSocket 进度推送

**文件**：`backend/app/api/websocket.py`

**功能**：
```python
from fastapi import WebSocket

@app.websocket("/ws/tasks/{task_id}")
async def task_progress_ws(websocket: WebSocket, task_id: str):
    await websocket.accept()

    while True:
        # 从 Redis 获取任务状态
        task_status = await get_task_status(task_id)

        # 推送进度
        await websocket.send_json({
            "event": "task_progress",
            "data": task_status
        })

        if task_status['status'] in ['completed', 'failed']:
            break

        await asyncio.sleep(1)
```

---

### 6.7 Celery Beat 定时任务

**目标**：配置定时清理任务

**文件**：`backend/app/tasks/scheduled_tasks.py`

**任务列表**：
- 清理过期任务
- 清理临时文件
- 数据库备份

---

### 6.8 任务状态 API

**目标**：创建任务状态查询 API

**文件**：`backend/app/api/v1/task.py`

**API 接口**：

| 接口 | 方法 | 功能 |
|------|------|------|
| `/api/v1/tasks/{task_id}` | GET | 获取任务状态 |
| `/api/v1/tasks/{task_id}/cancel` | POST | 取消任务 |
| `/api/v1/tasks` | GET | 获取任务列表 |

---

## 二、执行顺序

1. 创建 Celery 配置
2. 创建 PDF 任务
3. 创建 NER 任务
4. 创建批量任务
5. 创建任务管理器
6. 创建 WebSocket 处理
7. 创建定时任务
8. 创建任务状态 API
9. 测试异步任务

---

## 三、检查标准

| 检查项 | 标准 |
|--------|------|
| Celery Worker | Worker 正常启动 |
| 任务提交 | 任务提交成功返回 task_id |
| 任务执行 | 任务正常执行完成 |
| 进度更新 | 任务进度实时更新 |
| WebSocket | 进度实时推送到前端 |
| 任务取消 | 任务取消正常执行 |
| Redis 存储 | 任务状态正确存储 |

---

## 四、参考文件列表

| v2 文件 | v3 目标位置 |
|---------|------------|
| `backend/services/task_manager.py` | `backend/app/services/task_manager.py` |
| `backend/services/batch_service.py` | `backend/app/tasks/batch_tasks.py` |
| 架构设计文档 Celery 配置 | Celery 配置 |

---

*Step6 完成后进入 Step7: 部署测试*