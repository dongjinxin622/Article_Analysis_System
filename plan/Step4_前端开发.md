# Step4: 前端开发 - 详细计划

> 预计周期: 3 周 | 状态: 待开始 | 前置依赖: Step3

---

## 一、任务清单

### 4.1 Vue 3 项目初始化

**目标**：创建 Vue 3 + TypeScript + Vite 项目

**命令**：
```bash
cd frontend
npm create vite@latest . -- --template vue-ts
npm install
```

**依赖安装**：
```bash
npm install vue-router pinia axios element-plus socket.io-client echarts md-editor-v3 vue-pdf-embed
npm install -D typescript @vitejs/plugin-vue
```

---

### 4.2 Element Plus UI 集成

**目标**：集成 Element Plus 组件库

**文件**：`frontend/src/main.ts`

**配置**：
```typescript
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import App from './App.vue'

const app = createApp(App)
app.use(ElementPlus)
app.mount('#app')
```

---

### 4.3 Pinia 状态管理

**目标**：创建 Pinia stores

**文件**：`frontend/src/stores/*.ts`

**Stores 设计**：

| Store | 文件 | 功能 |
|-------|------|------|
| userStore | `user.ts` | 用户状态、登录状态 |
| paperStore | `paper.ts` | 论文数据状态 |
| taskStore | `task.ts` | 任务状态、进度 |
| domainStore | `domain.ts` | 领域配置状态 |
| notificationStore | `notification.ts` | 通知消息 |

---

### 4.4 API 请求模块

**目标**：创建 Axios API 请求模块

**文件**：`frontend/src/api/*.ts`

**API 模块**：

| 文件 | 功能 |
|------|------|
| `request.ts` | Axios 配置、拦截器 |
| `pdf.ts` | PDF 相关 API |
| `ner.ts` | NER 相关 API |
| `re.ts` | RE 相关 API |
| `batch.ts` | 批量处理 API |
| `domain.ts` | 领域分析 API |
| `vector.ts` | 向量检索 API |
| `user.ts` | 用户认证 API |

**request.ts 结构**：
```typescript
import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

// 请求拦截器：添加 JWT Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// 响应拦截器：处理错误
api.interceptors.response.use(
  response => response.data,
  error => Promise.reject(error)
)

export default api
```

---

### 4.5 核心页面开发

**目标**：开发核心功能页面

**文件**：`frontend/src/views/*.vue`

**页面列表**：

| 页面 | 文件 | 功能 |
|------|------|------|
| 首页 | `Home.vue` | 系统介绍、快速入口 |
| PDF 处理 | `PDFProcessor.vue` | PDF 上传、解析、结果展示 |
| NER 处理 | `NERProcessor.vue` | NER 执行、实体列表、Excel下载 |
| RE 处理 | `REProcessor.vue` | RE 执行、关系图谱 |
| 批量提取 | `BatchExtraction.vue` | LangGraph 工作流、HITL |
| 领域分析 | `DomainAnalysis.vue` | 技术路线、实验方案、Jc 指标分析 |
| 论文对比 | `PaperCompare.vue` | 相似论文检索、对比分析 |
| 系统设置 | `Settings.vue` | Prompt 管理、领域配置 |
| 登录页 | `Login.vue` | 用户登录 |
| 用户中心 | `UserCenter.vue` | 用户信息、历史记录 |

---

### 4.6 公共组件开发

**目标**：开发可复用公共组件

**文件**：`frontend/src/components/*.vue`

**组件列表**：

| 组件 | 文件 | 功能 |
|------|------|------|
| 文件上传 | `FileUpload.vue` | PDF 文件上传组件 |
| 结果列表 | `ResultList.vue` | 结果列表展示 |
| 实体展示 | `EntityView.vue` | NER 实体展示表格 |
| 关系图谱 | `RelationGraph.vue` | ECharts 关系图谱 |
| 进度监控 | `ProgressMonitor.vue` | 任务进度组件 |
| Prompt 编辑器 | `PromptEditor.vue` | Markdown 编辑器 |
| PDF 预览 | `PDFPreview.vue` | PDF 文件预览 |
| 报告展示 | `ReportView.vue` | 分析报告展示 |

---

### 4.7 WebSocket 进度推送

**目标**：实现 WebSocket 实时进度推送

**文件**：`frontend/src/utils/websocket.ts`

**功能**：
- 连接 WebSocket 服务
- 监听任务进度事件
- 更新 taskStore 状态
- 断线重连机制

---

### 4.8 前端路由配置

**目标**：配置 Vue Router

**文件**：`frontend/src/router/index.ts`

**路由设计**：

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | Home | 首页 |
| `/pdf` | PDFProcessor | PDF 处理 |
| `/ner` | NERProcessor | NER 处理 |
| `/re` | REProcessor | RE 处理 |
| `/batch` | BatchExtraction | 批量提取 |
| `/domain` | DomainAnalysis | 领域分析 |
| `/compare` | PaperCompare | 论文对比 |
| `/settings` | Settings | 系统设置 |
| `/login` | Login | 登录页 |
| `/user` | UserCenter | 用户中心 |

---

### 4.9 TypeScript 类型定义

**目标**：创建 TypeScript 类型定义

**文件**：`frontend/src/types/*.ts`

**类型定义**：

| 文件 | 类型 |
|------|------|
| `paper.ts` | Paper, ProcessingResult, Section |
| `entity.ts` | Entity, EntityType |
| `relation.ts` | Relation, RelationType |
| `task.ts` | BatchTask, TaskProgress |
| `user.ts` | User, Token |
| `domain.ts` | DomainConfig |

---

### 4.10 Vite 配置

**目标**：配置 Vite 构建工具

**文件**：`frontend/vite.config.ts`

**配置项**：
- API 代理（proxy）
- Element Plus 自动导入
- TypeScript 配置

---

## 二、执行顺序

1. 初始化 Vue 3 项目
2. 安装依赖
3. 配置 Element Plus
4. 创建 Axios 请求模块
5. 创建 Pinia stores
6. 创建公共组件
7. 创建核心页面
8. 配置路由
9. 创建 TypeScript 类型
10. 配置 WebSocket
11. 配置 Vite
12. 测试前端功能

---

## 三、检查标准

| 检查项 | 标准 |
|--------|------|
| 项目启动 | `npm run dev` 正常启动 |
| 页面访问 | 所有路由页面可访问 |
| Element Plus | UI 组件正常渲染 |
| API 调用 | 后端 API 正常响应 |
| 状态管理 | Pinia stores 正常工作 |
| WebSocket | 进度推送正常接收 |
| PDF 上传 | 文件上传成功 |
| NER 执行 | NER 处理流程完整 |
| 批量提取 | LangGraph 工作流正常 |

---

## 四、参考文件列表

| 来源 | 参考内容 |
|------|---------|
| 架构设计文档前端目录结构 | 目录结构设计 |
| 架构设计文档技术栈 | Vue 3 + Element Plus + Pinia |
| v2 无前端 | 需全新开发 |

---

*Step4 完成后进入 Step5: 领域扩展重构*