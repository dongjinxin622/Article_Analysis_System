# Article Analysis System v3 - Backend Dockerfile
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 使用阿里云 Debian 镜像源加速（中国大陆服务器）
RUN sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources 2>/dev/null; \
    sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list 2>/dev/null; \
    true

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpoppler-cpp-dev \
    pkg-config \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 先安装 CPU-only PyTorch（~200 MB，不依赖 requirements.txt，独立缓存层）
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# 复制依赖文件（放在 torch 之后，避免改 requirements 导致 torch 重新下载）
COPY backend/requirements.txt .

# 安装其余 Python 依赖（清华 PyPI 镜像加速，torch 已安装会被跳过）
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 复制应用代码（scipdf/ 和 stanza_resources 通过 volume 挂载，不进镜像）
COPY backend/ ./backend/
COPY scripts/ ./scripts/

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 创建数据目录
RUN mkdir -p /app/data/uploads /app/data/results /app/data/ner_results /app/data/re_results /app/logs

# 健康检查（使用标准库 urllib，无需额外安装 requests）
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# 启动命令
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
