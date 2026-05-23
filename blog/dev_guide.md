# SciPDF AI论文处理系统 v3 - 开发指南

## 快速启动

### Windows 启动脚本

双击运行以下脚本即可启动全部服务：

| 脚本 | 功能 |
|------|------|
| `start.bat` | 启动前后端服务 |
| `stop.bat` | 停止前后端服务 |

### 手动启动

```bash
# 启动后端 (在 backend 目录)
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# 启动前端 (在 frontend 目录)
npm run dev
```

---

## 服务地址

| 服务 | 地址 | 说明 |
|------|------|------|
| **前端界面** | http://localhost:3000 | Vue 3 + Element Plus |
| **后端 API** | http://127.0.0.1:8001 | FastAPI |
| **API 文档** | http://127.0.0.1:8001/docs | Swagger UI |
| **ReDoc** | http://127.0.0.1:8001/redoc | ReDoc 文档 |

---

## 测试账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |

---

## 目录结构

```
Article_Analysis_System_v3/
├── backend/                # 后端代码
│   ├── app/
│   │   ├── api/           # API 路由
│   │   ├── core/          # 核心配置
│   │   ├── models/        # 数据模型
│   │   ├── services/      # 业务服务
│   │   ├── schemas/       # Pydantic Schema
│   │   └── domain/        # 领域分析模块
│   │   └── main.py        # 应用入口
│   └── requirements.txt
├── frontend/              # 前端代码
│   ├── src/
│   │   ├── views/         # 页面组件
│   │   ├── api/           # API 调用
│   │   ├── stores/        # Pinia 状态管理
│   │   ├── router/        # 路由配置
│   │   └── types/         # TypeScript 类型
│   └── package.json
├── data/                  # 数据目录
│   ├── uploads/           # 上传文件
│   ├── results/           # 处理结果
│   ├── ner_results/       # NER 结果
│   └── re_results/        # 关系抽取结果
├── logs/                  # 日志目录
│   └── app.log            # 应用日志
├── scripts/               # 工具脚本
├── blog/                  # 文档/报告
├── .env                   # 环境变量配置
├── start.bat              # 启动脚本
├── stop.bat               # 停止脚本
└── docker-compose.yml     # Docker 部署配置
```

---

## 环境配置 (.env)

### 必需配置

```env
# MySQL 数据库
MYSQL_HOST=8.147.69.101
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DATABASE=article_analysis_v3

# Milvus 向量数据库
MILVUS_HOST=8.147.69.101
MILVUS_PORT=19530
EMBEDDING_DIM=1024

# LLM 配置 (通义千问)
API_KEY=your_api_key
BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
MODEL_NAME=qwen3.5-plus

# JWT 密钥
SECRET_KEY=your_secret_key
```

---

## 常用 API 端点

### 用户认证
- `POST /api/v1/users/register` - 用户注册
- `POST /api/v1/users/login` - 用户登录
- `GET /api/v1/users/me` - 获取当前用户

### PDF 处理
- `POST /api/v1/papers` - 上传论文
- `GET /api/v1/papers` - 论文列表
- `GET /api/v1/papers/{id}` - 论文详情

### NER 处理
- `POST /api/v1/ner` - 执行 NER
- `GET /api/v1/ner/{id}` - NER 结果

### 关系抽取
- `POST /api/v1/re` - 执行关系抽取
- `GET /api/v1/re/{id}` - 关系抽取结果

### 向量搜索
- `POST /api/v1/search` - 向量搜索
- `POST /api/v1/similar` - 相似论文

### 领域分析
- `GET /api/v1/domains` - 领域列表
- `POST /api/v1/domains/{domain}/techroute` - 技术路线分析
- `POST /api/v1/domains/{domain}/expscheme` - 实验方案分析

---

## 日志查看

日志文件位置: `logs/app.log`

```bash
# 查看实时日志 (PowerShell)
Get-Content logs\app.log -Wait

# 查看最后 50 行
tail -n 50 logs/app.log
```

---

## 数据库连接

### MySQL (云端)
- 地址: 8.147.69.101:3306
- 数据库: article_analysis_v3
- 已迁移数据: tech_routes (1949条), exp_schemes (1950条)

### Milvus (云端)
- 地址: 8.147.69.101:19530
- Collections: paper_embeddings, entity_embeddings, sentence_embeddings

---

## 开发建议

1. **后端开发**: 使用 FastAPI 自动文档测试 API
2. **前端开发**: 确保后端已启动，前端会自动代理 API 请求
3. **数据库操作**: 使用 SQLAlchemy ORM，避免直接 SQL
4. **日志调试**: 查看 logs/app.log 了解运行状态

---

## 故障排除

### 后端启动失败
1. 检查 .env 配置是否正确
2. 检查 MySQL/Milvus 连接是否可用
3. 查看 logs/app.log 错误信息

### 前端无法连接后端
1. 确认后端在 8001 端口运行
2. 检查 vite.config.ts 代理配置
3. 检查 CORS 配置

### 登录失败
1. 确认用户已注册
2. 检查密码是否正确 (admin123)
3. 查看 logs/app.log 确认具体错误