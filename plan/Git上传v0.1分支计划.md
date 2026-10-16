# Git 上传至 v0.1 分支 — 完整执行计划

**生成时间**: 2026-05-23
**目标仓库**: https://github.com/dongjinxin622/Article_Analysis_System.git
**目标分支**: v0.1
**当前状态**: 项目尚未初始化 Git，无 .gitignore 文件

---

## 一、排除清单（不上传的内容）

### 1.1 敏感信息（绝对禁止上传）
| 文件/目录 | 原因 |
|-----------|------|
| `.env` | 包含数据库密码 `Djx3861599!`、云端服务器 IP 等真实凭证 |

### 1.2 大型二进制/模型文件（体积过大，不适合 Git 管理）
| 文件/目录 | 大小 | 说明 |
|-----------|------|------|
| `stanza_resources/` | 326 MB | NLP 模型资源，通过 pip 安装后自动下载 |
| `scipdf/` | 33 MB | 第三方解析库（含 __pycache__），应通过 requirements.txt 安装 |
| `frontend/node_modules/` | 149 MB | npm 依赖，通过 `npm install` 恢复 |

### 1.3 运行时生成数据（非源码）
| 文件/目录 | 说明 |
|-----------|------|
| `data/*.pkl` | 大型 pickle 数据文件（共约 34 MB） |
| `data/uploads/` | 用户上传的 PDF 文件 |
| `data/results/` | 处理结果缓存 |
| `data/ner_results/` | NER 处理结果 |
| `data/re_results/` | RE 处理结果 |
| `data/failed_logs/` | 失败日志 |
| `outputs/` | 批量导出结果（.pkl + .xlsx） |
| `results/` | 批量任务结果（.pkl） |
| `batch_results/` | 批量处理中间结果 |
| `excel_section_test_sample/` | Excel 测试样本（400 KB） |

### 1.4 日志文件
| 文件/目录 | 说明 |
|-----------|------|
| `logs/` | 应用日志目录（~9 MB） |
| `backend.log` | 后端运行日志（44 KB） |
| `frontend/frontend.log` | 前端运行日志 |

### 1.5 构建产物与 IDE 配置
| 文件/目录 | 说明 |
|-----------|------|
| `frontend/dist/` | 前端构建产物（2 MB） |
| `.idea/` | JetBrains IDE 配置 |
| `__pycache__/` | Python 字节码缓存（所有子目录） |
| `*.pyc` | 编译后的 Python 文件 |

### 1.6 大型 PDF 样本（非必要）
| 文件/目录 | 大小 | 说明 |
|-----------|------|------|
| `sample/` | 5.3 MB | 测试用 PDF 样本文件 |
| `*.pdf` (根目录) | ~1.4 MB | 两篇参考论文 PDF |

---

## 二、上传清单（需要上传的内容）

### 2.1 源代码
- `backend/app/` — 后端 FastAPI 应用（所有 Python 源码）
- `backend/alembic/` — 数据库迁移脚本
- `backend/tests/` — 后端测试
- `backend/scripts/` — 后端脚本
- `backend/requirements.txt` — Python 依赖
- `backend/Dockerfile` — 后端容器镜像
- `backend/*.py` — 后端根目录工具脚本
- `frontend/src/` — 前端 Vue/React 源码
- `frontend/public/` — 前端静态资源
- `frontend/index.html` — 前端入口
- `frontend/package.json` — npm 依赖声明
- `frontend/package-lock.json` — npm 依赖锁定
- `frontend/tsconfig.json` — TypeScript 配置
- `frontend/tsconfig.node.json` — TypeScript Node 配置
- `frontend/vite.config.ts` — Vite 构建配置
- `frontend/Dockerfile` — 前端容器镜像

### 2.2 配置与构建文件
- `.env.example` — 环境变量模板（已脱敏）
- `docker-compose.yml` — Docker 编排
- `nginx.conf` — Nginx 反向代理配置
- `requirements.txt` — 根目录 Python 依赖（如有）

### 2.3 脚本文件
- `scripts/` — 各类运维脚本
- `*.bat` — 启动/停止批处理脚本
- `*.py` (根目录) — 测试与分析脚本

### 2.4 文档与设计
- `docs/` — 设计文档
- `plan/` — 各阶段计划文档
- `prompts/` — LLM 提示词模板
- `query/` — 查询相关文件
- `blog/` — 博客相关文件
- `CLAUDE.md` — 项目开发准则
- `openapi.json` — API 规范文档
- `*.md` (根目录) — 项目文档

### 2.5 CI/CD 与部署
- `docker-compose.yml`
- 各 `Dockerfile`
- `nginx.conf`

---

## 三、.gitignore 文件设计

将创建以下 `.gitignore`，覆盖所有排除项：

```gitignore
# ===== 敏感信息 =====
.env

# ===== Python =====
__pycache__/
*.py[cod]
*.pyo
*.egg-info/
dist/
build/
*.egg

# ===== 大型模型与第三方库 =====
stanza_resources/
scipdf/

# ===== Node.js =====
node_modules/
frontend/dist/

# ===== 运行时数据 =====
data/
outputs/
results/
batch_results/
logs/
*.log
backend.log

# ===== 上传文件 =====
excel_section_test_sample/
sample/

# ===== PDF 文件 =====
*.pdf

# ===== IDE 配置 =====
.idea/
.vscode/
*.swp
*.swo

# ===== 操作系统 =====
.DS_Store
Thumbs.db
desktop.ini

# ===== 临时文件 =====
*.tmp
*.bak
*.pkl

# ===== 任务结果 =====
task_result.json
```

---

## 四、完整执行流程

### 步骤 1：创建 .gitignore 文件
在项目根目录创建 `.gitignore`，内容如上。

### 步骤 2：初始化 Git 仓库
```bash
cd data\00. 研究课题\Article_Analysis_System_v3
git init
```

### 步骤 3：创建并切换到 v0.1 分支
```bash
git checkout -b v0.1
```

### 步骤 4：添加文件到暂存区
```bash
git add .
```
（此时 .gitignore 会自动过滤排除项）

### 步骤 5：验证暂存区内容
```bash
git status
```
确认无误：不应包含 .env / node_modules / __pycache__ / *.pkl / *.pdf / stanza_resources / scipdf / logs / data / outputs / results / batch_results 等。

### 步骤 6：创建首次提交
```bash
git commit -m "初始化项目 v0.1：论文分析系统核心源码

包含后端 FastAPI 应用、前端界面、Docker 部署配置、数据库迁移脚本、LLM 提示词模板、项目文档与计划。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

### 步骤 7：添加远程仓库
```bash
git remote add origin https://github.com/dongjinxin622/Article_Analysis_System.git
```

### 步骤 8：推送到远程 v0.1 分支
```bash
git push -u origin v0.1
```

### 步骤 9：最终验证
```bash
git log --oneline -1
git branch -a
```
确认提交成功，v0.1 分支已推送至 GitHub。

---

## 五、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| `.env` 意外上传 | 🔴 高 | .gitignore 首行即排除，步骤5人工确认 |
| 大型文件误上传 | 🟡 中 | .gitignore 覆盖 *.pkl/*.pdf/stanza_resources 等模式 |
| GitHub 认证失败 | 🟡 中 | 确认已配置 GitHub 凭据或 SSH key |
| 远程仓库已存在内容 | 🟢 低 | 使用独立 v0.1 分支，不与 main 冲突 |

---

## 六、预估文件体积

| 类别 | 排前大小 | 排后大小（预估） |
|------|----------|-------------------|
| stanza_resources | 326 MB | 0 |
| node_modules | 149 MB | 0 |
| scipdf | 33 MB | 0 |
| data/*.pkl | 34 MB | 0 |
| logs | 9 MB | 0 |
| PDF 文件 | 6.7 MB | 0 |
| 源码与配置 | ~2 MB | ~2 MB |
| **合计** | **~560 MB** | **~2 MB** |

推送体积从约 560 MB 压缩至约 2 MB，完全适合 GitHub 管理。

---

## 七、审核确认清单

请逐项确认后回复"同意执行"：

- [ ] `.gitignore` 排除清单是否完整？有无遗漏或需要调整的目录？
- [ ] `stanza_resources/` 和 `scipdf/` 是否确实可通过 pip 恢复？（确认 requirements.txt 中有对应依赖）
- [ ] `data/` 目录完全排除是否可接受？（其中所有 .pkl 均为运行时产物）
- [ ] `sample/` 和根目录 PDF 是否排除？（测试用样本）
- [ ] `plan/` 和 `docs/` 目录是否全部上传？
- [ ] 提交信息内容是否合适？
- [ ] 目标分支名 `v0.1` 是否确认？
