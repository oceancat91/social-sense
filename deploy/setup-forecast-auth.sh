#!/usr/bin/env bash
# 为热度预测仪表盘生成 HTTP Basic 认证的账号密码文件（默认 /etc/nginx/.htpasswd-forecast）。
#
#   sudo bash deploy/setup-forecast-auth.sh              # 首次生成：随机密码，只打印这一次
#   sudo bash deploy/setup-forecast-auth.sh -u alice     # 指定用户名（默认 forecast）
#   sudo bash deploy/setup-forecast-auth.sh --rotate     # 忘了密码就换一个新的
#   sudo bash deploy/setup-forecast-auth.sh --show-user  # 只显示当前用户名
#
# 密码以哈希存储，无法反查；忘了只能 --rotate。
# 该文件不进版本库（.gitignore 里有 .htpasswd*）。
#
# 配套的 nginx 配置见同目录 nginx-social-sense.conf：
#   location /forecast          -> 需要本文件里的账号密码
#   location /api/v1/forecast/  -> 同上

set -euo pipefail

USER_NAME="forecast"
OUT="/etc/nginx/.htpasswd-forecast"
ROTATE=0
SHOW_ONLY=0

while [ $# -gt 0 ]; do
  case "$1" in
    -u|--user)   USER_NAME="${2:?缺少用户名}"; shift 2 ;;
    -o|--out)    OUT="${2:?缺少输出路径}"; shift 2 ;;
    --rotate)    ROTATE=1; shift ;;
    --show-user) SHOW_ONLY=1; shift ;;
    -h|--help)   sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "未知参数: $1（用 -h 看用法）" >&2; exit 2 ;;
  esac
done

if [ "$SHOW_ONLY" -eq 1 ]; then
  [ -f "$OUT" ] || { echo "$OUT 不存在，还没生成过"; exit 1; }
  echo "文件  : $OUT"
  echo "用户名: $(cut -d: -f1 "$OUT" | paste -sd, -)"
  echo "（密码为哈希存储，无法显示；忘记请用 --rotate 换一个新的）"
  exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "需要 root 权限，请用：sudo bash $0 $*" >&2
  exit 1
fi

if [ -f "$OUT" ] && [ "$ROTATE" -eq 0 ]; then
  echo "$OUT 已存在，未做任何改动。"
  echo "  换密码    : sudo bash $0 --rotate"
  echo "  看用户名  : sudo bash $0 --show-user"
  exit 0
fi

# 32 字节随机 → base64 → 去掉 = + / 以及容易看错的 O 0 I l，取 24 位
PASS="$(head -c 32 /dev/urandom | base64 | tr -d '=+/O0Il' | cut -c1-24)"

if command -v htpasswd >/dev/null 2>&1; then
  htpasswd -bc "$OUT" "$USER_NAME" "$PASS" >/dev/null
else
  # 没装 apache2-utils 时用 openssl 生成 apr1 哈希，格式与 htpasswd 兼容
  HASH="$(openssl passwd -apr1 "$PASS")"
  printf '%s:%s\n' "$USER_NAME" "$HASH" > "$OUT"
fi

chmod 640 "$OUT"
# nginx worker 需要能读到；Debian/Ubuntu 上是 www-data
if getent group www-data >/dev/null 2>&1; then
  chown root:www-data "$OUT"
fi

cat <<EOF

✅ 已写入 $OUT
   用户名：$USER_NAME
   密码  ：$PASS

⚠️  密码只显示这一次，且无法从文件反查（哈希存储）。
    请立刻存进密码管理器，然后清掉这屏终端记录。

生效：
   sudo nginx -t && sudo systemctl reload nginx

之后访问 https://socialsense.cn/forecast 会弹一次密码框；
浏览器记住凭据后，同源的数据请求会自动带上，仪表盘正常显示。
EOF
