# CLAUDE.md — 项目级补充规则

> 全局通用规则已定义在 `C:\Users\djx\.claude\CLAUDE.md`，本文件仅包含本项目特有的补充规则。两者共同生效，冲突时以本文件为准。

**📁 Plan 文件存放规则（最高优先级）**
- 每次需要建立计划（plan）时，生成的 .md 文件必须统一存放在 `plan/` 文件夹下。
- 禁止将 plan 文件散落在项目根目录或其他目录中。

## 🚀 云端部署规范

**服务器信息**
- 地址：`8.147.69.101`，用户：`root`
- 项目目录：`/opt/scipdf/`
- Git 仓库：`https://github.com/dongjinxin622/Article_Analysis_System.git`（private，分支 `v0.3`）

**标准部署流程（必须遵循）**
```bash
# 1. 本地：修改代码后提交推送
git add . && git commit -m "..." && git push origin v0.3

# 2. 服务器：拉取最新代码并重建
ssh root@8.147.69.101
cd /opt/scipdf && git pull origin v0.3

# 按需重建（只改了什么就重建什么）
docker compose up -d --build frontend          # 改前端时
docker compose up -d --build backend celery-worker  # 改后端时
```

**禁止事项**
- ❌ 禁止直接在服务器上修改代码（服务器只负责运行，不负责开发）
- ❌ 禁止删除 Docker 镜像（`docker rmi`），否则依赖包需全部重新下载
- ❌ 禁止将 `.env`、API Key、数据库密码等敏感信息提交到 Git

**大文件管理**
- `stanza_resources_v112/`（324MB）和 `scipdf/`（33MB）通过 volume 挂载，不打入镜像
- 备份压缩包位于 `/opt/scipdf/stanza_resources_v112.tar.gz`，仅用于灾难恢复
- `.dockerignore` 已排除这些目录，构建上下文约 9KB

**Docker 缓存策略**
- `pip install torch` 和 `pip install -r requirements.txt` 已缓存为独立层
- 只要 `requirements.txt` 不变，构建时跳过下载（显示 `CACHED`）
- 修改 `requirements.txt` 会触发重新下载，但仅下载新增/变更的包
