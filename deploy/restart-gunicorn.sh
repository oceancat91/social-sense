#!/bin/bash
# 重启 SocialSense 后端 gunicorn。
#
# 踩过的两个坑，这里都修掉了：
# 1) ssh 里直接 `nohup ... &` 会让 ssh 持有 stdout 而挂住，命令被外层 timeout 杀掉，
#    重启实际没发生（日志里连 pkill 都没跑到）。→ 用 setsid 脱离，调用方用 ( ... & ) 包一层。
# 2) pkill 之后只 sleep 固定秒数就启动，旧进程还没释放端口，新进程报
#    "Address already in use" 直接退出，导致后端 503。→ 改成轮询端口直到真正释放。
set -u

PORT=5000
APP_DIR=/home/ubuntu/social-sense/backend
GUNICORN=/home/ubuntu/.local/bin/gunicorn

echo "[restart] $(date '+%F %T') stopping old gunicorn ..."
pkill -f "gunicorn.*run:app" 2>/dev/null || true

# 先等进程消失，再等端口释放（两者可能不同步）
for i in $(seq 1 20); do
  pgrep -f "gunicorn.*run:app" >/dev/null 2>&1 || break
  sleep 1
done
echo "[restart] processes left: $(pgrep -cf 'gunicorn.*run:app' 2>/dev/null || echo 0)"

for i in $(seq 1 30); do
  if ! ss -lnt 2>/dev/null | grep -q ":${PORT}\b"; then
    echo "[restart] port ${PORT} released after ${i}s"
    break
  fi
  sleep 1
done

if ss -lnt 2>/dev/null | grep -q ":${PORT}\b"; then
  echo "[restart] ERROR: port ${PORT} still busy, aborting to avoid 503"
  ss -lntp 2>/dev/null | grep ":${PORT}" || true
  exit 1
fi

cd "$APP_DIR" || { echo "[restart] app dir missing"; exit 1; }

echo "[restart] starting gunicorn ..."
exec "$GUNICORN" -w 1 -b "127.0.0.1:${PORT}" --timeout 120 run:app
