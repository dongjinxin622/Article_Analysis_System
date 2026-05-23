# 一键分析流程优化方案 - 并行处理

## 实施完成情况

**状态：已完成** (2026-04-23)

**并发数配置：20**

---

## 实际修改内容

### 1. task_processor.py - 并发数调整为20

**文件**: `backend/app/utils/task_processor.py`

**修改内容**:
```python
# AsyncTaskProcessor.__init__ 中的 max_concurrent 默认值
max_concurrent: int = 20  # 从50改为20

# process_with_llm 函数中的 max_concurrent 默认值
max_concurrent: int = 20  # 从50改为20
```

### 2. comprehensive_service.py - 后分析阶段并行化

**文件**: `backend/app/services/comprehensive_service.py`

**修改内容**:
- `run_full_analysis()` 方法中，技术路线、实验方案、Jc分析改为并行执行
- 使用 `asyncio.gather()` 并行等待三个分析任务
- 添加异常处理，任一分析失败不影响其他

```python
# 并行执行三个分析任务
tech_route_task = self._analyze_tech_route(...)
exp_scheme_task = self._analyze_exp_scheme(...)
jc_task = self._analyze_jc(...)

# 并行等待
tech_route_result, exp_scheme_result, jc_result = await asyncio.gather(
    tech_route_task, exp_scheme_task, jc_task,
    return_exceptions=True
)
```

---

## 已有并行机制（无需修改）

### NER 片段级并行
- `ner_service.py` 的 `process_ner_with_llm()` 调用 `task_processor.py` 的 `process_with_llm()`
- `task_processor.py` 内部使用 `asyncio.Semaphore(max_concurrent=20)` + `asyncio.gather()` 并行处理所有片段

### RE 片段级并行
- `re_service.py` 的 `process_re_for_ner()` 调用 `task_processor.py` 的 `process_with_llm()`
- 同样使用 `asyncio.Semaphore(max_concurrent=20)` + `asyncio.gather()` 并行处理

---

## 并行处理架构

```
PDF解析 (串行)
    ↓
章节分割 (sentences_data)
    ↓
NER (内部并行，并发数20)
    ├── 片段1 LLM调用
    ├── 片段2 LLM调用
    ├── 片段3 LLM调用
    └── ... (Semaphore控制并发)
    ↓
RE (内部并行，并发数20)
    ├── 片段1 LLM调用
    ├── 片段2 LLM调用
    └── ... (Semaphore控制并发)
    ↓
后分析阶段 (并行执行)
    ├── 技术路线分析 (asyncio.create_task)
    ├── 实验方案分析 (asyncio.create_task)
    └── Jc指标分析   (asyncio.create_task)
    ↓ (asyncio.gather等待)
LLM综合报告 (串行，依赖前面结果)
```

---

## 预期效果

| 阶段 | 原状态 | 优化后 |
|------|--------|--------|
| NER片段处理 | 并行(50并发) | 并行(20并发) |
| RE片段处理 | 并行(50并发) | 并行(20并发) |
| 后分析阶段 | 串行(依次执行) | 并行(同时执行) |
| 单篇PDF处理时间 | ~5-10分钟 | ~2-4分钟 |

---

## 文件修改清单

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `backend/app/utils/task_processor.py` | 并发数50→20 | ✓ |
| `backend/app/services/comprehensive_service.py` | 后分析并行化 | ✓ |
| `backend/app/services/ner_service.py` | 无需修改(已并行) | - |
| `backend/app/services/re_service.py` | 无需修改(已并行) | - |
| `backend/app/api/v1/comprehensive.py` | 无需修改 | - |

---

## 参考：v2中已有的并行处理代码

| 文件 | 函数 | 并行机制 |
|------|------|---------|
| `jc_service.py:1044` | `_run_llm_parallel` | asyncio.Semaphore + gather |
| `batch_service.py:225` | `run_batch_extraction` | Semaphore + gather |
| `task_processor.py:218` | `process_batch` | Semaphore + tqdm_asyncio.gather |