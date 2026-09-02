"""
Skill3 命令行入口：

  python -m MultimodalAnalyzer --in path/to/D_platform.json [--out path/to/skill3.json] [--tau 3.0]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from MultimodalAnalyzer.analyzer import AnalyzerConfig, run_analysis

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="MultimodalAnalyzer：多模态时序文本异常分析")
    p.add_argument("--in", dest="inp", required=True, help="输入 D_platform.json")
    p.add_argument("--out", default=None, help="输出 skill3 结果 JSON")
    p.add_argument("--tau", type=float, default=3.0, help="异常 z 阈值")
    p.add_argument("--tau-cross-scale", type=float, default=2.5, help="跨尺度残差跨度阈值")
    p.add_argument("--scale-windows", default=None, help="多尺度窗口，如 3,7,15")
    p.add_argument("--no-multiscale", action="store_true", help="关闭跨尺度检测")
    p.add_argument("--no-text", action="store_true", help="关闭文本塔")
    p.add_argument("--dry-run", action="store_true", help="只打印摘要")
    args = p.parse_args(argv)

    inp = Path(args.inp)
    if not inp.exists():
        raise SystemExit(f"找不到输入文件：{inp}")
    with inp.open("r", encoding="utf-8") as f:
        d_platform = json.load(f)

    scale_windows = None
    if args.scale_windows:
        try:
            scale_windows = tuple(
                int(value.strip())
                for value in str(args.scale_windows).split(",")
                if value.strip()
            )
        except ValueError as exc:
            raise SystemExit("--scale-windows 必须是逗号分隔的整数") from exc
    cfg = AnalyzerConfig(
        tau=args.tau,
        tau_cross_scale=args.tau_cross_scale,
        multiscale_windows=scale_windows,
        enable_multiscale=not args.no_multiscale,
        enable_text_tower=not args.no_text,
    )
    result = run_analysis(d_platform, cfg, out_dir=OUTPUT_DIR)

    summary = {
        "status": result["status"],
        "n_anomalies": len(result["anomalies"]),
        "need_recrawl": result["need_recrawl"],
        "recrawl_windows": result["recrawl_windows"],
        "model_version": result["model_version"],
        "anomalies": result["anomalies"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    if args.dry_run:
        return

    out = Path(args.out) if args.out else OUTPUT_DIR / f"skill3_{inp.stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"skill3 saved: {out}")


if __name__ == "__main__":
    main()
