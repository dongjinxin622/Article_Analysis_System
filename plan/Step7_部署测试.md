# Step7: 部署测试 - 详细计划

> 预计周期: 1 周 | 状态: 待开始 | 前置依赖: Step6

---

## 一、任务清单

### 7.1 Docker 容器化

**目标**：创建 Docker 镜像和 Docker Compose 配置

**文件**：
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `docker-compose.yml`

**参考来源**：架构设计文档 Docker 配置

**docker-compose.yml 结构**：
```yaml
version: '3.8'

services:
  # MySQL
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_PASSWORD}
      MYSQL_DATABASE: scipdf
    volumes:
      - mysql_data:/var/lib/mysql
    ports:
      - "3306:3306"

  # Milvus Standalone
  milvus:
    image: milvusdb/milvus:v2.3.3
    command: ["milvus", "run", "standalone"]
    volumes:
      - milvus_data:/var/lib/milvus
    ports:
      - "19530:19530"

  # Redis
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  # FastAPI
  api:
    build: ./backend
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: mysql+aiomysql://...
      MILVUS_HOST: milvus
      REDIS_URL: redis://redis:6379
    depends_on:
      - mysql
      - milvus
      - redis

  # Celery Worker
  worker:
    build: ./backend
    command: celery -A app.tasks worker -l info
    depends_on:
      - redis

  # Celery Beat
  beat:
    build: ./backend
    command: celery -A app.tasks beat -l info
    depends_on:
      - redis

  # Nginx
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - api

volumes:
  mysql_data:
  milvus_data:
```

---

### 7.2 Nginx 反向代理配置

**目标**：配置 Nginx 反向代理

**文件**：`nginx.conf`

**配置内容**：
```nginx
server {
    listen 80;

    # 前端静态资源
    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    # API 转发
    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
    }

    # WebSocket 转发
    location /ws/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

### 7.3 健康检查接口

**目标**：完善健康检查接口

**文件**：`backend/app/main.py`

**接口设计**：
```python
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "database": await check_database(),
        "milvus": await check_milvus(),
        "redis": await check_redis(),
        "llm": await check_llm_api()
    }

async def check_milvus() -> dict:
    try:
        from pymilvus import MilvusClient
        client = MilvusClient(uri=settings.MILVUS_URI)
        collections = client.list_collections()
        return {"status": "connected", "collections": len(collections)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
```

---

### 7.4 日志系统配置

**目标**：配置结构化日志系统

**文件**：`backend/app/utils/logger.py`

**配置内容**：
```python
from loguru import logger

logger.add(
    "logs/app_{time}.log",
    rotation="1 day",
    retention="7 days",
    level="INFO",
    format="{time} {level} {message}"
)
```

---

### 7.5 单元测试编写

**目标**：编写核心功能单元测试

**文件**：`backend/tests/*.py`

**测试列表**：

| 文件 | 测试内容 |
|------|---------|
| `test_api/test_pdf.py` | PDF API 测试 |
| `test_api/test_ner.py` | NER API 测试 |
| `test_api/test_re.py` | RE API 测试 |
| `test_api/test_domain.py` | 领域 API 测试 |
| `test_services/test_pdf_service.py` | PDF 服务测试 |
| `test_services/test_vector_service.py` | 向量服务测试 |

---

### 7.6 数据库迁移脚本

**目标**：创建 Alembic 数据库迁移

**文件**：`backend/alembic/`

**初始化命令**：
```bash
alembic init alembic
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

---

### 7.7 环境变量配置模板

**目标**：创建环境变量配置模板

**文件**：`.env.example`

**配置模板**：
```
# 应用配置
APP_NAME=SciPDF AI论文处理系统
DEBUG=true

# MySQL
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=
MYSQL_DATABASE=scipdf

# Milvus
MILVUS_HOST=localhost
MILVUS_PORT=19530

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# GROBID
GROBID_URL=http://localhost:8070

# LLM
API_KEY=
BASE_URL=
EMBEDDING_DIM=768

# JWT
SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

---

### 7.8 API 文档完善

**目标**：完善 FastAPI 自动文档

**改动文件**：`backend/app/main.py`

**配置**：
```python
app = FastAPI(
    title="SciPDF AI论文处理系统 API",
    description="学术论文 AI 处理系统 RESTful API",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)
```

---

## 二、执行顺序

1. 创建 backend/Dockerfile
2. 创建 frontend/Dockerfile
3. 创建 docker-compose.yml
4. 创建 nginx.conf
5. 完善健康检查接口
6. 配置日志系统
7. 创建 .env.example
8. 初始化 Alembic
9. 编写单元测试
10. 完善 API 文档
11. 运行 Docker Compose 测试
12. 完整流程测试

---

## 三、检查标准

| 检查项 | 标准 |
|--------|------|
| Docker 构建 | 所有镜像构建成功 |
| Docker 启动 | 所有容器正常启动 |
| 健康检查 | `/health` 返回所有服务 healthy |
| API 文档 | `/docs` 正常显示完整 API |
| 前端访问 | Nginx 正常代理前端 |
| WebSocket | WebSocket 连接正常 |
| 完整流程 | PDF上传→NER→RE→领域分析 流程完整 |

---

## 四、参考文件列表

| 来源 | v3 目标位置 |
|------|------------|
| 架构设计文档 docker-compose.yml | `docker-compose.yml` |
| 架构设计文档 Milvus 部署 | Milvus 配置 |
| 架构设计文档健康检查 | 健康检查接口 |

---

*Step7 完成后项目进入生产部署阶段*