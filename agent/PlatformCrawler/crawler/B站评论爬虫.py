import os
import re
import argparse
import requests
import json
from urllib.parse import quote, urlparse
import pandas as pd
import hashlib
import urllib
import time
import csv
import random
from datetime import datetime, timedelta, timezone
from typing import Any


TZ_CN = timezone(timedelta(hours=8))


def day_to_unix(day: str, *, end_of_day: bool = False) -> int:
    """YYYY-MM-DD → Unix 秒（按东八区；end_of_day=True 为当日 23:59:59）。"""
    dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=TZ_CN)
    if end_of_day:
        dt = dt + timedelta(days=1) - timedelta(seconds=1)
    return int(dt.timestamp())


def classify_ctime(
    ctime: int,
    since_ts: int | None,
    until_ts: int | None,
) -> str:
    """keep | skip_new | skip_old"""
    if until_ts is not None and ctime > until_ts:
        return "skip_new"
    if since_ts is not None and ctime < since_ts:
        return "skip_old"
    return "keep"


# 获取B站的Header（Cookie / UA 可用 setup_cookie.py 配置）
def get_Header():
    base = os.path.dirname(os.path.abspath(__file__))
    cookie_path = os.path.join(base, 'bili_cookie.txt')
    ua_path = os.path.join(base, 'bili_ua.txt')
    default_ua = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0'
    )
    with open(cookie_path, 'r', encoding='utf-8') as f:
        cookie = f.read().strip()
    if not cookie:
        raise FileNotFoundError(
            f'Cookie 为空，请先运行: python setup_cookie.py\n文件位置: {cookie_path}'
        )
    if os.path.isfile(ua_path):
        with open(ua_path, 'r', encoding='utf-8') as f:
            ua = f.read().strip() or default_ua
    else:
        ua = default_ua
    return {"Cookie": cookie, "User-Agent": ua}


def parse_target(raw: str) -> tuple[str, int]:
    """从 BV号 / 链接 解析目标 ID 与类型 flag。
    flag: 1=视频 2=番剧 3=动态
    """
    raw = (raw or "").strip()
    if not raw:
        raise ValueError("目标不能为空")

    # 完整链接
    if raw.startswith("http://") or raw.startswith("https://"):
        path = urlparse(raw).path.strip("/")
        # www.bilibili.com/video/BVxxxx
        m = re.search(r"video/(BV[\w]+)", raw, re.I)
        if m:
            return m.group(1), 1
        # bangumi/play/epxxxx 或 ssxxxx
        m = re.search(r"bangumi/play/(ep\d+|ss\d+)", raw, re.I)
        if m:
            return m.group(1), 2
        # opus/数字 或 动态数字 id
        m = re.search(r"opus/(\d+)", raw)
        if m:
            return m.group(1), 3
        m = re.search(r"/(\d{10,})", path)
        if m:
            return m.group(1), 3
        raise ValueError(f"无法从链接识别目标：{raw}")

    # 纯 ID
    if re.fullmatch(r"BV[\w]+", raw, re.I):
        return raw, 1
    if re.fullmatch(r"(ep|ss)\d+", raw, re.I):
        return raw, 2
    if re.fullmatch(r"\d{10,}", raw):
        return raw, 3

    raise ValueError(
        f"无法识别目标「{raw}」。请提供 BV号、番剧 ep/ss 号、动态 opus 号，或对应完整链接。"
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="B站评论爬虫：可指定视频 / 番剧 / 动态目标",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python B站评论爬虫.py BV1MT4y1M7eJ
  python B站评论爬虫.py https://www.bilibili.com/video/BV1MT4y1M7eJ --pages 2
  python B站评论爬虫.py https://www.bilibili.com/opus/1113811489474478100 --type opus
  python B站评论爬虫.py BV1xx --pages 0 --no-second --mode hot
  python B站评论爬虫.py BV1xx --mode latest --since 2020-01-01 --until 2020-05-31 --pages 50
""",
    )
    p.add_argument(
        "target",
        nargs="?",
        default="BV1MT4y1M7eJ",
        help="BV号 / 番剧号 / 动态opus号，或完整链接（默认: BV1MT4y1M7eJ）",
    )
    p.add_argument(
        "--type",
        choices=["auto", "video", "bangumi", "opus"],
        default="auto",
        help="目标类型，默认 auto 自动识别",
    )
    p.add_argument(
        "--pages",
        type=int,
        default=2,
        help="最多爬取一级评论页数；0 表示不限制（默认 2）",
    )
    p.add_argument(
        "--mode",
        choices=["latest", "hot"],
        default="latest",
        help="latest=最新评论(mode=2)，hot=热门评论(mode=3)",
    )
    p.add_argument(
        "--since",
        default=None,
        help="评论时间下界 YYYY-MM-DD（含当日 00:00 东八区）；仅保留窗内评论",
    )
    p.add_argument(
        "--until",
        default=None,
        help="评论时间上界 YYYY-MM-DD（含当日）；仅保留窗内评论。"
        " latest 模式下翻过 since 后会早停",
    )
    p.add_argument(
        "--no-second",
        action="store_true",
        help="不爬取二级回复",
    )
    return p


# 通过bv号，获取视频的oid
def get_information(bv,flag):
    # 如果是视频 
    if flag == 1:
        resp = requests.get(f"https://www.bilibili.com/video/{bv}",headers=get_Header())
    # 如果是番剧
    elif flag == 2:
        resp = requests.get(f"https://www.bilibili.com/bangumi/play/{bv}",headers=get_Header())
    # 如果是动态
    elif flag == 3:
        resp = requests.get(f"https://www.bilibili.com/opus/{bv}",headers=get_Header())
    else:
        raise ValueError(f"未知类型 flag={flag}")

    if resp.status_code != 200:
        raise RuntimeError(f"请求失败 HTTP {resp.status_code}，无法获取视频信息 (bv={bv})")

    text = resp.text

    if flag == 1:
        # 视频 oid（aid）：按 bvid 精确定位，页面结构变化时逐级回退
        oid = None
        for pat in (
            rf'"aid":(?P<id>\d+),"bvid":"{bv}"',
            rf'"bvid":"{bv}".*?"aid":(?P<id>\d+)',
            r'"aid":(?P<id>\d+)',
        ):
            m = re.search(pat, text)
            if m:
                oid = m.group('id')
                break
    elif flag == 2:
        # 番剧的oid
        m = re.findall(r'aid":(.+?),', text)
        oid = m[0] if m else None
    elif flag == 3:
        # 动态的oid
        m = re.findall(r'"rid_str":"(.+?)"', text)
        oid = m[0] if m else None
    else:
        oid = None

    if not oid:
        raise RuntimeError(f"无法从页面解析视频 oid (bv={bv}, flag={flag})")

    # 提取标题
    try:
        title = re.findall(r'<title>(.+?)</title>', text)[0]
    except Exception:
        title = "未识别"

    return oid, title

# MD5加密
def md5(code):
    MD5 = hashlib.md5()
    MD5.update(code.encode('utf-8'))
    w_rid = MD5.hexdigest()
    return w_rid

def _reply_sub_count(reply: dict[str, Any]) -> int:
    try:
        text = reply["reply_control"]["sub_reply_entry_text"]
        return int(re.findall(r"\d+", text)[0])
    except Exception:
        return 0


def _write_comment_row(csv_writer, count: int, reply: dict[str, Any]) -> None:
    parent = reply["parent"]
    rpid = reply["rpid"]
    uid = reply["mid"]
    name = reply["member"]["uname"]
    level = reply["member"]["level_info"]["current_level"]
    sex = reply["member"]["sex"]
    avatar = reply["member"]["avatar"]
    vip = "否" if reply["member"]["vip"]["vipStatus"] == 0 else "是"
    try:
        IP = reply["reply_control"]["location"][5:]
    except Exception:
        IP = "未知"
    context = reply["content"]["message"]
    reply_time = pd.to_datetime(reply["ctime"], unit="s")
    rereply = _reply_sub_count(reply)
    like = reply["like"]
    try:
        sign = reply["member"]["sign"]
    except Exception:
        sign = ""
    action = "是" if reply.get("action") == 1 else "否"
    up = reply.get("up_action") or {}
    up_action = "是" if up.get("like") is True else "否"
    up_reply = "是" if up.get("reply") is True else "否"
    csv_writer.writerow(
        [
            count,
            parent,
            rpid,
            uid,
            name,
            level,
            sex,
            context,
            reply_time,
            rereply,
            like,
            sign,
            IP,
            vip,
            avatar,
            action,
            up_action,
            up_reply,
        ]
    )


# 轮页爬取；返回 past_window=True 表示已翻过 since（仅 latest 有意义）
def start(
    bv,
    oid,
    pageID,
    count,
    csv_writer,
    is_second,
    flag,
    reply_mode=2,
    since_ts: int | None = None,
    until_ts: int | None = None,
    stats: dict[str, int] | None = None,
):
    mode = reply_mode  # 2=最新，3=热门
    plat = 1
    type = 1
    web_location = 1315875

    if flag == 3:
        type = 11
        if reply_mode is None:
            mode = 3

    wts = int(time.time())

    if pageID != "":
        pagination_str = '{"offset":"%s"}' % pageID
        code = (
            f"mode={mode}&oid={oid}&pagination_str={urllib.parse.quote(pagination_str, safe='')}"
            f"&plat={plat}&type={type}&web_location={web_location}&wts={wts}"
            "ea1db124af3c7062474693fa704f4ff8"
        )
        w_rid = md5(code)
        url = (
            f"https://api.bilibili.com/x/v2/reply/wbi/main?oid={oid}&type={type}&mode={mode}"
            f"&pagination_str={urllib.parse.quote(pagination_str, safe=':')}"
            f"&plat=1&web_location=1315875&w_rid={w_rid}&wts={wts}"
        )
    else:
        pagination_str = '{"offset":""}'
        code = (
            f"mode={mode}&oid={oid}&pagination_str={urllib.parse.quote(pagination_str, safe='')}"
            f"&plat={plat}&seek_rpid=&type={type}&web_location={web_location}&wts={wts}"
            "ea1db124af3c7062474693fa704f4ff8"
        )
        w_rid = md5(code)
        url = (
            f"https://api.bilibili.com/x/v2/reply/wbi/main?oid={oid}&type={type}&mode={mode}"
            f"&pagination_str={urllib.parse.quote(pagination_str, safe=':')}"
            f"&plat=1&seek_rpid=&web_location=1315875&w_rid={w_rid}&wts={wts}"
        )

    comment = requests.get(url=url, headers=get_Header()).content.decode("utf-8")
    comment = json.loads(comment)

    replies = (comment.get("data") or {}).get("replies") or []
    past_window = False
    has_time_filter = since_ts is not None or until_ts is not None

    for reply in replies:
        ctime = int(reply["ctime"])
        cls = classify_ctime(ctime, since_ts, until_ts)
        if cls == "skip_old":
            past_window = True
            if stats is not None:
                stats["skip_old"] = stats.get("skip_old", 0) + 1
            # latest 按时间倒序：本页及之后只会更旧，二级也不再抓
            continue
        if cls == "skip_new":
            if stats is not None:
                stats["skip_new"] = stats.get("skip_new", 0) + 1
            # 太新：继续翻页等进入时间窗；不写、不抓二级
            continue

        count += 1
        if stats is not None:
            stats["kept"] = stats.get("kept", 0) + 1
        _write_comment_row(csv_writer, count, reply)

        if count % 1000 == 0:
            cool_down(count, 30, 60, 2)

        rereply = _reply_sub_count(reply)
        if is_second and rereply != 0:
            for page in range(1, (rereply - 1) // 10 + 2):
                second_url = (
                    f"https://api.bilibili.com/x/v2/reply/reply?oid={oid}&type=1"
                    f"&root={reply['rpid']}&ps=10&pn={page}&web_location=333.788"
                )
                second_comment = requests.get(
                    url=second_url, headers=get_Header()
                ).content.decode("utf-8")
                second_comment = json.loads(second_comment)
                seconds = (second_comment.get("data") or {}).get("replies") or []
                for second in seconds:
                    s_ctime = int(second["ctime"])
                    s_cls = classify_ctime(s_ctime, since_ts, until_ts)
                    if s_cls != "keep":
                        if stats is not None:
                            key = "skip_old" if s_cls == "skip_old" else "skip_new"
                            stats[key] = stats.get(key, 0) + 1
                        continue
                    count += 1
                    if stats is not None:
                        stats["kept"] = stats.get("kept", 0) + 1
                    _write_comment_row(csv_writer, count, second)
                    if count % 1000 == 0:
                        cool_down(count, 30, 60, 2)

    try:
        next_pageID = comment["data"]["cursor"]["pagination_reply"]["next_offset"]
    except Exception:
        next_pageID = 0

    # latest + 时间窗：本页已出现早于 since 的一级评论 → 后续更旧，早停
    if has_time_filter and reply_mode == 2 and past_window:
        print(
            f"已翻过评论时间下界（since），早停。当前写入 {count} 条"
            + (
                f"（kept={stats.get('kept', 0)} skip_new={stats.get('skip_new', 0)} "
                f"skip_old={stats.get('skip_old', 0)}）"
                if stats
                else ""
            )
        )
        return bv, oid, 0, count, csv_writer, is_second, True

    if next_pageID == 0:
        print(f"评论爬取完成！总共写入 {count} 条。")
        return bv, oid, next_pageID, count, csv_writer, is_second, past_window

    print(f"当前已写入 {count} 条。")
    cool_down(count, 1, 10, 1)
    return bv, oid, next_pageID, count, csv_writer, is_second, past_window


# 冷却函数
def cool_down(count, min_sec, max_sec, cd_flag):
    if cd_flag == 1:
        page_cd = random.uniform(min_sec, max_sec)
        print(f"爬虫已进入下一页，为避免触发反爬机制，暂停 {page_cd} 秒...")
        time.sleep(page_cd)
    elif cd_flag == 2:
        comment_cd = random.uniform(min_sec, max_sec)
        print(f"已爬取 {count} 条评论，为避免触发反爬机制，暂停 {comment_cd} 秒...")
        time.sleep(comment_cd)


if __name__ == "__main__":
    args = build_arg_parser().parse_args()

    type_map = {"video": 1, "bangumi": 2, "opus": 3}
    if args.type == "auto":
        bv, flag = parse_target(args.target)
    else:
        bv = args.target.strip()
        try:
            bv, _ = parse_target(args.target)
        except ValueError:
            pass
        flag = type_map[args.type]

    reply_mode = 3 if args.mode == "hot" else 2
    is_second = not args.no_second
    max_pages = None if args.pages == 0 else args.pages

    since_ts = day_to_unix(args.since) if args.since else None
    until_ts = day_to_unix(args.until, end_of_day=True) if args.until else None
    if since_ts is not None and until_ts is not None and since_ts > until_ts:
        raise SystemExit("--since 不能晚于 --until")

    oid, title = get_information(bv, flag=flag)
    next_pageID = ""
    count = 0
    stats: dict[str, int] = {"kept": 0, "skip_new": 0, "skip_old": 0}

    print(f"当前爬取目标：{title} - {bv}")
    print(
        f"类型 flag={flag}（1视频/2番剧/3动态），排序={args.mode}，"
        f"二级回复={'开' if is_second else '关'}"
    )
    if args.since or args.until:
        print(
            f"评论时间窗：[{args.since or '-∞'}, {args.until or '+∞'}]（东八区，含首尾日）"
            + ("；latest 模式下越过 since 将早停" if args.mode == "latest" else "")
        )
    if max_pages:
        print(f"本次限制：最多 {max_pages} 页一级评论")
    else:
        print("本次限制：不限制页数")

    safe_name = re.sub(r'[\\/:*?"<>|]', "_", title[:10])
    out_path = f"{safe_name}...的评论_{bv}.csv"
    with open(out_path, mode="w", newline="", encoding="utf-8-sig") as file:
        csv_writer = csv.writer(file)
        csv_writer.writerow(
            [
                "序号",
                "上级评论ID",
                "评论ID",
                "用户ID",
                "用户名",
                "用户等级",
                "性别",
                "评论内容",
                "评论时间",
                "回复数",
                "点赞数",
                "个性签名",
                "IP属地",
                "是否为大会员",
                "头像",
                "当前账号是否点赞",
                "UP主是否点赞",
                "UP主是否回复",
            ]
        )

        page_num = 0
        while next_pageID != 0:
            page_num += 1
            bv, oid, next_pageID, count, csv_writer, is_second, _past = start(
                bv,
                oid,
                next_pageID,
                count,
                csv_writer,
                is_second,
                flag=flag,
                reply_mode=reply_mode,
                since_ts=since_ts,
                until_ts=until_ts,
                stats=stats,
            )
            if max_pages and page_num >= max_pages:
                print(f"已达到页数上限（{max_pages} 页），停止爬取。共写入 {count} 条。")
                break

    if args.since or args.until:
        print(
            f"时间窗统计：写入={stats['kept']}，跳过过新={stats['skip_new']}，"
            f"跳过过旧={stats['skip_old']}"
        )
    print(f"结果已保存：{out_path}")
