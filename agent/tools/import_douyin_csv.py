"""抖音清洗评论 CSV 接入工具：与其他平台(bilibili/weibo/xiaohongshu)相同口径处理。

输入为抖音导出的单文件清洗评论 CSV（如 all_comments_cleaned.csv），
其中每行含 ``domain``（12 大领域编码）与中文 topic_name。本工具：

1. 按 domain 拆分 CSV -> raw/douyin/{domain}__broad.csv（broad 粒度）。
2. 对每个 domain 构建 D_platform，运行 Skill2 StanceProfiler 与
   Skill3 多尺度异常检测，产出 reports/douyin/{domain}__broad.json。
3. 重新融合 broad fusion（bilibili+weibo+douyin 三个平台同域报告），
   覆盖 fusion/{domain}__broad.json，并更新 manifest / fusion index。

示例：
  python -m tools.import_douyin_csv "D:/.../all_comments_cleaned.csv" \
      --granularity day --text-tower   # 全量
  # 调试：只跑一个 domain
  python -m tools.import_douyin_csv "D:/.../all_comments_cleaned.csv" --only-domain sports_fitness
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

AGENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_DIR.parent
for _path in (str(AGENT_DIR), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position,import-error
from MultimodalAnalyzer.analyzer import AnalyzerConfig, run_analysis  # noqa: E402
from PlatformCrawler.dataloader.builder import build_d_platform  # noqa: E402
from PlatformCrawler.dataloader.cleaner import clean_records  # noqa: E402
from StanceProfiler.profiler import profile_d_platform  # noqa: E402
from multiagent.master import run_master  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
csv.field_size_limit(20 * 1024 * 1024)

DOMAIN_NAMES = {
    "culture_history": "文化历史与艺术",
    "economy_business": "财经商业与职场",
    "education_science": "教育科研与科普",
    "entertainment": "影视娱乐与明星",
    "games_anime": "游戏动漫与虚拟内容",
    "health_psychology": "医疗健康与心理",
    "life_consumption": "生活消费与家庭",
    "nature_rural": "自然环境与三农动物",
    "public_affairs": "时政与公共治理",
    "society_law": "社会事件与法治",
    "sports_fitness": "体育竞技与健身",
    "technology_industry": "科技工业与交通",
}

REQUIRED_COLUMNS = {
    "platform",
    "content_type",
    "author_name",
    "publish_time",
    "text_structured_clean",
    "like_count",
    "comment_count",
    "share_count",
    "collect_count",
}

SEVERITY_RANK = {"none": 0, "warning": 1, "important": 2, "critical": 3}


def _number(row: dict[str, Any], key: str) -> float:
    try:
        return float(row.get(key) or 0)
    except (TypeError, ValueError):
        return 0.0


def _stable_id(
    platform: str,
    source_key: str,
    row_number: int,
    row: dict[str, Any],
) -> str:
    import hashlib

    raw = "\x1f".join(
        [
            platform,
            source_key,
            str(row_number),
            str(row.get("publish_time") or ""),
            str(row.get("author_name") or ""),
            str(row.get("text_structured_clean") or ""),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _to_raw_record(
    row: dict[str, Any],
    *,
    platform: str,
    source_key: str,
    row_number: int,
    file_meta: dict[str, str],
) -> dict[str, Any]:
    import hashlib

    author = str(row.get("author_name") or "").strip()
    author_hash = hashlib.sha1(author.encode("utf-8")).hexdigest() if author else None
    emotion = {
        key: _number(row, key)
        for key in (
            "sentiment_joy_score",
            "sentiment_anger_score",
            "sentiment_sadness_score",
            "sentiment_questioning_score",
            "sentiment_surprise_score",
            "sentiment_fear_score",
            "sentiment_primary_score",
        )
        if row.get(key) not in (None, "")
    }
    return {
        "platform": platform,
        "content_id": _stable_id(platform, source_key, row_number, row),
        "parent_id": None,
        "author_id": author_hash,
        "text": str(row.get("text_structured_clean") or "").strip(),
        "ts_raw": str(row.get("publish_time") or "").strip(),
        "like": _number(row, "like_count"),
        "reply_count": _number(row, "comment_count"),
        "share_or_coin": _number(row, "share_count") + _number(row, "collect_count"),
        "source_url": str(row.get("source_content_url") or "").strip() or None,
        "ext": {
            "uname": author,
            "content_type": str(row.get("content_type") or "").strip(),
            "domain": file_meta["domain"],
            "domain_name": file_meta["domain_name"],
            "scope": file_meta["scope"],
            "hot_topic": file_meta["hot_topic"],
            "source_file": source_key,
            "view_count": _number(row, "view_count"),
            "relevance_score_pred": (
                _number(row, "relevance_score_pred")
                if row.get("relevance_score_pred") not in (None, "")
                else None
            ),
            "source_sentiment": emotion,
        },
    }


def _time_range(records: list[dict[str, Any]]) -> tuple[str, str]:
    import re

    dates = sorted(
        {
            str(record.get("ts_raw") or "")[:10]
            for record in records
            if re.match(r"^\d{4}-\d{2}-\d{2}", str(record.get("ts_raw") or ""))
        }
    )
    if not dates:
        raise ValueError("没有可解析的 publish_time")
    end = datetime.strptime(dates[-1], "%Y-%m-%d") + timedelta(days=1)
    return dates[0], end.strftime("%Y-%m-%d")


def _load_rows_by_domain(csv_path: Path) -> dict[str, list[dict[str, Any]]]:
    """读抖音 CSV，按 domain 编码分组为跨平台原始字段列表。"""
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    source_key = f"douyin/{csv_path.name}"
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"{csv_path.name} 缺少字段：{missing}")
        for row_number, row in enumerate(reader, start=2):
            domain = str(row.get("domain") or "").strip().lower()
            if domain not in DOMAIN_NAMES:
                continue
            rec = _to_raw_record(
                row,
                platform="douyin",
                source_key=source_key,
                row_number=row_number,
                file_meta={
                    "domain": domain,
                    "domain_name": DOMAIN_NAMES[domain],
                    "scope": "broad",
                    "hot_topic": "",
                },
            )
            if not rec["text"] or len(rec["ts_raw"]) < 10:
                continue
            groups[domain].append(rec)
    return groups


def _analyze_domain(
    records: list[dict[str, Any]],
    domain: str,
    *,
    granularity: str,
    text_tower: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """单领域：clean → build D_platform → Skill2 → Skill3 → PlatformReport。"""
    since, until = _time_range(records)
    start = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=TZ)
    end = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=TZ)
    bundle = clean_records(
        records,
        time_range=(start, end),
        platform="douyin",
    )
    d_platform = build_d_platform(
        bundle,
        keyword=DOMAIN_NAMES[domain],
        time_range=(since, until),
        granularity=granularity,
        platform="douyin",
    )
    d_platform, stance_profile = profile_d_platform(d_platform)
    skill3 = run_analysis(
        d_platform,
        AnalyzerConfig(enable_text_tower=text_tower),
    )
    meta = d_platform.get("D_meta") or {}
    severity_counts = Counter(
        str(anomaly.get("severity") or "warning")
        for anomaly in skill3.get("anomalies") or []
    )
    anomaly_type_counts = Counter(
        str(anomaly.get("type"))
        for anomaly in skill3.get("anomalies") or []
        if anomaly.get("type")
    )
    anomalies = sorted(
        skill3.get("anomalies") or [],
        key=lambda item: (
            -SEVERITY_RANK.get(str(item.get("severity") or "warning"), 0),
            -float(item.get("score") or 0),
        ),
    )
    report = {
        "schema_version": "platform_report_v1",
        "platform": "douyin",
        "keyword": DOMAIN_NAMES[domain],
        "time_range": meta.get("time_range"),
        "granularity": meta.get("granularity"),
        "meta": meta,
        "D_ts": d_platform.get("D_ts") or [],
        "stance_dist": stance_profile.get("stance_ratios") or {},
        "stance_profile": stance_profile,
        "skill3": {
            "anomalies": anomalies[:100],
            "n_anomalies": len(anomalies),
            "anomalies_truncated": len(anomalies) > 100,
            "risk_summary": skill3.get("risk_summary") or {},
            "severity_counts": dict(severity_counts),
            "anomaly_type_counts": dict(anomaly_type_counts),
            "multiscale_windows": (skill3.get("multiscale") or {}).get("windows") or [],
            "need_recrawl": bool(skill3.get("need_recrawl")),
        },
        "OT1": {
            "OT1_status": "not_run",
            "claim_stance": meta.get("stance_global"),
            "risk_flags": [],
            "summary_analysis": "",
        },
        "source": {
            "raw_csv": "douyin/all_comments_cleaned.csv",
            "domain": domain,
            "domain_name": DOMAIN_NAMES[domain],
            "scope": "broad",
            "hot_topic": "",
        },
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
    }
    summary = {
        "n_text": int(meta.get("n_text") or 0),
        "n_buckets": int(meta.get("n_buckets") or 0),
        "empty_ratio": float(meta.get("empty_ratio") or 0),
        "time_range": meta.get("time_range"),
        "stance_global": meta.get("stance_global"),
        "sentiment_global_mean": meta.get("sentiment_global_mean"),
        "bias_score": meta.get("bias_score"),
        "n_anomalies": len(anomalies),
        "max_severity": (skill3.get("risk_summary") or {}).get("max_severity"),
    }
    return report, summary


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _archive_raw_csv(
    csv_path: Path,
    raw_dir: Path,
) -> Path:
    """把抖音原始 CSV 留存一份到 raw/douyin/（供追溯）。"""
    target = raw_dir / "douyin" / csv_path.name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(csv_path, target)
    return target


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="抖音清洗 CSV 接入多 Agent 流程")
    parser.add_argument("csv", help="抖音评论 CSV 路径")
    parser.add_argument("--granularity", choices=["hour", "day"], default="day")
    parser.add_argument("--only-domain", default=None,
                        help="只处理某个 domain（调试用），如 public_affairs")
    parser.add_argument("--skip-done", action="store_true",
                        help="跳过已存在且可解析的 douyin 平台报告（断点续跑）")
    parser.add_argument("--out-dir", default="dataset/real_multiplatform",
                        help="相对 agent/ 的输出目录")
    parser.add_argument("--fusion-only", action="store_true",
                        help="只重跑 broad fusion（不重新生成 douyin 平台报告）")
    parser.add_argument("--sample", type=int, default=0,
                        help="每个 domain 采样上限，0=全量")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--text-tower", action="store_true", help="启用 Skill3 文本塔")
    args = parser.parse_args(argv)

    import random

    random.seed(args.seed)
    csv_path = Path(args.csv)
    if not csv_path.exists():
        raise FileNotFoundError(csv_path)

    output_dir = AGENT_DIR / args.out_dir
    raw_dir = output_dir / "raw"
    reports_dir = output_dir / "reports"
    fusion_dir = output_dir / "fusion"

    # 用平台已存在的报告重新跑 fusion（含 douyin 报告，若已生成）
    def refusion() -> None:
        fusion_index = _read_json(fusion_dir / "index.json")
        counter = 0
        for entry in fusion_index:
            if entry.get("scope") != "broad":
                continue
            stem = Path(str(entry["file"])).stem  # {domain}__broad
            reports = []
            for platform in ("bilibili", "weibo", "douyin"):
                rp = reports_dir / platform / f"{stem}.json"
                if rp.exists():
                    reports.append(_read_json(rp))
            if len(reports) < 2:
                continue
            result = run_master(reports, use_llm=False)
            fusion_path = fusion_dir / f"{stem}.json"
            _write_json(fusion_path, result)
            entry["platforms"] = [r.get("platform") for r in reports]
            entry["CT_status"] = result.get("CT_status")
            entry["echo_chamber_score"] = (result.get("echo_chamber") or {}).get("score")
            counter += 1
            print(f"[fusion] {stem} <- {entry['platforms']} / {entry['CT_status']}")
        _write_json(fusion_dir / "index.json", fusion_index)
        print(f"\n重跑 broad fusion 完成：{counter} 条")

    if args.fusion_only:
        refusion()
        return

    # 0) 留存原始 CSV
    raw_target = _archive_raw_csv(csv_path, raw_dir)
    print(f"==> raw 留存: {raw_target.relative_to(AGENT_DIR)}")

    # 1) 拆分并生成 douyin 平台报告
    groups = _load_rows_by_domain(csv_path)
    if args.only_domain:
        if args.only_domain not in DOMAIN_NAMES:
            raise ValueError(f"未知 domain：{args.only_domain}")
        groups = {args.only_domain: groups.get(args.only_domain, [])}
    print(f"==> 读取 {csv_path.name}，领域数={len(groups)}，"
          f"总记录={sum(len(v) for v in groups.values())}")

    douyin_entries = []
    for domain in sorted(DOMAIN_NAMES.keys()):
        if domain not in groups:
            continue
        report_path = reports_dir / "douyin" / f"{domain}__broad.json"
        if args.skip_done and report_path.exists():
            try:
                existing = _read_json(report_path)
                if existing.get("platform") == "douyin":
                    meta = existing.get("meta") or {}
                    print(f"[skip] {domain} 已存在报告，n_text={meta.get('n_text')}")
                    douyin_entries.append(
                        {
                            "domain": domain,
                            "domain_name": DOMAIN_NAMES[domain],
                            "scope": "broad",
                            "report": str(report_path.relative_to(AGENT_DIR)),
                            "n_text": int(meta.get("n_text") or 0),
                            "n_buckets": int(meta.get("n_buckets") or 0),
                            "stance_global": meta.get("stance_global"),
                            "sentiment_global_mean": meta.get("sentiment_global_mean"),
                            "bias_score": meta.get("bias_score"),
                            "n_anomalies": len(
                                (existing.get("skill3") or {}).get("anomalies") or []
                            ),
                            "max_severity": (
                                (existing.get("skill3") or {}).get("risk_summary") or {}
                            ).get("max_severity"),
                        }
                    )
                    continue
            except Exception:  # noqa: BLE001
                pass  # 报告损坏则重跑
        records = groups[domain]
        if args.sample > 0 and len(records) > args.sample:
            records = random.sample(records, args.sample)
        print(f"\n==> [{domain}] {DOMAIN_NAMES[domain]} 记录={len(records)} 分析中...")
        report, stats = _analyze_domain(
            records,
            domain,
            granularity=args.granularity,
            text_tower=args.text_tower,
        )
        report_path = reports_dir / "douyin" / f"{domain}__broad.json"
        _write_json(report_path, report)
        print(
            f"    保存 {report_path.relative_to(AGENT_DIR)} "
            f"n_text={stats['n_text']} 主导={stats['stance_global']} "
            f"情绪均值={stats['sentiment_global_mean']} "
            f"异常数={stats['n_anomalies']} risk={stats['max_severity']}"
        )
        douyin_entries.append(
            {
                "domain": domain,
                "domain_name": DOMAIN_NAMES[domain],
                "scope": "broad",
                "report": str(report_path.relative_to(AGENT_DIR)),
                **stats,
            }
        )

    if not douyin_entries:
        print("没有生成任何 douyin 平台报告。")
        return

    # 2) 全量跑（含 12 domain）时重跑 broad fusion
    if args.only_domain:
        print("\n==> 调试模式（--only-domain），跳过 fusion。"
              "全量运行后再 fusion。")
    else:
        refusion()

    # 3) 更新 manifest 的 summary（追加 douyin 平台概况）
    manifest_path = output_dir / "manifest.json"
    manifest = _read_json(manifest_path) if manifest_path.exists() else {}
    summary = manifest.get("summary") or {}
    platform_counts = summary.get("files_per_platform") or {}
    platform_counts["douyin"] = len(douyin_entries)
    summary["platforms"] = sorted(set(summary.get("platforms") or []) | {"douyin"})
    summary["files_per_platform"] = platform_counts
    manifest["summary"] = summary
    manifest["douyin_run"] = {
        "csv": str(csv_path.resolve()),
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "domains": douyin_entries,
    }
    _write_json(manifest_path, manifest)
    print(f"\n==> 完成，douyin 报告 {len(douyin_entries)} 个领域。")

    for e in douyin_entries:
        print(
            f"  {e['domain']} {e['domain_name']}: "
            f"n_text={e['n_text']} 主导={e['stance_global']} "
            f"bias={e['bias_score']:.3f} 异常={e['n_anomalies']}"
        )


if __name__ == "__main__":
    main()
