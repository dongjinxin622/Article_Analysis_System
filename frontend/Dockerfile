# Article Analysis System v3 - Frontend Dockerfile
FROM node:18-alpine as builder

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY frontend/package.json frontend/package-lock.json* ./

# 安装依赖
RUN npm install

# 复制源代码
COPY frontend/ .

# 构建
RUN npm run build

# 生产阶段 - 使用 nginx
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 复制 nginx 配置
COPY nginx.conf /etc/nginx/nginx.conf

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1

# 启动 nginx
CMD ["nginx", "-g", "daemon off;"]