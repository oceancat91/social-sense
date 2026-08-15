"""
自动打开浏览器登录 B 站并提取 Cookie

用法：
    pip install playwright requests
    playwright install chromium
    python auto_get_cookie.py

说明：
    会弹出一个浏览器窗口，请在页面中完成登录（账号密码 / 扫码均可）。
    检测到登录成功后，自动把 Cookie 和 User-Agent 写入本地文件。
"""

from __future__ import annotations

import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIE_PATH = os.path.join(SCRIPT_DIR, "bili_cookie.txt")
UA_PATH = os.path.join(SCRIPT_DIR, "bili_ua.txt")
BILI_HOME = "https://www.bilibili.com"
NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
LOGIN_TIMEOUT_SEC = 300  # 最长等待登录时间（秒）


def ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("缺少依赖，请先执行：")
        print("  pip install playwright requests")
        print("  playwright install chromium")
        sys.exit(1)


def cookies_to_header(cookies: list[dict]) -> str:
    # 只要 bilibili 相关域名的 cookie
    parts = []
    seen = set()
    for c in cookies:
        domain = (c.get("domain") or "").lstrip(".")
        if "bilibili.com" not in domain and "bilivideo.com" not in domain:
            continue
        name = c.get("name") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        parts.append(f"{name}={c.get('value', '')}")
    return "; ".join(parts)


def verify_login(cookie: str, ua: str) -> tuple[bool, str]:
    import requests

    try:
        resp = requests.get(
            NAV_URL,
            headers={"Cookie": cookie, "User-Agent": ua},
            timeout=15,
        )
        data = resp.json()
    except Exception as e:
        return False, f"校验请求失败：{e}"

    if data.get("code") != 0:
        return False, f"接口异常：code={data.get('code')} message={data.get('message')}"

    info = data.get("data") or {}
    if not info.get("isLogin"):
        return False, "尚未登录成功"

    uname = info.get("uname") or "未知用户"
    mid = info.get("mid") or "?"
    return True, f"{uname}（UID={mid}）"


def save_auth(cookie: str, ua: str) -> None:
    with open(COOKIE_PATH, "w", encoding="utf-8") as f:
        f.write(cookie.strip() + "\n")
    with open(UA_PATH, "w", encoding="utf-8") as f:
        f.write(ua.strip() + "\n")


def launch_browser(sync_playwright):
    """优先用本机 Edge / Chrome，找不到再用 Playwright 自带 Chromium。"""
    pw = sync_playwright().start()
    last_err = None
    for channel in ("msedge", "chrome", None):
        try:
            if channel:
                browser = pw.chromium.launch(
                    channel=channel,
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                print(f"已启动浏览器通道：{channel}")
            else:
                browser = pw.chromium.launch(
                    headless=False,
                    args=["--disable-blink-features=AutomationControlled"],
                )
                print("已启动 Playwright Chromium")
            return pw, browser
        except Exception as e:
            last_err = e
            continue
    pw.stop()
    raise RuntimeError(f"无法启动浏览器：{last_err}")


def wait_until_logged_in(context, page, ua: str) -> tuple[str, str]:
    print("-" * 60)
    print("请在弹出的浏览器中登录 B 站（扫码或账号均可）。")
    print(f"登录成功后会自动保存，最长等待 {LOGIN_TIMEOUT_SEC} 秒。")
    print("也可在本窗口按 Ctrl+C 取消。")
    print("-" * 60)

    deadline = time.time() + LOGIN_TIMEOUT_SEC
    last_tip = 0

    while time.time() < deadline:
        cookies = context.cookies()
        names = {c.get("name") for c in cookies}
        if "SESSDATA" in names and "bili_jct" in names:
            cookie_header = cookies_to_header(cookies)
            ok, msg = verify_login(cookie_header, ua)
            if ok:
                return cookie_header, msg

        now = time.time()
        if now - last_tip >= 8:
            remain = int(deadline - now)
            print(f"等待登录中… 剩余约 {remain}s（需出现 SESSDATA / bili_jct）")
            last_tip = now

        # 若停在别的页，偶尔拉回首页便于检测
        try:
            if "bilibili.com" not in (page.url or ""):
                page.goto(BILI_HOME, wait_until="domcontentloaded")
        except Exception:
            pass

        time.sleep(2)

    raise TimeoutError("等待登录超时。请重新运行本脚本并完成登录。")


def main() -> None:
    os.chdir(SCRIPT_DIR)
    sync_playwright = ensure_playwright()

    print("=" * 60)
    print("  B站 Cookie 自动获取")
    print("=" * 60)

    pw = browser = context = page = None
    try:
        pw, browser = launch_browser(sync_playwright)
        context = browser.new_context(
            viewport={"width": 1280, "height": 860},
            locale="zh-CN",
        )
        page = context.new_page()
        page.goto(BILI_HOME, wait_until="domcontentloaded", timeout=60000)
        ua = page.evaluate("() => navigator.userAgent")

        cookie_header, user_msg = wait_until_logged_in(context, page, ua)
        save_auth(cookie_header, ua)

        print("\n✓ 登录成功：", user_msg)
        print(f"✓ Cookie 已写入：{COOKIE_PATH}")
        print(f"✓ User-Agent 已写入：{UA_PATH}")
        print('\n下一步可运行：python "B站评论爬虫.py"')
        print("或检查状态：python setup_cookie.py --check")

        # 稍留窗口，方便确认头像已登录
        time.sleep(1.5)
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(130)
    except Exception as e:
        print(f"\n失败：{e}")
        print("若提示缺少浏览器，请执行：playwright install chromium")
        sys.exit(1)
    finally:
        try:
            if browser:
                browser.close()
        except Exception:
            pass
        try:
            if pw:
                pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
