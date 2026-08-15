"""
B站 Cookie / User-Agent 配置脚本

用法：
    python setup_cookie.py

功能：
1. 引导粘贴浏览器 Cookie（及可选 User-Agent）
2. 写入 bili_cookie.txt / bili_ua.txt
3. 调用 B 站接口校验是否登录成功
"""

from __future__ import annotations

import os
import sys

try:
    import requests
except ImportError:
    print("缺少依赖：请先执行  pip install requests")
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(SCRIPT_DIR, "bili_cookie.txt")
UA_PATH = os.path.join(SCRIPT_DIR, "bili_ua.txt")

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0"
)

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"


def print_guide() -> None:
    print("=" * 60)
    print("  B站 Cookie 配置向导")
    print("=" * 60)
    print(
        """
操作步骤：
  1. 浏览器打开 https://www.bilibili.com 并登录
  2. 按 F12 → 切换到「网络 / Network」
  3. 刷新页面，点任意 bilibili 请求
  4. 在「请求头 / Request Headers」里找到 Cookie，整段复制
  5. （可选）同理复制 User-Agent
  6. 回到本窗口粘贴即可

提示：Cookie 一般是一行很长的字符串，包含 SESSDATA、bili_jct 等字段。
"""
    )


def read_multiline_or_line(prompt: str) -> str:
    """支持单行粘贴；若误按回车可再输一次。"""
    print(prompt)
    first = input("> ").strip()
    if first:
        return first
    print("（未检测到内容，请再粘贴一次；直接回车则跳过）")
    return input("> ").strip()


def normalize_cookie(raw: str) -> str:
    raw = raw.strip().strip('"').strip("'")
    # 有人会从 DevTools 复制成 "Cookie: xxx"
    if raw.lower().startswith("cookie:"):
        raw = raw.split(":", 1)[1].strip()
    return " ".join(raw.split())


def cookie_looks_valid(cookie: str) -> list[str]:
    """粗检关键字段，返回缺失项（不一定致命）。"""
    missing = []
    for key in ("SESSDATA", "bili_jct"):
        if f"{key}=" not in cookie:
            missing.append(key)
    return missing


def save_text(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


def load_text(path: str) -> str:
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def verify_login(cookie: str, ua: str) -> tuple[bool, str]:
    headers = {"Cookie": cookie, "User-Agent": ua}
    try:
        resp = requests.get(NAV_URL, headers=headers, timeout=15)
        data = resp.json()
    except Exception as e:
        return False, f"请求失败：{e}"

    if data.get("code") != 0:
        return False, f"接口返回异常：code={data.get('code')} message={data.get('message')}"

    info = data.get("data") or {}
    if not info.get("isLogin"):
        return False, "Cookie 无效或已过期（isLogin=false），请重新登录后复制。"

    uname = info.get("uname") or "未知用户"
    mid = info.get("mid") or "?"
    level = (info.get("level_info") or {}).get("current_level", "?")
    return True, f"登录成功：{uname}（UID={mid}，等级={level}）"


def show_status() -> None:
    cookie = load_text(COOKIE_PATH)
    ua = load_text(UA_PATH) or DEFAULT_UA
    print("-" * 60)
    if not cookie:
        print(f"当前状态：未配置 Cookie（期望文件：{COOKIE_PATH}）")
        return

    print(f"Cookie 文件：{COOKIE_PATH}（已存在，长度 {len(cookie)}）")
    print(f"UA 文件：{UA_PATH}（{'已存在' if os.path.isfile(UA_PATH) else '未配置，将用默认 UA'}）")
    ok, msg = verify_login(cookie, ua)
    print(("✓ " if ok else "✗ ") + msg)


def configure() -> None:
    print_guide()
    show_status()
    print("-" * 60)

    raw_cookie = read_multiline_or_line("请粘贴 Cookie（整段粘贴后回车）：")
    if not raw_cookie:
        print("已取消：未写入 Cookie。")
        return

    cookie = normalize_cookie(raw_cookie)
    missing = cookie_looks_valid(cookie)
    if missing:
        print(f"警告：未检测到常见登录字段 {missing}，可能复制不完整。")
        cont = input("仍要继续保存吗？[y/N] ").strip().lower()
        if cont not in ("y", "yes"):
            print("已取消。")
            return

    raw_ua = read_multiline_or_line(
        "请粘贴 User-Agent（可选，直接回车则保留已有/默认值）："
    )
    if raw_ua:
        ua = raw_ua.strip()
        if ua.lower().startswith("user-agent:"):
            ua = ua.split(":", 1)[1].strip()
    else:
        ua = load_text(UA_PATH) or DEFAULT_UA

    save_text(COOKIE_PATH, cookie)
    save_text(UA_PATH, ua)
    print(f"\n已保存：\n  - {COOKIE_PATH}\n  - {UA_PATH}")

    print("\n正在校验登录状态…")
    ok, msg = verify_login(cookie, ua)
    print(("✓ " if ok else "✗ ") + msg)
    if ok:
        print("\n配置完成。可直接运行：python \"B站评论爬虫.py\"")
    else:
        print("\n文件已写入，但校验未通过。请重新登录 B 站后再次运行本脚本。")


def main() -> None:
    # 保证相对路径脚本也能找到同目录文件
    os.chdir(SCRIPT_DIR)

    if len(sys.argv) > 1 and sys.argv[1] in ("-c", "--check"):
        show_status()
        return

    if len(sys.argv) > 1 and sys.argv[1] in ("-a", "--auto"):
        from auto_get_cookie import main as auto_main
        auto_main()
        return

    print("=" * 60)
    print("  B站 Cookie 配置")
    print("=" * 60)
    print("  1) 自动打开浏览器登录并获取（推荐）")
    print("  2) 手动粘贴 Cookie")
    print("  3) 检查当前 Cookie 是否有效")
    print("  0) 退出")
    choice = input("\n请选择 [1/2/3/0]，默认 1：").strip() or "1"

    try:
        if choice == "1":
            from auto_get_cookie import main as auto_main
            auto_main()
        elif choice == "2":
            configure()
        elif choice == "3":
            show_status()
        else:
            print("已退出。")
    except KeyboardInterrupt:
        print("\n已中断。")
        sys.exit(130)


if __name__ == "__main__":
    main()
