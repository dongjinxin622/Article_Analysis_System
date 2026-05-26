# 综合分析结果 MySQL 持久化计划

**时间**: 2026-05-23
**目标**: 综合分析任务成功后，将结果同步写入 MySQL，解决 Redis 2 小时 TTL 导致的旧数据丢失问题。

## 改动点

### 1. 新增模型 `backend/app/models/comprehensive.py`
- `ComprehensiveTask` 表，存储任务元信息和结果 JSON
- 字段: task_id, user_id, status, progress, current_step, message, result(JSON), error, params(JSON), created_at, updated_at, completed_at

### 2. 修改 `backend/app/models/__init__.py`
- 导出 `ComprehensiveTask`

### 3. 修改 `backend/app/api/v1/comprehensive.py`
- 任务成功后同步写入 MySQL
- `get_task_status`: Redis 未命中时回退查询 MySQL
- `get_user_tasks`: 合并 Redis + MySQL 结果
- `delete_task`: 同步删除 MySQL 记录

### 4. 验证
- 重启后端，确认表自动创建
- 发起一次综合分析，确认结果写入 MySQL
