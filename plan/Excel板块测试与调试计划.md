# Excel 板块测试与调试计划

> 创建时间: 2026-04-22
> 目标: 完整测试 Excel 批量提取功能，修复 WebSocket 连接问题，确保端到端流程正常工作

---

## 1. 问题现状

### 1.1 当前核心问题
- **WebSocket 连接状态显示异常**: 前端显示"未连接"，但实际 WebSocket 已建立连接
- **状态同步问题**: composable 返回的 `isConnected.value` 无法正确传递到 Vue 组件

### 1.2 模块结构概览

```
Excel 批量提取功能模块
├── 前端 (frontend/src)
│   ├── views/ExcelBatchExtraction.vue     # 主页面组件
│   ├── components/ExcelExtractionTab.vue  # Tab 组件
│   ├── api/excel_extraction.ts            # API 接口
│   ├── types/excel_extraction.ts          # TypeScript 类型
│   └── composables/useExcelExtractionWs.ts # WebSocket 管理
│
├── 后端 (backend/app)
│   ├── api/v1/excel_extraction.py         # API 路由 + WebSocket 端点
│   ├── models/excel_extraction.py         # 数据库模型
│   ├── schemas/excel_extraction.py        # Pydantic Schema
│   └── excel_extraction/
│       ├── agent.py                       # WebAgentRunner 工作流执行器
│       ├── state.py                       # AgentState 状态定义
│       ├── nodes.py                       # 工作流节点
│       ├── llm_hitl_nodes.py              # HITL 智能对话节点
│       ├── conversation.py                # 对话管理
│       └── models.py                      # LLM 模型配置
│
└── 测试数据 (excel_section_test_sample/)
    ├── savedrecs (1).xls                  # Excel 输入文件
    └── 3.2.5 短脉冲高峰值功率半导体激光技术检索策略 20260331.docx  # 策略文档
```

---

## 2. 测试与调试阶段

### Phase 1: WebSocket 连接修复 (最高优先级)

**问题诊断**:
- WebSocket 连接成功后状态无法正确同步到 Vue 组件
- 可能原因: 单例模式实现问题、ref 响应式丢失、闭包问题

**调试步骤**:

| 步骤 | 操作 | 验证方式 |
|-----|------|---------|
| 1.1 | 检查 composable 单例实现 | console.log 输出 wsInstance 对象 |
| 1.2 | 验证 isConnected ref 响应性 | 添加详细日志跟踪 ref 变化 |
| 1.3 | 检查 Vue 组件读取方式 | 对比 ws.value.isConnected 和直接访问 |
| 1.4 | 测试浏览器直接连接后端 | curl 测试 WebSocket 端点 |
| 1.5 | 检查 Vite WebSocket 代理配置 | 查看 vite.config.ts proxy 设置 |

**关键代码位置**:
- `frontend/src/composables/useExcelExtractionWs.ts:18-30` (单例创建)
- `frontend/src/composables/useExcelExtractionWs.ts:88-100` (连接处理)
- `frontend/src/views/ExcelBatchExtraction.vue:354-400` (恢复任务)

---

### Phase 2: API 接口测试

**测试用例**:

| 序号 | 接口 | 方法 | 测试内容 | 预期结果 |
|-----|------|-----|---------|---------|
| 2.1 | `/api/v1/excel-extraction/upload` | POST | 上传 Excel + 策略文档 | 返回 session_id, preview 数据 |
| 2.2 | `/api/v1/excel-extraction/tasks` | POST | 创建任务 | 返回 task_id |
| 2.3 | `/api/v1/excel-extraction/tasks` | GET | 获取任务列表 | 返回历史任务数组 |
| 2.4 | `/api/v1/excel-extraction/tasks/{id}` | GET | 获取任务详情 | 返回完整任务信息 |
| 2.5 | `/api/v1/ws/excel-extraction/{session_id}` | WS | WebSocket 连接 | 返回 101 Switching Protocols |

**测试脚本** (可使用 curl 或 Postman):
```bash
# 2.1 上传文件测试
curl -X POST http://localhost:8000/api/v1/excel-extraction/upload \
  -F "excel_files=@excel_section_test_sample/savedrecs (1).xls" \
  -F "strategy_file=@excel_section_test_sample/策略文档.docx"

# 2.3 获取任务列表
curl http://localhost:8000/api/v1/excel-extraction/tasks?page=1&page_size=10

# 2.5 WebSocket 连接测试
curl -v -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Sec-WebSocket-Version: 13" \
  http://localhost:8000/api/v1/ws/excel-extraction/test_session_id
```

---

### Phase 3: 后端 Agent 工作流测试

**测试目标**: 确保 WebAgentRunner 可以正常执行完整工作流

**工作流节点顺序**:
```
START → integrate → field_check → data_quality → filter →
parse_strategy → generate_prompt → prompt_check → prepare_eval →
batch_eval → result_check → export_result → END

(包含 HITL 分支: llm_hitl, data_lookup, modify_config 等)
```

**关键节点测试**:

| 节点 | 功能 | 测试内容 |
|-----|------|---------|
| integrate | 读取 Excel 数据 | 验证 DOI 解析、行数统计 |
| field_check | 字段完整性检查 | 验证缺失字段检测 |
| data_quality | 数据质量检查 | 验证质量评分逻辑 |
| filter | 过滤无效数据 | 验证筛选逻辑 |
| parse_strategy | 解析策略文档 | 验证 docx 解析 |
| generate_prompt | 生成提取 Prompt | 验证 LLM 调用 |
| batch_eval | 批量评估 | 验证并行处理 |
| export_result | 导出结果 | 验证 Excel 输出 |

**测试方法**:
1. 后端单元测试: 创建 `test_excel_extraction.py`
2. 手动触发工作流: 通过 WebSocket 发送 start 消息
3. 观察后端日志: 查看 Agent 执行过程

---

### Phase 4: 前端端到端测试

**测试流程**:

```
步骤 1: 上传文件
├── 选择 Excel 文件 (savedrecs (1).xls)
├── 选择策略文档 (可选)
├── 点击"上传并预览"
└── 验证: 显示文件预览、列名、行数

步骤 2: 配置任务
├── 设置任务名称
├── 选择 LLM 模型
├── 设置并发数、质量阈值
├── 选择提取字段
└── 点击"创建任务"

步骤 3: 智能处理
├── WebSocket 连接状态: 显示"已连接"
├── 进度条实时更新
├── 日志窗口显示执行过程
├── HITL 对话交互 (如有问题)
└── 验证: 状态同步、进度更新

步骤 4: 下载结果
├── 显示完成状态
├── 统计信息: 成功/失败数
├── 点击下载 Excel 结果
└── 验证: 输出文件格式正确
```

**验证点**:
- [ ] 文件上传成功率 100%
- [ ] WebSocket 连接成功率 100%
- [ ] 进度更新延迟 < 500ms
- [ ] 日志显示完整
- [ ] 结果下载正确

---

### Phase 5: 问题修复清单

**已知问题**:

| 问题ID | 描述 | 优先级 | 状态 |
|-------|------|-------|------|
| P1-001 | WebSocket 连接状态显示异常 | P0 | 待修复 |
| P1-002 | ws.value.isConnected.value 返回 undefined | P0 | 待修复 |
| P1-003 | 单例模式可能存在问题 | P0 | 待验证 |
| P2-001 | 后端任务状态未更新 (processing 停留) | P1 | 待排查 |
| P2-002 | Agent 执行可能未完成 | P1 | 待排查 |

---

## 3. 执行计划

### 3.1 Phase 1 执行步骤 (WebSocket 修复)

```
Step 1: 创建独立测试页面
├── 创建 test_ws.html 简单 WebSocket 测试
├── 直接连接后端验证连接状态
└── 确认问题在 Vue 层还是 WebSocket 层

Step 2: 深入调试 composable
├── 添加详细状态跟踪日志
├── 检查 ref 对象是否被正确导出
├── 测试单例模式是否正确工作

Step 3: 检查 Vue 组件响应性
├── 验证 ws.value 是否响应式
├── 检查 setInterval 中的状态读取
├── 测试直接绑定 vs 间接读取

Step 4: 修复并验证
├── 根据调试结果修复代码
├── 清理历史任务 (processing 状态)
├── 完整端到端测试验证
```

### 3.2 Phase 2-4 并行执行

在 WebSocket 修复后，并行执行:
- API 接口自动化测试
- 后端 Agent 单元测试
- 前端 E2E 测试

---

## 4. 测试环境

### 4.1 服务启动
```bash
# 后端
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd frontend
npm run dev  # 或 pnpm dev
```

### 4.2 数据库检查
```sql
-- 查看任务表状态
SELECT task_id, status, progress, created_at FROM excel_extraction_tasks;

-- 清理异常状态任务
UPDATE excel_extraction_tasks SET status = 'cancelled'
WHERE status = 'processing' AND created_at < NOW() - INTERVAL 1 HOUR;
```

---

## 5. 验收标准

| 检查项 | 标准 | 测试方法 |
|-------|------|---------|
| WebSocket 连接 | 显示"已连接"状态 | 前端 UI 验证 |
| 进度同步 | 实时更新进度条 | 观察执行过程 |
| 日志显示 | 完整执行日志 | 检查日志窗口 |
| 结果导出 | Excel 文件下载成功 | 文件验证 |
| HITL 对话 | 对话交互正常 | 手动测试 |

---

## 6. 附录

### 6.1 相关文件清单
- 前端: `frontend/src/views/ExcelBatchExtraction.vue`
- 前端: `frontend/src/composables/useExcelExtractionWs.ts`
- 后端: `backend/app/api/v1/excel_extraction.py`
- 后端: `backend/app/excel_extraction/agent.py`

### 6.2 测试数据
- Excel: `excel_section_test_sample/savedrecs (1).xls`
- 策略: `excel_section_test_sample/3.2.5 短脉冲高峰值功率半导体激光技术检索策略 20260331.docx`

---

**审核要点**:
1. Phase 1 WebSocket 修复步骤是否合理?
2. 是否需要添加更多测试用例?
3. 验收标准是否完整?

请审核后批准执行。