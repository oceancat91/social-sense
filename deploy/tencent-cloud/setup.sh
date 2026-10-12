#!/usr/bin/env bash
# Social Sense - 腾讯云 Ubuntu 一键部署脚本
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info() {
    echo -e "${YELLOW}$1${NC}"
}

success() {
    echo -e "${GREEN}$1${NC}"
}

success "========================================="
success "  Social Sense 腾讯云部署"
success "========================================="

# 1. Docker
if ! command -v docker >/dev/null 2>&1; then
    info "[1/5] 安装 Docker..."
    curl -fsSL https://get.docker.com | bash
    systemctl enable --now docker
else
    success "[1/5] Docker 已安装"
fi

if ! docker compose version >/dev/null 2>&1; then
    info "安装 Docker Compose 插件..."
    apt-get update -qq
    apt-get install -y -qq docker-compose-plugin
else
    success "Docker Compose 已安装"
fi

# 2. 项目代码
if [ ! -d "social-sense/.git" ]; then
    info "[2/5] 克隆项目..."
    git clone https://github.com/oceancat91/social-sense.git
else
    success "[2/5] 使用现有 social-sense 目录"
fi
cd social-sense

# 3. 运行配置
info "[3/5] 生成运行配置..."
mkdir -p config
if [ ! -f "config/.env" ] && [ -f ".env" ]; then
    mv .env config/.env
fi
if [ ! -f "config/.env" ]; then
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || openssl rand -hex 16)
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    cat > config/.env <<ENVEOF
DB_PASSWORD=${DB_PASS}
APP_SECRET_KEY=${SECRET_KEY}
ADMIN_EMAIL=admin@social-sense.com
ADMIN_PASSWORD=admin123
LLM_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_TIMEOUT=30
LLM_MAX_WORKERS=8
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
ENVEOF
    success "配置文件 config/.env 已生成"
else
    success "配置文件 config/.env 已存在，跳过"
fi

# 从仓库根目录执行，固定配置和环境文件位置。
compose() {
    docker compose --env-file config/.env -f deploy/docker-compose.yml "$@"
}

# 4. 构建和启动
info "[4/5] 构建镜像并启动服务（约 3-5 分钟）..."
compose up -d --build
success "服务已启动"

# 5. 等待后端就绪后灌入演示数据
info "[5/5] 等待后端就绪..."
BACKEND_READY=0
for _ in $(seq 1 30); do
    if compose exec -T backend python -c \
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/health', timeout=2)" \
        >/dev/null 2>&1; then
        BACKEND_READY=1
        break
    fi
    sleep 2
done
if [ "$BACKEND_READY" -ne 1 ]; then
    echo "后端未在 60 秒内就绪，请运行 docker compose --env-file config/.env -f deploy/docker-compose.yml logs backend 排查。" >&2
    exit 1
fi
info "灌入演示数据..."
compose exec -T backend python scripts/seed_demo.py

SERVER_IP=$(curl -fsS ifconfig.me 2>/dev/null || curl -fsS ip.sb 2>/dev/null || echo "你的服务器IP")
echo ""
success "========================================="
success "  部署完成"
success "========================================="
echo ""
echo -e "  访问地址:  ${YELLOW}http://${SERVER_IP}/app/${NC}"
echo -e "  登录邮箱:  ${YELLOW}admin@social-sense.com${NC}"
echo -e "  登录密码:  ${YELLOW}admin123${NC}"
echo ""
echo "  数据库密码已保存在 config/.env 文件中"
echo "  建议首次登录后修改管理员密码"
echo ""
echo "  常用运维命令:"
echo "    docker compose --env-file config/.env -f deploy/docker-compose.yml ps"
echo "    docker compose --env-file config/.env -f deploy/docker-compose.yml logs -f backend"
echo "    docker compose --env-file config/.env -f deploy/docker-compose.yml restart"
