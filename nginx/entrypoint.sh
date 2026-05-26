#!/bin/sh
# Nginx 入口脚本 — 根据证书是否存在动态切换 HTTP/HTTPS 配置
set -e

CONF_DIR="/etc/nginx/conf.d"
CERT_DIR="/etc/letsencrypt/live"
HTTP_CONF="$CONF_DIR/http_server.conf"
HTTPS_CONF="$CONF_DIR/https_server.conf"

# 确保 conf.d 目录存在
mkdir -p "$CONF_DIR"

# 检测是否有任何 Let's Encrypt 证书
HAS_CERT=false
if [ -d "$CERT_DIR" ]; then
    for domain_dir in "$CERT_DIR"/*/; do
        if [ -f "${domain_dir}fullchain.pem" ] && [ -f "${domain_dir}privkey.pem" ]; then
            HAS_CERT=true
            DOMAIN=$(basename "$domain_dir")
            break
        fi
    done
fi

if [ "$HAS_CERT" = true ]; then
    echo "[entrypoint] 检测到 SSL 证书: $DOMAIN，启用 HTTPS"

    # ========== HTTP 服务器：仅处理 ACME 验证 + 重定向到 HTTPS ==========
    cat > "$HTTP_CONF" <<EOF
# 自动生成：HTTP → HTTPS 重定向
server {
    listen 80;
    server_name _;

    # Let's Encrypt 验证路径（续期时需要）
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # 其余所有请求重定向到 HTTPS
    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF

    # ========== HTTPS 服务器：完整应用配置 ==========
    cat > "$HTTPS_CONF" <<EOF
# 自动生成：HTTPS 服务器块
server {
    listen 443 ssl http2;
    server_name $DOMAIN;

    ssl_certificate $CERT_DIR/$DOMAIN/fullchain.pem;
    ssl_certificate_key $CERT_DIR/$DOMAIN/privkey.pem;

    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;

    # 前端静态文件
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    # API 代理
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        client_max_body_size 100m;
    }

    # WebSocket 代理
    location /ws {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400s;
    }

    # 健康检查
    location /health {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    # 错误页面
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF
else
    echo "[entrypoint] 未检测到 SSL 证书，仅启用 HTTP"

    # ========== HTTP 服务器：完整应用配置（无 HTTPS） ==========
    cat > "$HTTP_CONF" <<EOF
# 自动生成：HTTP 服务器块（无 SSL 证书）
server {
    listen 80;
    server_name _;

    # Let's Encrypt 验证路径（获取证书时需要）
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # 前端静态文件
    location / {
        root /usr/share/nginx/html;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    # API 代理
    location /api/ {
        limit_req zone=api burst=20 nodelay;
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 60s;
        proxy_send_timeout 300s;
        client_max_body_size 100m;
    }

    # WebSocket 代理
    location /ws {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400s;
    }

    # 健康检查
    location /health {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
    }

    # 错误页面
    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        root /usr/share/nginx/html;
    }
}
EOF

    # HTTPS 服务器：空文件（无证书不启用）
    echo "# 自动生成：无 SSL 证书，不启用 HTTPS" > "$HTTPS_CONF"
fi

echo "[entrypoint] 配置生成完毕，验证语法..."

# 语法检查
if nginx -t 2>&1; then
    echo "[entrypoint] 配置语法正确，启动 nginx..."
    exec nginx -g "daemon off;"
else
    echo "[entrypoint] 错误：nginx 配置语法检查失败"
    exit 1
fi
