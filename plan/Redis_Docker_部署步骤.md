# Redis Docker 部署步骤

> 目标：在云端服务器部署 Redis 服务，用于 Celery Broker 和任务状态存储

---

## 一、部署步骤

### 1.1 拉取 Redis 镜像

```bash
docker pull redis:7-alpine
```

### 1.2 创建配置文件

```bash
# 创建配置目录
mkdir -p /opt/redis/conf

# 创建配置文件
cat > /opt/redis/conf/redis.conf << 'EOF'
# Redis 配置文件

# 绑定地址（允许外部访问）
bind 0.0.0.0

# 端口
port 6379

# 密码认证（重要！请修改密码）
requirepass Djx3861599!

# 最大内存
maxmemory 512mb
maxmemory-policy allkeys-lru

# 持久化配置
appendonly yes
appendfsync everysec

# 日志级别
loglevel notice

# 超时设置
timeout 300
EOF
```

### 1.3 启动 Redis 容器

```bash
docker run -d \
  --name redis-server \
  --restart always \
  -p 6379:6379 \
  -v /opt/redis/conf:/etc/redis \
  -v /opt/redis/data:/data \
  redis:7-alpine \
  redis-server /etc/redis/redis.conf
```

### 1.4 验证 Redis 运行状态

```bash
# 查看容器状态
docker ps | grep redis

# 测试连接
docker exec -it redis-server redis-cli ping

# 测试密码认证
docker exec -it redis-server redis-cli -a YourRedisPassword123 ping
```

---

## 二、防火墙配置

### 2.1 开放端口

```bash
# CentOS/RHEL
firewall-cmd --permanent --add-port=6379/tcp
firewall-cmd --reload

# Ubuntu
ufw allow 6379/tcp

# 云服务商安全组
# 在云控制台添加入站规则：
# - 端口：6379
# - 协议：TCP
# - 来源：你的开发环境IP或0.0.0.0/0（需谨慎）
```

---

## 三、连接信息

部署完成后，请提供以下信息：

| 项目 | 值 |
|------|---|
| **Redis 地址** | `你的服务器IP` |
| **Redis 端口** | `6379` |
| **Redis 密码** | `你设置的密码` |

---

## 四、可选：Docker Compose 方式

```yaml
# /opt/redis/docker-compose.yml
version: '3.8'
services:
  redis:
    image: redis:7-alpine
    container_name: redis-server
    restart: always
    ports:
      - "6379:6379"
    volumes:
      - ./conf:/etc/redis
      - ./data:/data
    command: redis-server /etc/redis/redis.conf
```

启动：
```bash
cd /opt/redis
docker-compose up -d
```

---

## 五、安全建议

1. **必须设置密码**：生产环境务必配置 `requirepass`
2. **限制访问IP**：安全组只允许必要的IP访问
3. **数据持久化**：配置 `appendonly` 防止数据丢失
4. **监控内存**：设置 `maxmemory` 防止内存溢出

---

**完成后请告诉我：**
- Redis 服务器地址（如：8.147.69.101）
- Redis 端口（默认：6379）
- Redis 密码

我将据此生成完整的功能完善计划。