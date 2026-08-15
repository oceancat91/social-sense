"""
StanceProfiler 命令行入口

用法：
  python -m StanceProfiler.pipeline --in PlatformCrawler/outputs/D_platform_xxx.json --out out.json
  python -m StanceProfiler.pipeline --in ... --to-dataset --event-title "事件名"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from StanceProfiler.archive import archive_event
from StanceProfiler.profiler import profile_d_platform


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="StanceProfiler：刷新 D_platform 立场画像")
    p.add_argument("--in", dest="inp", required=True, help="输入 D_platform.json")
    p.add_argument("--out", default=None, help="输出刷新后的 D_platform.json")
    p.add_argument("--profile-out", default=None, help="输出 stance_profile.json")
    p.add_argument("--dry-run", action="store_true", help="只打印摘要，不写文件")
    p.add_argument(
        "--to-dataset",
        action="store_true",
        help="归档到 dataset/events/<event_id>/（含 meta / D_platform / stance_profile）",
    )
    p.add_argument("--event-id", default=None, help="自定义 event_id")
    p.add_argument("--event-title", default=None, help="事件可读标题")
    p.add_argument("--description", default="", help="事件说明")
    p.add_argument("--source-notes", default="", help="来源备注")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    inp = Path(args.inp)
    if not inp.exists():
        raise SystemExit(f"找不到输入文件：{inp}")

    with inp.open("r", encoding="utf-8") as f:
        d_platform = json.load(f)

    d_out, profile = profile_d_platform(d_platform)

    summary = {
        "keyword": d_out["D_meta"].get("keyword"),
        "n_text": d_out["D_meta"].get("n_text"),
        "stance_global": d_out["D_meta"].get("stance_global"),
        "bias_score": d_out["D_meta"].get("bias_score"),
        "confidence": d_out["D_meta"].get("confidence"),
        "stance_provisional": (d_out["D_meta"].get("ext") or {}).get("stance_provisional"),
        "labeler": profile.get("labeler"),
        "stance_ratios": profile.get("stance_ratios"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.dry_run:
        return

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(d_out, f, ensure_ascii=False, indent=2)
        print(f"D_platform saved: {out_path}")

    if args.profile_out:
        po = Path(args.profile_out)
        po.parent.mkdir(parents=True, exist_ok=True)
        with po.open("w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"stance_profile saved: {po}")

    if args.to_dataset:
        event_dir = archive_event(
            d_out,
            profile,
            event_title=args.event_title,
            description=args.description,
            source_notes=args.source_notes,
            event_id=args.event_id,
        )
        print(f"archived to dataset: {event_dir}")

    if not args.out and not args.profile_out and not args.to_dataset:
        # 默认写到 StanceProfiler/outputs
        out_dir = Path(__file__).resolve().parent / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = inp.stem + "_stanced"
        out_path = out_dir / f"{stem}.json"
        profile_path = out_dir / f"{stem}_profile.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(d_out, f, ensure_ascii=False, indent=2)
        with profile_path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)
        print(f"D_platform saved: {out_path}")
        print(f"stance_profile saved: {profile_path}")


if __name__ == "__main__":
    main()
