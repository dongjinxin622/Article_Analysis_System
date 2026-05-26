#!/bin/bash
# =============================================================================
# SciPDF v3 - 一键部署脚本
# 用法：
#   ./deploy.sh              # 构建并启动所有服务
#   ./deploy.sh ssl-init <域名> <邮箱>  # 首次获取 SSL 证书
#   ./deploy.sh ssl-renew              # 手动续期 SSL 证书
#   ./deploy.sh restart                # 重启所有服务
#   ./deploy.sh logs                   # 查看日志
#   ./deploy.sh status                 # 查看服务状态
# =============================================================================
set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 检查必要工具
check_deps() {
    local missing=0
    for cmd in docker git; do
        if ! command -v $cmd &> /dev/null; then
            echo -e "${RED}[错误] 缺少依赖: $cmd${NC}"
            missing=1
        fi
    done
    if ! docker compose version &> /dev/null; then
        echo -e "${RED}[错误] 缺少 docker compose 插件${NC}"
        missing=1
    fi
    if [ $missing -eq 1 ]; then
        exit 1
    fi
}

# 检查 .env 文件
check_env() {
    if [ ! -f .env ]; then
        echo -e "${YELLOW}[警告] .env 文件不存在，从 .env.prod 复制模板...${NC}"
        if [ -f .env.prod ]; then
            cp .env.prod .env
            echo -e "${YELLOW}[提示] 请编辑 .env 文件填写实际配置后重新运行部署${NC}"
            echo "  nano .env"
            exit 1
        else
            echo -e "${RED}[错误] .env.prod 模板文件不存在${NC}"
            exit 1
        fi
    fi

    # 检查是否还有未填写的占位符
    if grep -q '<填写' .env; then
        echo -e "${YELLOW}[警告] .env 文件中存在未填写的占位符（<填写...>）：${NC}"
        grep '<填写' .env | head -10
        echo ""
        read -p "是否继续部署？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "请先编辑 .env 文件：nano .env"
            exit 1
        fi
    fi
}

# 构建并启动
deploy() {
    check_deps
    check_env

    echo -e "${GREEN}[1/4] 拉取最新代码...${NC}"
    git pull --ff-only 2>/dev/null || echo -e "${YELLOW}[提示] git pull 跳过（非快进或无远程跟踪）${NC}"

    echo -e "${GREEN}[2/4] 构建 Docker 镜像...${NC}"
    docker compose build --no-cache

    echo -e "${GREEN}[3/4] 启动服务...${NC}"
    docker compose up -d

    echo -e "${GREEN}[4/4] 等待服务就绪...${NC}"
    sleep 5

    # 健康检查
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${GREEN}[成功] 后端服务已就绪${NC}"
    else
        echo -e "${YELLOW}[提示] 后端服务尚未就绪，可能仍在启动中${NC}"
    fi

    if curl -sf http://localhost/ > /dev/null 2>&1; then
        echo -e "${GREEN}[成功] 前端服务已就绪${NC}"
    else
        echo -e "${YELLOW}[提示] 前端服务尚未就绪，可能仍在启动中${NC}"
    fi

    echo ""
    echo -e "${GREEN}部署完成！${NC}"
    echo "  HTTP  访问: http://$(hostname -I | awk '{print $1}')"
    echo "  后端 API:   http://$(hostname -I | awk '{print $1}'):8000"
    echo "  查看日志:   ./deploy.sh logs"
    echo ""
    echo -e "${YELLOW}如需启用 HTTPS：${NC}"
    echo "  ./deploy.sh ssl-init yourdomain.com your@email.com"
}

# SSL 证书初始化
ssl_init() {
    local domain="$1"
    local email="$2"

    if [ -z "$domain" ] || [ -z "$email" ]; then
        echo -e "${RED}用法: ./deploy.sh ssl-init <域名> <邮箱>${NC}"
        echo "示例: ./deploy.sh ssl-init scipdf.example.com admin@example.com"
        exit 1
    fi

    check_deps

    echo -e "${GREEN}[1/5] 验证前置条件...${NC}"

    # 检查前端容器是否在运行
    if ! docker compose ps frontend | grep -q "Up"; then
        echo -e "${RED}[错误] 前端容器未运行，请先执行 ./deploy.sh${NC}"
        exit 1
    fi

    # 检查 DNS 解析
    local server_ip
    server_ip=$(hostname -I | awk '{print $1}')
    local dns_ip
    dns_ip=$(dig +short "$domain" 2>/dev/null | head -1 || echo "")

    if [ -n "$dns_ip" ] && [ "$dns_ip" != "$server_ip" ]; then
        echo -e "${YELLOW}[警告] 域名 $domain 解析到 $dns_ip，但本机 IP 是 $server_ip${NC}"
        echo "Let's Encrypt 验证可能失败，请确认 DNS 配置正确"
        read -p "是否继续？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    elif [ -z "$dns_ip" ]; then
        echo -e "${YELLOW}[警告] 无法解析域名 $domain 的 DNS 记录${NC}"
        echo "请确保域名已添加 A 记录指向 $server_ip"
        read -p "是否继续？(y/N) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    echo -e "${GREEN}[2/5] 获取 SSL 证书...${NC}"
    docker compose run --rm certbot \
        certonly --webroot \
        -w /var/www/certbot \
        -d "$domain" \
        --email "$email" \
        --agree-tos \
        --non-interactive \
        --no-eff-email

    echo -e "${GREEN}[3/5] 重启前端容器以加载 HTTPS 配置...${NC}"
    docker compose restart frontend

    sleep 3

    echo -e "${GREEN}[4/5] 验证 HTTPS...${NC}"
    if curl -sf "https://$domain/health" > /dev/null 2>&1; then
        echo -e "${GREEN}[成功] HTTPS 已启用！${NC}"
    elif curl -skf "https://localhost/health" > /dev/null 2>&1; then
        echo -e "${GREEN}[成功] HTTPS 本地验证通过${NC}"
    else
        echo -e "${YELLOW}[提示] HTTPS 验证未通过，可能需要等待几秒后重试${NC}"
        echo "  手动验证: curl -k https://$domain/health"
    fi

    echo -e "${GREEN}[5/5] 设置证书自动续期...${NC}"
    setup_ssl_renewal

    echo ""
    echo -e "${GREEN}HTTPS 配置完成！${NC}"
    echo "  访问: https://$domain"
}

# 设置证书自动续期 cron
setup_ssl_renewal() {
    local cron_cmd="cd $PROJECT_DIR && docker compose run --rm certbot renew --quiet && docker compose exec -T frontend nginx -s reload"
    local cron_line="0 3 * * * $cron_cmd >> /var/log/scipdf-certbot-renew.log 2>&1"

    # 检查是否已存在续期任务
    if crontab -l 2>/dev/null | grep -q "certbot renew"; then
        echo "证书自动续期 cron 任务已存在，跳过"
        return
    fi

    # 添加 cron 任务（每天凌晨 3 点执行）
    (crontab -l 2>/dev/null; echo "$cron_line") | crontab -
    echo "已添加证书自动续期 cron 任务（每天凌晨 3:00）"
}

# 手动续期证书
ssl_renew() {
    check_deps
    echo "正在续期 SSL 证书..."
    docker compose run --rm certbot renew --quiet
    echo "重载 nginx 配置..."
    docker compose exec -T frontend nginx -s reload
    echo -e "${GREEN}证书续期完成${NC}"
}

# 重启服务
restart() {
    echo "重启所有服务..."
    docker compose restart
    echo -e "${GREEN}重启完成${NC}"
}

# 查看日志
logs() {
    docker compose logs -f --tail=100
}

# 查看状态
status() {
    echo "========== 容器状态 =========="
    docker compose ps
    echo ""
    echo "========== 健康检查 =========="
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "后端 API:  ${GREEN}正常${NC}"
    else
        echo -e "后端 API:  ${RED}异常${NC}"
    fi
    if curl -sf http://localhost/ > /dev/null 2>&1; then
        echo -e "前端 Nginx: ${GREEN}正常${NC}"
    else
        echo -e "前端 Nginx: ${RED}异常${NC}"
    fi
    echo ""
    echo "========== 证书状态 =========="
    docker compose run --rm certbot certificates 2>/dev/null || echo "暂无 SSL 证书"
}

# 主入口
case "${1:-deploy}" in
    deploy|"")
        deploy
        ;;
    ssl-init)
        ssl_init "$2" "$3"
        ;;
    ssl-renew)
        ssl_renew
        ;;
    restart)
        restart
        ;;
    logs)
        logs
        ;;
    status)
        status
        ;;
    *)
        echo "用法: $0 {deploy|ssl-init|ssl-renew|restart|logs|status}"
        echo ""
        echo "命令说明："
        echo "  deploy                        构建并启动所有服务（默认）"
        echo "  ssl-init <域名> <邮箱>        首次获取 SSL 证书"
        echo "  ssl-renew                     手动续期 SSL 证书"
        echo "  restart                       重启所有服务"
        echo "  logs                          查看实时日志"
        echo "  status                        查看服务状态"
        exit 1
        ;;
esac
