# Step8: 功能完善计划

> 预计周期: 3-5 天 | 状态: 待开始 | 前置依赖: Redis已部署 ✅

---

## 一、Redis 状态确认

| 项目 | 状态 | 说明 |
|------|------|------|
| Redis 部署 | ✅ 完成 | localhost:6379 |
| Redis 密码 | ✅ 配置 | Djx3861599! |
| .env 更新 | ✅ 完成 | REDIS_URL 已配置 |
| Celery 配置 | ✅ 正常 | Broker URL 正确 |
| Celery Worker | ❌ 待启动 | 需手动启动 |

---

## 二、任务清单

### 2.1 高优先级任务

#### 任务 1: 启动 Celery Worker

**目标**: 启动 Celery Worker 使异步任务系统生效

**步骤**:
```bash
# 启动 Celery Worker（在backend目录）
cd backend
celery -A backend.app.tasks worker -l info -P solo

# 或启动多队列 Worker
celery -A backend.app.tasks worker -l info -Q pdf,ner,re,batch,default -P solo
```

**验证标准**:
- Worker 正常启动并显示 "ready"
- 任务提交后能在 Worker 中看到执行日志

---

#### 任务 2: NER 结果列表 API

**目标**: 为 RE 页面提供 NER 结果列表

**文件**: `backend/app/api/v1/ner.py`

**新增接口**:
```python
@router.get("/ner/list", summary="获取 NER 结果列表")
async def get_ner_list(
    result_id: Optional[str] = None,
    status: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """获取用户的 NER 结果列表"""
    # 实现列表查询
```

**前端修改**: `frontend/src/views/REProcessor.vue`
- 调用 nerApi.getNerList() 获取列表
- 替换当前的 el-empty 组件

---

#### 任务 3: 用户信息更新 API

**目标**: Settings 页面能保存用户信息

**文件**: `backend/app/api/v1/user.py`

**完善接口**:
```python
@router.put("/users/me", summary="更新当前用户信息")
async def update_current_user(
    user_data: UserUpdateRequest,
    db = Depends(get_db),
    user = Depends(get_current_user_required)
):
    """更新用户邮箱、姓名等"""
    # TODO 需实现
```

---

#### 任务 4: Prompt 模板管理 API

**目标**: Settings 页面能管理 Prompt 模板

**文件**: `backend/app/api/v1/config.py`

**完善接口**:
- `GET /config/prompts` - 获取 Prompt 列表 (TODO)
- `GET /config/prompts/{name}` - 获取 Prompt 内容 (TODO)
- `POST /config/prompts` - 创建 Prompt (TODO)
- `PUT /config/prompts/{name}` - 更新 Prompt (TODO)

---

### 2.2 中优先级任务

#### 任务 5: 修改密码功能

**文件**:
- 后端: `backend/app/api/v1/user.py` 新增接口
- 前端: `frontend/src/views/Settings.vue` 添加表单

---

#### 任务 6: 服务状态实时检测

**目标**: Settings 页面显示真实的服务状态

**文件**: `backend/app/api/v1/config.py`

**新增接口**:
```python
@router.get("/config/services-status", summary="获取服务状态")
async def get_services_status():
    """检测 MySQL、Milvus、Redis、GROBID、LLM 连接状态"""
```

---

#### 任务 7: LangGraph 工作流 (可选)

**目标**: 实现 HITL 交互式提取

**文件**: `backend/app/api/v1/extraction.py`

**完善**:
- 启动 LangGraph 工作流 (TODO)
- 获取检查点逻辑 (TODO)
- 审核检查点逻辑 (TODO)

---

## 三、执行顺序

### 第一天
1. ✅ Redis 部署 (已完成)
2. ✅ .env 配置更新 (已完成)
3. 启动 Celery Worker
4. 测试批量任务提交

### 第二天
5. 实现 NER 结果列表 API
6. 修复 RE 页面 NER 列表获取

### 第三天
7. 实现用户信息更新 API
8. 实现修改密码功能

### 第四天
9. 实现 Prompt 模板管理 API
10. 实现服务状态检测 API

### 第五天
11. LangGraph 工作流 (可选)
12. 全流程测试

---

## 四、启动脚本

创建便捷启动脚本：

**文件**: `scripts/start_celery.bat`

```batch
@echo off
echo 启动 Celery Worker...
cd /d data\00. 研究课题\Article_Analysis_System_v3\backend
celery -A backend.app.tasks worker -l info -P solo -Q pdf,ner,re,batch,default
pause
```

**文件**: `scripts/start_all.bat`

```batch
@echo off
echo 启动后端服务...
start cmd /k "cd /d data\00. 研究课题\Article_Analysis_System_v3\backend && python main.py"
timeout /t 3 >nul

echo 启动 Celery Worker...
start cmd /k "cd /d data\00. 研究课题\Article_Analysis_System_v3\backend && celery -A backend.app.tasks worker -l info -P solo"
timeout /t 3 >nul

echo 启动前端服务...
start cmd /k "cd /d data\00. 研究课题\Article_Analysis_System_v3\frontend && npm run dev"

echo 所有服务已启动
pause
```

---

## 五、检查标准

| 检查项 | 验证方法 |
|--------|----------|
| Celery Worker 运行 | Worker 控制台显示 "ready" |
| 批量任务执行 | 提交任务后进度更新 |
| NER 结果列表 | RE 页面显示 NER 列表 |
| 用户信息保存 | Settings 页面保存成功 |
| Prompt 管理 | Prompt 列表显示并可编辑 |
| 服务状态检测 | Settings 显示真实连接状态 |

---

## 六、当前服务配置汇总

| 服务 | 地址 | 密码/密钥 | 状态 |
|------|------|----------|------|
| MySQL | localhost:3306 | Djx3861599! | ✅ |
| Milvus | localhost:19530 | - | ✅ |
| Redis | localhost:6379 | Djx3861599! | ✅ |
| GROBID | localhost:8070 | - | ✅ |
| LLM API | dashscope.aliyuncs.com | <DASHSCOPE_API_KEY> | ✅ |

---

*Step8 完成后进入 Step9: 部署上线*