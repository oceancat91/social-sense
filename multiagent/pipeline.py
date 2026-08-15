"""
多平台多 Agent 主控流水线 CLI。

用法：
  python -m multiagent --reports bilibili_report.json weibo_report.json [--out out.json] [--no-llm]
  python -m multiagent --reports-dir path/to/reports/ [--out out.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .master import run_master


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _collect(paths: list[str], reports_dir: str | None) -> list[dict[str, Any]]:
    reports: list[dict[str, Any]] = []
    for p in paths:
        reports.append(_load_json(p))
    if reports_dir:
        d = Path(reports_dir)
        for f in sorted(d.glob("*.json")):
            reports.append(_load_json(f))
    return reports


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="多平台多 Agent 主控：对齐→融合→归纳")
    p.add_argument("--reports", nargs="*", default=[], help="各平台报告 JSON（可多个）")
    p.add_argument("--reports-dir", default=None, help="报告目录（读全部 *.json）")
    p.add_argument("--out", default=None, help="输出文件")
    p.add_argument("--no-llm", action="store_true", help="禁用 LLM，纯确定性归纳")
    args = p.parse_args(argv)

    reports = _collect(args.reports, args.reports_dir)
    if not reports:
        raise SystemExit("未提供任何平台报告（--reports 或 --reports-dir）")

    ct = run_master(reports, use_llm=not args.no_llm)

    print(
        json.dumps(
            {
                "CT_status": ct["CT_status"],
                "scope": ct["scope"],
                "platforms": ct["platforms"],
                "echo_chamber_score": ct["echo_chamber"]["score"],
                "stance_divergence": ct["fusion"].get("stance_divergence"),
                "sentiment_divergence": ct["fusion"].get("sentiment_divergence"),
                "summary": ct["summary"],
                "risk_flags": ct["risk_flags"],
                "llm_used": ct["llm_used"],
                "calibration": ct["calibration"]["all_pass"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            json.dump(ct, f, ensure_ascii=False, indent=2)
        print(f"saved: {out}")


if __name__ == "__main__":
    main()
