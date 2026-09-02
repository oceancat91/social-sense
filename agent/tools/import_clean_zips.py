"""清洗后多平台 ZIP 接入工具。

功能：
1. 按 ZIP UTF-8 标志解码文件名；旧式 CP437 文件名尝试恢复为 UTF-8/GB18030。
2. Unicode NFC 规范化并安全解压 CSV，拒绝绝对路径和 ``..`` 路径穿越。
3. 将统一 CSV schema 映射为 PlatformCrawler 原始字段，构建 D_platform。
4. 运行 Skill2 StanceProfiler 与 Skill3 CrossAD 启发的多尺度异常检测。
5. 按同一 hot 话题或 broad 领域运行跨平台 Master 融合。

示例：
  python -m tools.import_clean_zips \
    --archive bilibili="D:/.../data_bili_clean.zip" \
    --archive weibo="D:/.../data_weibo_clean(1).zip" \
    --archive xiaohongshu="D:/.../data_xhs_clean.zip"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
import unicodedata
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any
from zoneinfo import ZoneInfo

AGENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_DIR.parent
for _path in (str(AGENT_DIR), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# CLI 运行时动态加入 agent/ 与仓库根目录。
# pylint: disable=wrong-import-position,import-error
from MultimodalAnalyzer.analyzer import AnalyzerConfig, run_analysis  # noqa: E402
from PlatformCrawler.dataloader.builder import build_d_platform  # noqa: E402
from PlatformCrawler.dataloader.cleaner import clean_records  # noqa: E402
from StanceProfiler.profiler import profile_d_platform  # noqa: E402
from multiagent.master import run_master  # noqa: E402

TZ = ZoneInfo("Asia/Shanghai")
csv.field_size_limit(20 * 1024 * 1024)

PLATFORM_ALIASES = {
    "bili": "bilibili",
    "bilibili": "bilibili",
    "weibo": "weibo",
    "xhs": "xiaohongshu",
    "xiaohongshu": "xiaohongshu",
}

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

MEMBER_RE = re.compile(
    r"^sentiment_records_(?P<domain>.+)_(?P<platform>bili|bilibili|weibo|xhs|xiaohongshu)_"
    r"(?P<scope>broad|hot)(?:_(?P<hot_topic>.+))?\.csv$",
    re.IGNORECASE,
)

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


def _mojibake_score(value: str) -> int:
    suspicious = "��������锟斤拷"
    return sum(value.count(char) for char in suspicious)


def repair_zip_name(info: zipfile.ZipInfo) -> str:
    """恢复 ZIP 文件名并统一为 NFC。

    UTF-8 flag（bit 11）存在时，Python 已正确解码；没有标志时才尝试将
    CP437 中间态恢复为 UTF-8 或 GB18030，并选择乱码特征最少的候选。
    """
    original = info.filename.replace("\\", "/")
    if info.flag_bits & 0x800:
        return unicodedata.normalize("NFC", original)
    candidates = [original]
    try:
        raw = original.encode("cp437")
    except UnicodeEncodeError:
        raw = b""
    for encoding in ("utf-8", "gb18030"):
        if not raw:
            continue
        try:
            candidates.append(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    best = min(candidates, key=lambda value: (_mojibake_score(value), -len(value)))
    return unicodedata.normalize("NFC", best)


def _safe_basename(member_name: str) -> str:
    path = PurePosixPath(member_name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"ZIP 成员路径不安全：{member_name!r}")
    name = path.name
    if not name:
        raise ValueError(f"ZIP 成员缺少文件名：{member_name!r}")
    return name


def parse_member(info: zipfile.ZipInfo, expected_platform: str) -> dict[str, str] | None:
    if info.is_dir():
        return None
    decoded = repair_zip_name(info)
    basename = _safe_basename(decoded)
    match = MEMBER_RE.match(basename)
    if not match:
        raise ValueError(f"无法识别 CSV 文件名：{decoded}")
    data = {key: str(value or "") for key, value in match.groupdict().items()}
    platform = PLATFORM_ALIASES.get(data["platform"].lower())
    if platform != expected_platform:
        raise ValueError(
            f"文件名平台 {platform!r} 与参数平台 {expected_platform!r} 不一致：{decoded}"
        )
    domain = data["domain"].lower()
    if domain not in DOMAIN_NAMES:
        raise ValueError(f"未知领域编码 {domain!r}：{decoded}")
    hot_topic = unicodedata.normalize("NFC", data["hot_topic"].strip())
    if data["scope"] == "hot" and not hot_topic:
        raise ValueError(f"hot 文件缺少具体话题：{decoded}")
    return {
        "decoded_member": decoded,
        "basename": basename,
        "platform": platform,
        "domain": domain,
        "domain_name": DOMAIN_NAMES[domain],
        "scope": data["scope"].lower(),
        "hot_topic": hot_topic,
        "topic": hot_topic or DOMAIN_NAMES[domain],
    }


def _safe_filename(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]+', "_", unicodedata.normalize("NFC", value))
    return value.strip(" .") or "unnamed"


def _extract_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    target: Path,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with archive.open(info, "r") as source, target.open("wb") as output:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)
            digest.update(chunk)
    return digest.hexdigest()


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
        "source_url": None,
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


def load_csv_records(
    csv_path: Path,
    *,
    platform: str,
    file_meta: dict[str, str],
    sample: int = 0,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    raw_rows = 0
    invalid_rows = 0
    source_key = f"{platform}/{csv_path.name}"
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - columns)
        if missing:
            raise ValueError(f"{csv_path.name} 缺少字段：{missing}")
        for row_number, row in enumerate(reader, start=2):
            raw_rows += 1
            record = _to_raw_record(
                row,
                platform=platform,
                source_key=source_key,
                row_number=row_number,
                file_meta=file_meta,
            )
            if not record["text"] or len(record["ts_raw"]) < 10:
                invalid_rows += 1
                continue
            records.append(record)
    if sample > 0 and len(records) > sample:
        records = random.Random(seed).sample(records, sample)
    return records, {
        "raw_rows": raw_rows,
        "mapped_rows": len(records),
        "mapping_invalid_rows": invalid_rows,
        "columns": sorted(columns),
    }


def _time_range(records: list[dict[str, Any]]) -> tuple[str, str]:
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


def analyze_file(
    csv_path: Path,
    file_meta: dict[str, str],
    *,
    granularity: str,
    sample: int,
    seed: int,
    text_tower: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    records, load_stats = load_csv_records(
        csv_path,
        platform=file_meta["platform"],
        file_meta=file_meta,
        sample=sample,
        seed=seed,
    )
    if not records:
        raise ValueError(f"{csv_path.name} 没有有效记录")
    since, until = _time_range(records)
    start = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=TZ)
    end = datetime.strptime(until, "%Y-%m-%d").replace(tzinfo=TZ)
    bundle = clean_records(
        records,
        time_range=(start, end),
        platform=file_meta["platform"],
    )
    d_platform = build_d_platform(
        bundle,
        keyword=file_meta["topic"],
        time_range=(since, until),
        granularity=granularity,
        platform=file_meta["platform"],
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
        "platform": file_meta["platform"],
        "keyword": file_meta["topic"],
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
            "raw_csv": str(csv_path.resolve().relative_to(AGENT_DIR)),
            "domain": file_meta["domain"],
            "domain_name": file_meta["domain_name"],
            "scope": file_meta["scope"],
            "hot_topic": file_meta["hot_topic"],
        },
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
    }
    summary = {
        **load_stats,
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


def _parse_archive(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("--archive 格式必须为 platform=zip_path")
    platform_raw, path_raw = value.split("=", 1)
    platform = PLATFORM_ALIASES.get(platform_raw.strip().lower())
    if not platform:
        raise argparse.ArgumentTypeError(f"不支持的平台：{platform_raw}")
    path = Path(path_raw.strip().strip('"'))
    if not path.exists():
        raise argparse.ArgumentTypeError(f"ZIP 不存在：{path}")
    return platform, path


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="真实多平台清洗 ZIP 接入")
    parser.add_argument(
        "--archive",
        action="append",
        type=_parse_archive,
        required=True,
        help="可重复：bilibili=path.zip / weibo=path.zip / xiaohongshu=path.zip",
    )
    parser.add_argument("--granularity", choices=["hour", "day"], default="day")
    parser.add_argument("--sample", type=int, default=0, help="每个 CSV 采样上限，0=全量")
    parser.add_argument("--max-files", type=int, default=0, help="最多处理文件数，0=全部")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--text-tower", action="store_true", help="启用 Skill3 文本塔")
    parser.add_argument(
        "--out-dir",
        default="dataset/real_multiplatform",
        help="相对 agent/ 的输出目录",
    )
    args = parser.parse_args(argv)

    output_dir = AGENT_DIR / args.out_dir
    raw_dir = output_dir / "raw"
    reports_dir = output_dir / "reports"
    fusion_dir = output_dir / "fusion"
    manifest: dict[str, Any] = {
        "schema_version": "real_multiplatform_manifest_v1",
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "archives": [],
        "files": [],
        "summary": {},
    }
    grouped_reports: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    processed = 0

    for platform, archive_path in args.archive:
        archive_entry = {
            "platform": platform,
            "path": str(archive_path.resolve()),
            "size_bytes": archive_path.stat().st_size,
        }
        manifest["archives"].append(archive_entry)
        print(f"==> {platform}: {archive_path}")
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                file_meta = parse_member(info, platform)
                if file_meta is None:
                    continue
                if args.max_files > 0 and processed >= args.max_files:
                    break
                target_name = _safe_filename(
                    f"{file_meta['domain']}__{file_meta['scope']}"
                    + (f"__{file_meta['hot_topic']}" if file_meta["hot_topic"] else "")
                    + ".csv"
                )
                target = raw_dir / platform / target_name
                sha256 = _extract_member(archive, info, target)
                report, stats = analyze_file(
                    target,
                    file_meta,
                    granularity=args.granularity,
                    sample=args.sample,
                    seed=args.seed,
                    text_tower=args.text_tower,
                )
                report_path = reports_dir / platform / (
                    f"{file_meta['domain']}__{file_meta['scope']}.json"
                )
                _write_json(report_path, report)
                group_key = (file_meta["scope"], file_meta["topic"])
                grouped_reports[group_key].append(report)
                file_entry = {
                    **file_meta,
                    "archive": str(archive_path.resolve()),
                    "archive_member": info.filename,
                    "utf8_flag": bool(info.flag_bits & 0x800),
                    "extracted_csv": str(target.relative_to(AGENT_DIR)),
                    "report": str(report_path.relative_to(AGENT_DIR)),
                    "sha256": sha256,
                    "uncompressed_bytes": info.file_size,
                    **stats,
                }
                manifest["files"].append(file_entry)
                processed += 1
                print(
                    f"    [{processed:02d}] {file_meta['scope']} / {file_meta['topic']} / "
                    f"rows={stats['raw_rows']} -> n_text={stats['n_text']} / "
                    f"risk={stats['max_severity']}"
                )
                _write_json(output_dir / "manifest.json", manifest)
            if args.max_files > 0 and processed >= args.max_files:
                break

    fusion_index: list[dict[str, Any]] = []
    for (scope, topic), reports in sorted(grouped_reports.items()):
        if len(reports) < 2:
            continue
        result = run_master(reports, use_llm=False)
        domain = str((reports[0].get("source") or {}).get("domain") or "unknown")
        fusion_path = fusion_dir / f"{domain}__{scope}.json"
        _write_json(fusion_path, result)
        fusion_index.append(
            {
                "scope": scope,
                "topic": topic,
                "platforms": [report["platform"] for report in reports],
                "file": str(fusion_path.relative_to(AGENT_DIR)),
                "CT_status": result.get("CT_status"),
                "echo_chamber_score": (result.get("echo_chamber") or {}).get("score"),
            }
        )

    platform_counts = Counter(item["platform"] for item in manifest["files"])
    manifest["summary"] = {
        "platforms": sorted(platform_counts),
        "files_per_platform": dict(platform_counts),
        "n_csv": len(manifest["files"]),
        "raw_rows": sum(int(item.get("raw_rows") or 0) for item in manifest["files"]),
        "n_text": sum(int(item.get("n_text") or 0) for item in manifest["files"]),
        "n_cross_platform_fusions": len(fusion_index),
        "sample_per_file": args.sample,
        "text_tower_enabled": args.text_tower,
    }
    manifest["fusion_index"] = fusion_index
    manifest["generated_at"] = datetime.now(TZ).isoformat(timespec="seconds")
    _write_json(output_dir / "manifest.json", manifest)
    _write_json(fusion_dir / "index.json", fusion_index)

    print("\n==> 接入完成")
    print(json.dumps(manifest["summary"], ensure_ascii=False, indent=2))
    print(f"manifest: {output_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
