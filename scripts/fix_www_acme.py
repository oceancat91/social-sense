#!/usr/bin/env python3
"""修复 www 的 80 端口块：让 ACME 挑战路径不被 server 级 return 301 吞掉。

nginx 的 server 级 return 在 rewrite 阶段执行，先于 location 匹配，
所以即使 server 块里写了 location /.well-known/acme-challenge/ 也不会生效。
必须把 return 下沉到 location / 里，让 ACME 路径有机会先被匹配。
"""
import re
import subprocess
import sys

CONF = "/etc/nginx/sites-enabled/social-sense"

text = open(CONF, encoding="utf-8").read()
original = text

# ---- www 的 80 块 ----
old80 = """server {
    listen 80;
    server_name www.socialsense.cn;
    return 301 http://socialsense.cn$request_uri;
}"""
new80 = """server {
    listen 80;
    server_name www.socialsense.cn;

    # ACME 挑战必须排在 return 之前：server 级 return 在 rewrite 阶段执行，
    # 会先于 location 匹配，导致挑战请求被 301 走。
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
        try_files $uri =404;
    }

    location / {
        return 301 http://socialsense.cn$request_uri;
    }
}"""

if old80 in text:
    text = text.replace(old80, new80)
    print("  www:80 已改为 location 形式")
elif "location ^~ /.well-known/acme-challenge/" in text and "www.socialsense.cn" in text:
    print("  www:80 结构不同，尝试正则替换")
    # 兜底：把 www 块里的裸 return 换成 location /
    pattern = re.compile(
        r"(server_name www\.socialsense\.cn;\s*\n)(\s*)(return 301 http://socialsense\.cn\$request_uri;)"
    )
    m = pattern.search(text)
    if m:
        text = pattern.sub(lambda mm: mm.group(1) + mm.group(2) + "location / {\n" + mm.group(2) + "    return 301 http://socialsense.cn$request_uri;\n" + mm.group(2) + "}", text, count=1)
        print("  已转换")
else:
    print("    :80 块未找到，跳过")

# 确保 www:80 块里有 ACME location（若上面替换没带上）
if "www.socialsense.cn" in text and text.count("location ^~ /.well-known/acme-challenge/") < 3:
    # 在 www 80 块内补一个
    m = re.search(r"(server_name www\.socialsense\.cn;\s*\n)", text)
    if m and "location / {" in text[m.end():m.end() + 400]:
        acme = """
    location ^~ /.well-known/acme-challenge/ {
        root /var/www/acme;
        default_type text/plain;
        try_files $uri =404;
    }
"""
        text = text[: m.end()] + acme + text[m.end():]
        print("  已在 www:80 补上 ACME location")
    else:
        print("  www:80 内部结构异常，需人工确认")

if text == original:
    print("  配置未变化")
else:
    open(CONF, "w", encoding="utf-8").write(text)
    print("  已写入")

print(f"  ACME location 数量: {text.count('location ^~ /.well-known/acme-challenge/')}")
r = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
print("  nginx -t:", (r.stdout + r.stderr).strip().replace("\n", " | "))
sys.exit(0 if r.returncode == 0 else 1)
