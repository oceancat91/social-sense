#!/usr/bin/env python3
"""把 acme.sh account.conf 里保存的腾讯云凭证替换为只限 DNS 的子用户密钥。

用法（密钥从环境变量读，绝不写进仓库）：
    TC_NEW_SID=AKID... TC_NEW_SKEY=... python3 scripts/swap_acme_credentials.py

背景：acme.sh 首次保存凭证后不会覆盖，即使用环境变量重新签发成功，
account.conf 里仍是旧的主账号密钥 —— 将来 cron 续期会用旧的，必须显式替换。
"""
import os
import pathlib
import re
import sys

NEW_ID = os.environ.get("TC_NEW_SID", "").strip()
NEW_KEY = os.environ.get("TC_NEW_SKEY", "").strip()
if not NEW_ID or not NEW_KEY:
    sys.exit("缺少 TC_NEW_SID / TC_NEW_SKEY 环境变量")

p = pathlib.Path.home() / ".acme.sh/account.conf"
if not p.exists():
    sys.exit("找不到 account.conf")

s = p.read_text(encoding="utf-8")
before = s

# acme.sh 用 SAVED_X='value' 形式（带单引号），保持一致
s = re.sub(r"^SAVED_Tencent_SecretId=.*$", f"SAVED_Tencent_SecretId='{NEW_ID}'", s, flags=re.M)
s = re.sub(r"^SAVED_Tencent_SecretKey=.*$", f"SAVED_Tencent_SecretKey='{NEW_KEY}'", s, flags=re.M)

if s == before:
    print("  ⚠ 未匹配到要替换的行，以下是现有 Tencent 相关行：")
    for line in before.splitlines():
        if "Tencent" in line:
            print("   ", re.sub(r"(=.{0,14}).*", r"\1…", line))
    sys.exit(1)

p.write_text(s, encoding="utf-8")
print("  ✓ 已替换")

# 回显脱敏结果
for line in p.read_text().splitlines():
    if "Tencent_SecretId" in line or "Tencent_SecretKey" in line:
        print("   " + re.sub(r"(=.{0,16}).*", r"\1…", line))
