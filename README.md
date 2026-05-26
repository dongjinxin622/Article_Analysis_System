# SciPDF — AI 科学论文分析系统 v3

> 基于 FastAPI + Vue 3 + Celery + LangGraph 的全流程学术论文智能分析平台

## 系统概述

SciPDF 是一个面向科研人员的 AI 论文分析系统，支持从 PDF 论文中自动提取结构化知识，覆盖 **PDF 解析 → 命名实体识别 (NER) → 关系抽取 (RE) → 综合分析 → 报告生成** 的完整流水线。

系统采用插件式领域分析器架构，当前已实现 **超导材料 (REBCO)** 领域的深度分析，包含技术路线、实验方案、临界电流密度 (Jc) 指标等专业维度。

## 核心功能

| 功能模块 | 说明 |
|----------|------|
| **PDF 解析** | 基于 SciPDF-Parser / GROBID 提取论文结构化内容（标题、摘要、章节、参考文献等） |
| **命名实体识别 (NER)** | 基于 Stanza + LLM 识别论文中的专业实体（材料、方法、参数等） |
| **关系抽取 (RE)** | 基于 LLM 提取实体间的语义关系 |
| **批量处理** | 支持多篇 PDF 批量上传与并行处理，实时进度追踪 |
| **Excel 批量提取** | 从 Excel 表格中提取结构化数据并进行分析 |
| **领域分析** | 插件式领域分析器，支持 REBCO 超导材料的 Jc 搜索、对比、技术路线分析 |
| **向量检索** | 基于 Milvus 的论文/实体/句子向量语义搜索 |
| **综合分析** | 一键式综合分析任务，含 HITL (Human-in-the-Loop) 审核中断机制 |
| **用户管理** | JWT 双令牌认证 (Access + Refresh)，支持注册、登录、角色权限 |
| **Prompt 管理** | 在线管理 LLM Prompt 模板，支持用户私有 + 系统共享 |
| **系统监控** | 实时服务状态检测（PostgreSQL / Redis / Milvus / GROBID） |

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                        前端 (Vue 3)                          │
│   Vue 3.4 + Element Plus 2.5 + Pinia + Vue Router + Vite   │
└───────────────────────────┬─────────────────────────────────┘
                            │ Nginx 反向代理 (HTTP/HTTPS)
┌───────────────────────────┴─────────────────────────────────┐
│                     后端 (FastAPI)                           │
│   FastAPI + SQLAlchemy 2.0 (asyncpg) + Uvicorn              │
│   ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐ │
│   │ PDF 解析  │ │ NER 服务  │ │  RE 服务   │ │  领域分析器   │ │
│   └──────────┘ └──────────┘ └───────────┘ └──────────────┘ │
│   ┌──────────┐ ┌──────────┐ ┌───────────┐ ┌──────────────┐ │
│   │ LLM 服务  │ │ 向量服务  │ │ 报告生成   │ │ Prompt 管理  │ │
│   └──────────┘ └──────────┘ └───────────┘ └──────────────┘ │
└──┬────────────┬───────────┬────────────┬───────────────────┘
   │            │           │            │
┌──┴──┐  ┌─────┴──┐  ┌─────┴──┐  ┌─────┴──────┐
│Redis│  │Postgres│  │ Milvus │  │   GROBID   │
│ 7.x │  │  16.x  │  │ Stand. │  │  0.8.x     │
└─────┘  └────────┘  └────────┘  └────────────┘
   │
┌──┴──────────────────────────────┐
│     Celery Worker + Beat        │
│  6 个队列 · 4 并发 · 定时调度    │
└─────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端框架 | Vue 3 + TypeScript | 3.4 / 5.3 |
| UI 组件库 | Element Plus | 2.5 |
| 状态管理 | Pinia | 2.1 |
| 构建工具 | Vite | 5.x |
| 后端框架 | FastAPI | ≥ 0.100 |
| ORM | SQLAlchemy (asyncpg) | 2.0 |
| 异步任务 | Celery + Beat | 5.3 |
| 数据库 | PostgreSQL | 16 |
| 缓存/消息 | Redis | 7.x |
| 向量数据库 | Milvus | Standalone |
| PDF 解析 | SciPDF-Parser + GROBID | 0.8.x |
| NLP | Stanza + Transformers | 1.12.0 / 4.x |
| LLM | OpenAI 兼容 API（通义千问） | - |
| 工作流 | LangGraph + LangChain-OpenAI | ≥ 0.2 |
| 认证 | JWT (Access + Refresh Token) | python-jose |
| 容器化 | Docker Compose | - |

## 项目结构

```
Article_Analysis_System_v3/
├── backend/                    # 后端应用
│   ├── app/
│   │   ├── api/
│   │   │   ├── deps.py         # 依赖注入
│   │   │   └── v1/             # API v1 路由
│   │   │       ├── pdf.py          # PDF 处理
│   │   │       ├── ner.py          # 命名实体识别
│   │   │       ├── re.py           # 关系抽取
│   │   │       ├── batch.py        # 批量处理
│   │   │       ├── domain.py       # 领域分析
│   │   │       ├── extraction.py   # 批量提取
│   │   │       ├── excel_extraction.py  # Excel 提取
│   │   │       ├── jc.py           # Jc 数据库搜索
│   │   │       ├── comprehensive.py # 综合分析
│   │   │       ├── user.py         # 用户认证
│   │   │       ├── config.py       # 配置与 Prompt 管理
│   │   │       └── task.py         # 任务管理
│   │   ├── core/               # 核心配置
│   │   │   ├── config.py           # Pydantic Settings
│   │   │   └── redis_client.py     # Redis 客户端
│   │   ├── domain/             # 领域分析器（插件式）
│   │   │   ├── base.py             # 抽象基类
│   │   │   ├── registry.py         # 注册中心
│   │   │   └── material/           # 超导材料领域
│   │   │       ├── analyzer.py         # REBCO 分析器
│   │   │       ├── tech_route.py       # 技术路线分析
│   │   │       ├── exp_scheme.py       # 实验方案分析
│   │   │       └── jc_index.py         # Jc 指标分析
│   │   ├── models/             # SQLAlchemy ORM 模型
│   │   ├── schemas/            # Pydantic Schema
│   │   ├── services/           # 业务服务层
│   │   │   ├── pdf_service.py      # PDF 解析
│   │   │   ├── ner_service.py      # NER 服务
│   │   │   ├── re_service.py       # RE 服务
│   │   │   ├── llm_service.py      # LLM 调用
│   │   │   ├── embedding_service.py # 向量化
│   │   │   ├── milvus_service.py   # Milvus 操作
│   │   │   ├── comprehensive_service.py # 综合分析
│   │   │   ├── report_service.py   # 报告生成
│   │   │   ├── task_manager.py     # 任务状态管理
│   │   │   ├── user_service.py     # 用户服务
│   │   │   └── prompt_service.py   # Prompt 模板管理
│   │   ├── tasks/              # Celery 异步任务
│   │   │   ├── pdf_tasks.py        # PDF 解析任务
│   │   │   ├── ner_tasks.py        # NER 任务
│   │   │   ├── re_tasks.py         # RE 任务
│   │   │   ├── batch_tasks.py      # 批量处理任务
│   │   │   └── scheduled_tasks.py  # 定时调度任务
│   │   ├── workflows/          # LangGraph 工作流
│   │   └── utils/              # 工具函数
│   ├── Dockerfile
│   ├── requirements.txt
│   └── tests/
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── api/                # API 调用封装
│   │   ├── views/              # 页面视图
│   │   ├── components/         # 通用组件
│   │   ├── stores/             # Pinia 状态管理
│   │   ├── router/             # 路由配置
│   │   ├── composables/        # Vue Composable
│   │   └── types/              # TypeScript 类型
│   ├── Dockerfile
│   └── package.json
├── nginx/                      # Nginx 配置
│   └── entrypoint.sh           # HTTP/HTTPS 动态切换脚本
├── prompts/                    # LLM Prompt 模板文件
├── scipdf/                     # SciPDF 解析器 + Prompt 查询模板
│   ├── ner_queries/            # NER Prompt 模板
│   ├── re_queries/             # RE Prompt 模板
│   └── domain_queries/         # 领域分析 Prompt 模板
├── stanza_resources_v112/      # Stanza v1.12.0 NLP 模型（不提交 git）
├── scripts/                    # 项目级脚本
├── docker-compose.yml          # 容器编排
├── nginx.conf                  # Nginx 主配置
├── .env                        # 环境变量
└── ddl_postgresql.sql          # 数据库 DDL
```

## 页面路由

| 路径 | 页面 | 说明 | 需认证 |
|------|------|------|--------|
| `/login` | 登录页 | 用户登录 / 注册 | 否 |
| `/` | 首页 | 系统概览与快捷入口 | 是 |
| `/pdf` | PDF 解析 | 单篇论文 PDF 解析 | 是 |
| `/ner` | NER 处理 | 命名实体识别与结果查看 | 是 |
| `/re` | RE 处理 | 关系抽取与结果查看 | 是 |
| `/pdf-batch` | 批量提取 | 多篇 PDF 批量上传与处理 | 是 |
| `/excel-batch` | Excel 提取 | Excel 表格数据提取分析 | 是 |
| `/domain` | 领域分析 | REBCO 超导材料深度分析 | 是 |
| `/settings` | 系统设置 | 系统信息、Prompt 管理、用户设置 | 是 |
| `/logs` | 日志查看 | 系统日志与任务日志 | 是 |

## API 模块

| 模块 | 前缀 | 说明 |
|------|------|------|
| PDF 处理 | `/api/v1/papers` | 论文 PDF 上传与解析 |
| NER 处理 | `/api/v1/ner` | 命名实体识别（含批量） |
| 关系抽取 | `/api/v1/re` | 实体关系抽取 |
| 批量处理 | `/api/v1/batch` | 多文件批量任务管理 |
| 批量提取 | `/api/v1/extraction` | 批量提取与检查点 |
| Excel 提取 | `/api/v1/excel-extraction` | Excel 表格提取任务 |
| 领域分析 | `/api/v1/domains` | 领域配置与分析 |
| Jc 数据库 | `/api/v1/jc` | 超导材料 Jc 数据搜索 |
| 综合分析 | `/api/v1/comprehensive` | 综合分析任务与报告 |
| 任务管理 | `/api/v1/tasks` | 任务状态查询与取消 |
| 用户认证 | `/api/v1/users` | 注册、登录、令牌刷新 |
| 配置管理 | `/api/v1/config` | 系统配置、Prompt 模板、服务状态 |
| WebSocket | `/ws` | 实时任务进度推送 |

## 部署

### 环境要求

| 组件 | 最低版本 | 说明 |
|------|----------|------|
| Docker | 20.x | 容器运行时 |
| Docker Compose | v2 | 容器编排 |
| PostgreSQL | 16 | 主数据库 |
| Redis | 7.x | 缓存 + Celery Broker |
| Milvus | 2.3+ | 向量数据库（Standalone 模式） |
| GROBID | 0.8.x | 论文 PDF 结构化解析 |

### Docker Compose 部署

**1. 准备环境变量**

```bash
cp .env.example .env
# 编辑 .env 配置数据库、Redis、Milvus、LLM 等连接信息
```

**2. 启动服务**

```bash
docker compose up -d
```

启动 3 个应用容器：

| 容器 | 端口 | 说明 |
|------|------|------|
| `scipdf-frontend` | 80 / 443 | Nginx 反向代理（自动切换 HTTP/HTTPS） |
| `scipdf-backend` | 8000 | FastAPI 后端 API |
| `scipdf-celery-worker` | — | Celery Worker + Beat 定时调度 |

**3. 验证部署**

```bash
# 健康检查
curl http://localhost:8000/health

# 容器状态
docker ps --filter "name=scipdf"
```

**4. SSL 证书（可选）**

```bash
docker compose run --rm certbot certonly --webroot -w /var/www/certbot -d yourdomain.com
```

### 运维注意事项

**容器重启后登录异常**

容器重启后如出现登录失败（"用户名或密码错误"），通常是 Redis 中残留的旧 Token 缓存导致。清空 Token 缓存即可恢复：

```python
# 在 backend 容器内执行
import asyncio
from backend.app.core.security import hash_password
from backend.app.models.base import AsyncSessionLocal
from backend.app.core.redis_client import get_redis
from sqlalchemy import text

async def fix():
    async with AsyncSessionLocal() as s:
        h = hash_password('admin123')
        await s.execute(text("UPDATE users SET password_hash = :h WHERE username = 'admin'"), {'h': h})
        await s.commit()
    r = await get_redis()
    keys = await r.keys('token:*')
    if keys: await r.delete(*keys)
    print(f'done, cleared {len(keys)} tokens')

asyncio.run(fix())
```

**Stanza 模型**

Stanza v1.12.0 NLP 模型（~324 MB）已预置在 `stanza_resources_v112/` 目录，Docker 构建时自动复制到容器内。首次 NER 处理无需额外下载。

## 云端部署验证（2026-05-26）

### 基础设施

| 服务 | 状态 | 地址 |
|------|------|------|
| PostgreSQL 16 | ✅ 已连接 | 8.147.69.101:5432 |
| Redis 7 | ✅ 已连接 | 8.147.69.101:6379 |
| Milvus Standalone | ✅ 已连接 | 8.147.69.101:19530 |
| GROBID | ✅ 已连接 | http://8.147.69.101:8070 |

### API 功能验证（15/15 通过）

| 功能 | 端点 | 状态 |
|------|------|------|
| 用户登录 | `POST /users/login` | ✅ |
| 用户信息 | `GET /users/me` | ✅ |
| 系统配置 | `GET /config/system` | ✅ |
| 服务状态 | `GET /config/status` | ✅ |
| Prompt 模板 | `GET /config/prompts` | ✅ |
| 论文列表 | `GET /papers` | ✅ (34 篇) |
| NER 结果 | `GET /ner/list` | ✅ (28 条) |
| 领域列表 | `GET /domains` | ✅ (rebco) |
| 任务列表 | `GET /tasks` | ✅ |
| Jc 统计 | `GET /jc/stats` | ✅ |
| 综合分析 | `GET /comprehensive/active` | ✅ |
| Excel 提取 | `GET /excel-extraction/tasks` | ✅ |
| 批量任务 | `GET /batch` | ✅ |
| 任务统计 | `GET /tasks/statistics` | ✅ |
| 健康检查 | `GET /health` | ✅ |

### NER 端到端测试

| 步骤 | 结果 |
|------|------|
| PDF 上传 (203 KB) | ✅ 解析成功，`result_id: 10.2478_v10177-011-0030-y` |
| NER 处理 | ✅ 33.7 秒，提取 135 个实体，29 个分组 |
| 实体类型分布 | Material (52), Microstructural_Hierarchy (43), Transport_Behavior (34), Manufacturing_Process (4) |
| 示例提取 | `YBa2Cu3O7−x`, `Tm = 90 K`, `Film_Thickness = 1 μm`, `Tc_onset = 90 K` |
| LLM API | ✅ 通义千问 (qwen3.6-plus) |
| Embedding API | ✅ text-embedding-v4, dim=1024 |

### 核心依赖版本

| 组件 | 版本 | 状态 |
|------|------|------|
| Stanza | 1.12.0 | ✅ Pipeline 初始化 6.3s |
| PyMuPDF | 1.27.2 | ✅ |
| SciPDF-Parser | latest | ✅ |
| Transformers | 4.x | ✅ (Stanza depparse 依赖) |
| beautifulsoup4 | 4.14 | ✅ (SciPDF-Parser 依赖) |

### 本地开发

**后端**

```bash
cd backend
pip install -r requirements.txt
# CPU-only PyTorch（无 GPU 时推荐）
pip install torch --index-url https://download.pytorch.org/whl/cpu

uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

**前端**

```bash
cd frontend
npm install
npm run dev
```

**Celery Worker**

```bash
celery -A backend.app.tasks worker -B --loglevel=info --concurrency=4 \
    -Q default,pdf,ner,re,batch,scheduled
```

## 环境变量

| 类别 | 关键配置项 | 说明 |
|------|-----------|------|
| 应用基础 | `APP_NAME`, `DEBUG`, `PORT`, `CORS_ORIGINS` | 应用名称、调试模式、端口、跨域 |
| PostgreSQL | `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DATABASE` | 数据库连接 |
| Redis | `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `REDIS_DB` | 缓存与消息队列 |
| Milvus | `MILVUS_HOST`, `MILVUS_PORT`, `EMBEDDING_DIM` | 向量数据库 |
| GROBID | `GROBID_URL` | PDF 解析服务地址 |
| LLM | `API_KEY`, `BASE_URL`, `MODEL_NAME`, `EMBEDDING_MODEL` | 大模型调用配置 |
| JWT 认证 | `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_MINUTES` | 令牌配置 |
| 管理员 | `DEFAULT_ADMIN_USERNAME`, `DEFAULT_ADMIN_PASSWORD` | 首次启动自动创建 |

## Celery 任务队列

| 队列 | 用途 |
|------|------|
| `default` | 默认任务 |
| `pdf` | PDF 解析任务 |
| `ner` | 命名实体识别 |
| `re` | 关系抽取 |
| `batch` | 批量处理 |
| `scheduled` | 定时调度任务 |

### 定时任务 (Beat)

| 任务 | 频率 | 说明 |
|------|------|------|
| `cleanup_expired_tasks` | 每日 | 清理过期任务 |
| `cleanup_failed_logs` | 每日 | 清理失败日志 |
| `cleanup_old_results` | 每日 | 清理过期结果文件 |
| `cleanup_temp_files` | 每日 | 清理临时文件 |
| `generate_statistics` | 每小时 | 生成系统统计 |
| `health_check` | 每 30 分钟 | 服务健康检查 |

## 领域分析器

系统采用**插件式注册中心**架构，通过 `DomainRegistry` 动态注册领域分析器：

```python
# backend/app/domain/registry.py
class DomainRegistry:
    @classmethod
    def register(cls, name: str, analyzer: DomainAnalyzerBase): ...

# backend/app/domain/base.py — 抽象基类
class DomainAnalyzerBase(ABC):
    def get_entity_types(self) -> List[str]: ...
    def get_relation_types(self) -> List[str]: ...
    def get_prompt_template(self) -> str: ...
    def build_profile(self, entities, relations) -> dict: ...
    def analyze(self, paper_data) -> dict: ...
```

当前已注册领域：**REBCO 超导材料**（含技术路线、实验方案、Jc 指标分析）

## 许可证

本项目仅供学术研究使用。
