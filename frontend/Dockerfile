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

# 复制 nginx 配置（移除默认 default.conf 避免冲突）
RUN rm -f /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/nginx.conf

# 复制入口脚本（动态 HTTP/HTTPS 切换）
COPY nginx/entrypoint.sh /docker-entrypoint.d/entrypoint.sh
RUN chmod +x /docker-entrypoint.d/entrypoint.sh

# 创建 certbot 验证目录
RUN mkdir -p /var/www/certbot

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:80/ || exit 1

# 使用入口脚本启动（根据证书自动切换 HTTP/HTTPS）
CMD ["/docker-entrypoint.d/entrypoint.sh"]