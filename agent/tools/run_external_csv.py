"""
外部评论 CSV 接入工具：把已爬取清洗好的评论数据接入多 Agent 流程并跑通。

适用数据：单/多平台评论 CSV（如抖音导出的 all_comments_cleaned.csv）。
按话题（topic_name / domain）切分为多个「信息圈层」，每个圈层跑单平台 Skill1→2
产出标准 D_platform + 立场画像，再交给 multiagent 主控做跨圈层对齐 / 融合，
度量同平台不同话题圈层之间的立场分化、情绪分化与信息茧房指数。

用法：
  python -m tools.run_external_csv "D:/.../all_comments_cleaned.csv" \
      --granularity day --min-count 1000 --sample 0 --out-dir dataset/external_run

  # 快速验证（每话题采样 1500 条、只跑数据量最大的若干话题）
  python -m tools.run_external_csv "D:/.../all_comments_cleaned.csv" \
      --min-count 3000 --sample 1500
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# —— 路径注入：agent 目录（顶层包）+ 仓库根（multiagent 包）—— #
AGENT_DIR = Path(__file__).resolve().parents[1]      # .../agent
REPO_ROOT = AGENT_DIR.parent                         # 仓库根
for _p in (str(AGENT_DIR), str(REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from PlatformCrawler.dataloader.builder import build_d_platform  # noqa: E402
from PlatformCrawler.dataloader.cleaner import clean_records      # noqa: E402
from StanceProfiler.profiler import profile_d_platform            # noqa: E402
from multiagent.master import run_master                          # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
csv.field_size_limit(10 * 1024 * 1024)


def _topic_short(topic_name: str) -> str:
    """去掉「(待话题聚类)」等后缀，得到简洁圈层名。"""
    name = (topic_name or "其他").strip()
    for suffix in ("(待话题聚类)", "（待话题聚类）"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name.strip() or "其他"


def _to_raw_field(row: dict[str, Any]) -> dict[str, Any]:
    """CSV 行 -> 跨平台原始字段（clean_records 输入契约）。"""
    parent = (row.get("parent_comment_id") or "").strip()
    parent_id = None if parent in ("", "0") else parent

    def num(key: str) -> float:
        try:
            return float(row.get(key) or 0)
        except (TypeError, ValueError):
            return 0.0

    return {
        "platform": (row.get("platform") or "").strip() or "douyin",
        "content_id": (row.get("comment_id") or "").strip() or None,
        "parent_id": parent_id,
        "author_id": (row.get("author_id_hash") or "").strip() or None,
        "text": (row.get("text_structured_clean") or "").strip(),
        "ts_raw": (row.get("publish_time") or "").strip(),
        "like": num("like_count"),
        "reply_count": num("comment_count"),
        "share_or_coin": num("share_count") + num("collect_count"),
        "source_url": (row.get("source_content_url") or "").strip() or None,
        "ext": {
            "uname": (row.get("author_name") or "").strip(),
            "ip": (row.get("ip_label") or "").strip(),
            "topic": (row.get("topic_name") or "").strip(),
            "keywords": (row.get("keywords") or "").strip(),
        },
    }


def load_grouped(csv_path: str) -> dict[str, list[dict[str, Any]]]:
    """读 CSV，按话题圈层分组为跨平台原始字段列表。"""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            topic = _topic_short(row.get("topic_name") or "")
            rec = _to_raw_field(row)
            if rec["text"] and rec["ts_raw"]:
                groups[topic].append(rec)
    return groups


def _time_range(records: list[dict[str, Any]]) -> tuple[str, str]:
    """由记录的 ts_raw（YYYY-MM-DD HH:MM:SS）求 [since, until_exclusive] 日界。"""
    days = sorted({r["ts_raw"][:10] for r in records if r.get("ts_raw")})
    since = days[0]
    until_dt = datetime.strptime(days[-1], "%Y-%m-%d") + timedelta(days=1)
    return since, until_dt.strftime("%Y-%m-%d")


def analyze_topic(
    topic: str,
    records: list[dict[str, Any]],
    *,
    granularity: str,
) -> dict[str, Any]:
    """单圈层：clean → build D_platform → Skill2 立场画像 → 组装 PlatformReport。"""
    since, until = _time_range(records)
    start = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=TZ)
    end = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=TZ)

    platform = records[0].get("platform") or "douyin"
    bundle = clean_records(records, time_range=(start, end), platform=platform)
    d_platform = build_d_platform(
        bundle,
        keyword=topic,
        time_range=(since, until),
        granularity=granularity,
        platform=platform,
    )
    # Skill2：按平台词表做立场/情绪画像（原地刷新 D_ts/D_meta）
    d_platform, profile = profile_d_platform(d_platform)

    meta = dict(d_platform["D_meta"])
    # 让 master 以「话题圈层」为区分维度（platform 字段置为圈层名）
    meta["platform"] = f"{platform}:{topic}"
    meta["keyword"] = topic

    report = {
        "schema_version": "platform_report_v1",
        "platform": meta["platform"],
        "keyword": topic,
        "meta": meta,
        "D_ts": d_platform["D_ts"],
        "stance_dist": profile.get("stance_ratios") or {},
        "stance_profile": profile,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {
        "report": report,
        "n_text": meta.get("n_text"),
        "stance_global": meta.get("stance_global"),
        "sentiment_global_mean": meta.get("sentiment_global_mean"),
        "bias_score": meta.get("bias_score"),
        "stance_ratios": profile.get("stance_ratios") or {},
        "time_range": (since, until),
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="外部评论 CSV 接入多 Agent 流程")
    parser.add_argument("csv", help="评论 CSV 路径")
    parser.add_argument("--granularity", choices=["hour", "day"], default="day")
    parser.add_argument("--min-count", type=int, default=1000,
                        help="话题最少条数，低于此跳过")
    parser.add_argument("--sample", type=int, default=0,
                        help="每话题采样上限（0=全量）")
    parser.add_argument("--max-topics", type=int, default=0,
                        help="只跑数据量最大的前 N 个话题（0=全部）")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default="dataset/external_run",
                        help="输出目录（相对 agent/）")
    args = parser.parse_args(argv)

    random.seed(args.seed)
    print(f"==> 读取 CSV: {args.csv}")
    groups = load_grouped(args.csv)
    print(f"==> 话题圈层数: {len(groups)}，总记录: {sum(len(v) for v in groups.values())}")

    # 按数据量排序，过滤 & 采样
    ordered = sorted(groups.items(), key=lambda kv: len(kv[1]), reverse=True)
    ordered = [(t, r) for t, r in ordered if len(r) >= args.min_count]
    if args.max_topics > 0:
        ordered = ordered[: args.max_topics]

    reports: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for topic, records in ordered:
        if args.sample > 0 and len(records) > args.sample:
            records = random.sample(records, args.sample)
        print(f"\n==> [{topic}] 记录={len(records)} 分析中...")
        res = analyze_topic(topic, records, granularity=args.granularity)
        reports.append(res["report"])
        summaries.append({k: v for k, v in res.items() if k != "report"} | {"topic": topic})
        sr = res["stance_ratios"]
        print(
            f"    n_text={res['n_text']} 主导立场={res['stance_global']} "
            f"情绪均值={res['sentiment_global_mean']} 偏向={res['bias_score']:.3f}\n"
            f"    立场分布: 支持{sr.get('support',0):.2f} 反对{sr.get('oppose',0):.2f} "
            f"中立{sr.get('neutral',0):.2f} 混合{sr.get('mixed',0):.2f}"
        )

    if len(reports) < 1:
        print("没有满足条件的话题，退出。")
        return

    print(f"\n==> 主控融合（{len(reports)} 个话题圈层）...")
    ct = run_master(reports, use_llm=False)

    out_dir = AGENT_DIR / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "master_result.json").write_text(
        json.dumps(ct, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "topic_summaries.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 单圈层 report 也各存一份（去掉超大的 D_ts 以便查看）
    for r in reports:
        slim = {k: v for k, v in r.items() if k != "D_ts"}
        safe = str(r["platform"]).replace(":", "_").replace("/", "_")
        (out_dir / f"report_{safe}.json").write_text(
            json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("\n" + "=" * 60)
    print("跨圈层融合结果（CT）")
    print("=" * 60)
    ec = ct.get("echo_chamber") or {}
    fusion = ct.get("fusion") or {}
    print(f"CT_status: {ct.get('CT_status')}")
    print(f"信息茧房指数 echo_chamber_score: {ec.get('score')}")
    print(f"  分量: {ec.get('components')}")
    print(f"立场分歧 stance_divergence: {fusion.get('stance_divergence')}")
    print(f"情绪分歧 sentiment_divergence: {fusion.get('sentiment_divergence')}")
    print(f"各圈层主导立场: {fusion.get('dominant_stance')}")
    print(f"风险提示 risk_flags: {ct.get('risk_flags')}")
    print(f"\n归纳 summary:\n{ct.get('summary')}")
    print(f"\n结果已保存: {out_dir}")


if __name__ == "__main__":
    main()
