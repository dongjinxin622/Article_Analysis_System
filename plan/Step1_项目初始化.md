# Step1: 项目初始化 - 详细计划

> 预计周期: 1 周 | 状态: 待开始

---

## 一、任务清单

### 1.1 项目目录结构创建

**目标**：按照架构设计文档创建完整的项目目录结构

**目录结构**：
```
Article_Analysis_System_v3/
├── backend/                        # FastAPI 后端
│   ├── app/
│   │   ├── api/                    # API 路由
│   │   │   ├── v1/                 # API 版本控制
│   │   │   │   ├── pdf.py
│   │   │   │   ├── ner.py
│   │   │   │   ├── re.py
│   │   │   │   ├── batch.py
│   │   │   │   ├── domain.py
│   │   │   │   ├── extraction.py
│   │   │   │   ├── user.py
│   │   │   │   └── config.py
│   │   │   ├── deps.py             # 依赖注入
│   │   │   └── websocket.py        # WebSocket 处理
│   │   ├── core/                   # 核心配置
│   │   │   ├── config.py           # 系统配置
│   │   │   ├── security.py         # 安全认证
│   │   │   ├── exceptions.py       # 异常定义
│   │   │   └── middleware.py       # 中间件
│   │   ├── models/                 # 数据库模型
│   │   │   ├── base.py             # 模型基类
│   │   │   ├── paper.py            # 论文模型
│   │   │   ├── ner.py              # NER 模型
│   │   │   ├── re.py               # RE 模型
│   │   │   ├── batch.py            # 批量任务模型
│   │   │   ├── user.py             # 用户模型
│   │   │   └── domain.py           # 领域配置模型
│   │   ├── schemas/                # Pydantic 模型
│   │   │   ├── paper.py
│   │   │   ├── ner.py
│   │   │   ├── re.py
│   │   │   ├── batch.py
│   │   │   ├── user.py
│   │   │   └── domain.py
│   │   ├── services/               # 业务服务
│   │   │   ├── pdf_service.py
│   │   │   ├── ner_service.py
│   │   │   ├── re_service.py
│   │   │   ├── batch_service.py
│   │   │   ├── extraction_service.py
│   │   │   ├── llm_service.py
│   │   │   ├── embedding_service.py
│   │   │   ├── vector_service.py
│   │   │   ├── storage_service.py
│   │   │   └── cache_service.py
│   │   ├── domain/                 # 领域扩展模块
│   │   │   ├── base.py             # 领域分析器基类
│   │   │   ├── registry.py         # 领域注册中心
│   │   │   ├── material/           # 材料科学领域
│   │   │   │   ├── __init__.py
│   │   │   │   ├── analyzer.py
│   │   │   │   ├── tech_route.py
│   │   │   │   ├── exp_scheme.py
│   │   │   │   └── jc_index.py
│   │   │   └── biomedical/         # 生物医学领域（预留）
│   │   ├── workflows/              # LangGraph 工作流
│   │   │   ├── extraction_wf.py    # 批量提取工作流
│   │   │   └── analysis_wf.py      # 分析工作流
│   │   ├── tasks/                  # Celery 任务
│   │   │   ├── pdf_tasks.py
│   │   │   ├── ner_tasks.py
│   │   │   ├── batch_tasks.py
│   │   │   └── email_tasks.py
│   │   ├── utils/                  # 工具函数
│   │   │   ├── file_utils.py
│   │   │   ├── text_utils.py
│   │   │   ├── prompt_utils.py
│   │   │   └── date_utils.py
│   │   └── main.py                 # 应用入口
│   ├── tests/                      # 测试
│   ├── alembic/                    # 数据库迁移
│   ├── requirements.txt
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/                       # Vue 3 前端
│   ├── src/
│   │   ├── api/                    # API 请求模块
│   │   ├── components/             # 公共组件
│   │   ├── views/                  # 页面视图
│   │   ├── stores/                 # Pinia 状态管理
│   │   ├── utils/                  # 工具函数
│   │   ├── types/                  # TypeScript 类型定义
│   │   ├── router/                 # 路由配置
│   │   ├── App.vue
│   │   └── main.ts
│   ├── public/
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── package.json
├── scipdf/                         # PDF 解析库（从v2复制）
│   ├── pdf/
│   │   ├── parse_pdf.py
│   │   └── __init__.py
│   └── features/
│   │   ├── text_utils.py
│   │   └── __init__.py
├── data/                           # 数据存储
│   ├── uploads/
│   ├── results/
│   ├── ner_results/
│   ├── re_results/
│   └── failed_logs/
├── scripts/                        # 初始化脚本
│   ├── init_db.py
│   └── init_milvus.py
├── docs/                           # 文档
│   ├── v2_analysis/
│   └── architecture/
├── plan/                           # 计划文档
├── docker-compose.yml
├── .env.example
├── requirements.txt
└── README.md
```

**执行命令**：
```bash
mkdir -p backend/app/{api/v1,core,models,schemas,services,domain/material,domain/biomedical,workflows,tasks,utils}
mkdir -p backend/tests backend/alembic/versions
mkdir -p frontend/src/{api,components,views,stores,utils,types,router}
mkdir -p frontend/public
mkdir -p scipdf/{pdf,features}
mkdir -p data/{uploads,results,ner_results,re_results,failed_logs}
mkdir -p scripts
mkdir -p docs docs/v2_analysis docs/architecture
mkdir -p plan
```

---

### 1.2 FastAPI 应用入口

**目标**：创建 FastAPI 应用入口，配置 CORS、路由、生命周期

**文件**：`backend/app/main.py`

**参考来源**：v2 `backend/main.py`

**复制要点**：
- 应用生命周期管理（启动/关闭）
- CORS 中间件配置
- 路由注册机制
- 健康检查接口
- 日志配置

**新增内容**：
- 异步数据库初始化
- Milvus 连接初始化
- Redis 连接初始化

---

### 1.3 Pydantic 配置管理

**目标**：创建配置管理类，支持环境变量和配置文件

**文件**：`backend/app/core/config.py`

**参考来源**：v2 `backend/config.py`

**配置项**：
```python
class Settings(BaseSettings):
    # 应用配置
    APP_NAME: str = "SciPDF AI论文处理系统"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = True

    # API 配置
    API_PREFIX: str = "/api"
    API_V1_PREFIX: str = "/api/v1"

    # 数据库配置（MySQL）
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_DATABASE: str

    # Milvus 配置
    MILVUS_HOST: str
    MILVUS_PORT: int = 19530
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""
    MILVUS_DATABASE: str = "scipdf"

    # Redis 配置
    REDIS_HOST: str
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""

    # GROBID 配置
    GROBID_URL: str = "http://localhost:8070"

    # LLM 配置
    API_KEY: str
    BASE_URL: str
    EMBEDDING_DIM: int = 768

    # 文件配置
    MAX_UPLOAD_SIZE: int = 100 * 1024 * 1024
    ALLOWED_EXTENSIONS: set = {".pdf"}

    # JWT 配置
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
```

---

### 1.4 MySQL 数据库连接

**目标**：配置异步 MySQL 连接

**文件**：`backend/app/models/base.py`

**参考来源**：v2 `backend/models/database.py`

**改动**：
- 使用 `aiomysql` 替代同步驱动
- 异步会话管理
- 异步上下文管理器

**代码结构**：
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(settings.DATABASE_URL_ASYNC)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
```

---

### 1.5 Milvus 连接配置

**目标**：配置 Milvus 向量数据库连接

**文件**：`backend/app/services/vector_service.py`

**Collection 设计**：

**paper_vectors**:
```
字段:
- paper_id (INT64): 主键
- user_id (INT64): 分区键
- vector_type (VARCHAR): 向量类型
- embedding (FLOAT_VECTOR): 768维
- metadata (JSON): 元数据

索引: IVF_FLAT, COSINE
```

**entity_vectors**:
```
字段:
- entity_id (INT64): 主键
- paper_id (INT64): 论文ID
- entity_type (VARCHAR): 实体类型
- entity_name (VARCHAR): 实体名称
- embedding (FLOAT_VECTOR): 768维
- source_sentence (VARCHAR): 来源句子

索引: IVF_FLAT
```

**tech_route_vectors**:
```
字段:
- profile_id (INT64): 主键
- paper_id (INT64): 论文ID
- profile_text (VARCHAR): 技术路线描述
- embedding (FLOAT_VECTOR): 768维
- domain (VARCHAR): 领域标识

索引: HNSW
```

---

### 1.6 Redis 连接配置

**目标**：配置 Redis 连接用于缓存和 Celery Broker

**文件**：`backend/app/services/cache_service.py`

**功能**：
- 任务状态缓存
- 会话缓存
- Celery Broker

---

### 1.7 基础 Schema 定义

**目标**：创建 Pydantic Schema 基础模型

**文件**：`backend/app/schemas/*.py`

**参考来源**：v2 `backend/schemas/schemas.py`

**模型列表**：
| 文件 | Schema |
|------|--------|
| paper.py | ProcessingStatus, PaperResult, SectionInfo |
| ner.py | NERRequest, NERResponse, EntityInfo |
| re.py | RERequest, REResponse, RelationInfo |
| batch.py | BatchTaskRequest, BatchTaskResponse |
| user.py | UserCreate, UserLogin, UserResponse, Token |
| domain.py | DomainConfig, DomainAnalyzerInfo |

---

### 1.8 依赖安装文件

**目标**：创建 requirements.txt 和 package.json

**文件**：
- `backend/requirements.txt`
- `frontend/package.json`

**参考架构设计文档**中的依赖清单。

---

## 二、执行顺序

1. 创建目录结构（命令执行）
2. 复制 v2 `scipdf/` 目录
3. 创建 `backend/app/core/config.py`
4. 创建 `backend/app/main.py`
5. 创建 `backend/app/models/base.py`
6. 创建各 Schema 文件
7. 创建 `requirements.txt`
8. 创建 `.env.example`
9. 测试 FastAPI 启动

---

## 三、检查标准

| 检查项 | 标准 |
|--------|------|
| 目录结构 | 所有目录存在 |
| FastAPI 启动 | `uvicorn app.main:app` 正常启动 |
| 健康检查 | `/health` 返回 `{"status": "healthy"}` |
| API 文档 | `/docs` 正常显示 |
| 数据库连接 | MySQL 连接池正常 |
| Milvus 连接 | Collection 列表可获取 |
| Redis 连接 | ping 命令正常响应 |

---

## 四、参考文件列表

| v2 文件 | v3 目标位置 |
|---------|------------|
| `backend/config.py` | `backend/app/core/config.py` |
| `backend/main.py` | `backend/app/main.py` |
| `backend/models/database.py` | `backend/app/models/base.py` |
| `backend/schemas/schemas.py` | `backend/app/schemas/*.py` |
| `scipdf/pdf/parse_pdf.py` | `scipdf/pdf/parse_pdf.py` |
| `scipdf/features/text_utils.py` | `scipdf/features/text_utils.py` |

---

*Step1 完成后进入 Step2: 核心模块迁移*