#!/bin/bash
# ============================================================
# Social Sense - 鑵捐浜戜竴閿儴缃茶剼鏈?
# 閫傜敤锛歎buntu 22.04 / CentOS 7+ 杞婚噺搴旂敤鏈嶅姟鍣?
# ============================================================
set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  Social Sense 鑵捐浜戦儴缃茶剼鏈?{NC}"
echo -e "${GREEN}=========================================${NC}"

# ---- 1. Docker ----
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}[1/5] 瀹夎 Docker...${NC}"
    curl -fsSL https://get.docker.com | bash
    systemctl enable docker && systemctl start docker
else
    echo -e "${GREEN}[1/5] Docker 宸插畨瑁?{NC}"
fi

if ! docker compose version &> /dev/null; then
    echo -e "${YELLOW}瀹夎 Docker Compose 鎻掍欢...${NC}"
    apt-get update -qq && apt-get install -y -qq docker-compose-plugin
else
    echo -e "${GREEN}Docker Compose 宸插畨瑁?{NC}"
fi

# ---- 2. 鍏嬮殕椤圭洰 ----
if [ ! -d "social-sense" ]; then
    echo -e "${YELLOW}[2/5] 鍏嬮殕椤圭洰...${NC}"
    git clone https://github.com/oceancat91/social-sense.git
fi
cd social-sense

# ---- 3. 閰嶇疆 ----
echo -e "${YELLOW}[3/5] 鐢熸垚閰嶇疆鏂囦欢...${NC}"
if [ ! -f ".env" ]; then
    DB_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))" 2>/dev/null || openssl rand -hex 16)
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
    cat > .env <<ENVEOF
DB_PASSWORD=${DB_PASS}
APP_SECRET_KEY=${SECRET_KEY}
ADMIN_EMAIL=admin@social-sense.com
ADMIN_PASSWORD=admin123
ENVEOF
    echo -e "${GREEN}閰嶇疆鏂囦欢 .env 宸茬敓鎴?{NC}"
else
    echo -e "${GREEN}閰嶇疆鏂囦欢 .env 宸插瓨鍦紝璺宠繃${NC}"
fi

# ---- 4. 鏋勫缓 & 鍚姩 ----
echo -e "${YELLOW}[4/5] 鏋勫缓闀滃儚骞跺惎鍔ㄦ湇鍔★紙绾?3-5 鍒嗛挓锛?..${NC}"
docker compose up -d --build
echo -e "${GREEN}鏈嶅姟宸插惎鍔?{NC}"

# ---- 5. 绉嶅瓙鏁版嵁 ----
echo -e "${YELLOW}[5/5] 绛夊緟 MySQL 灏辩华...${NC}"
sleep 20
echo -e "${YELLOW}鐏屽叆婕旂ず鏁版嵁...${NC}"
docker compose exec -T backend python seed_data.py

# ---- 瀹屾垚 ----
SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s ip.sb 2>/dev/null || echo "浣犵殑鏈嶅姟鍣↖P")
echo ""
echo -e "${GREEN}=========================================${NC}"
echo -e "${GREEN}  閮ㄧ讲瀹屾垚锛?{NC}"
echo -e "${GREEN}=========================================${NC}"
echo ""
echo -e "  璁块棶鍦板潃:  ${YELLOW}http://${SERVER_IP}${NC}"
echo -e "  鐧诲綍閭:  ${YELLOW}admin@social-sense.com${NC}"
echo -e "  鐧诲綍瀵嗙爜:  ${YELLOW}admin123${NC}"
echo ""
echo -e "  鏁版嵁搴撳瘑鐮佸凡淇濆瓨鍦?.env 鏂囦欢涓?
echo -e "  寤鸿鐧诲綍鍚庝慨鏀圭鐞嗗憳瀵嗙爜"
echo ""
echo -e "  甯哥敤杩愮淮鍛戒护:"
echo -e "    docker compose ps              鏌ョ湅鐘舵€?
echo -e "    docker compose logs -f backend 鏌ョ湅鏃ュ織"
echo -e "    docker compose restart         閲嶅惎鏈嶅姟"
