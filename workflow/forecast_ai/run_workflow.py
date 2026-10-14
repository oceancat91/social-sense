#!/usr/bin/env python
"""一键入口：异常 → 预测 → LLM 归因。

在 social-sense 根目录或任意位置::

  python -u workflow/forecast_ai/run_workflow.py
  python -u workflow/forecast_ai/run_workflow.py --template-llm
  python -u workflow/forecast_ai/run_workflow.py --skip-anomaly --ckpt path/to.pt
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOCIAL_SENSE = HERE.parents[1]
if str(SOCIAL_SENSE) not in sys.path:
    sys.path.insert(0, str(SOCIAL_SENSE))


def main():
    ap = argparse.ArgumentParser(description="Forecast + AI attribution workflow")
    ap.add_argument("--ckpt", type=str, default="",
                    help="checkpoint .pt path (default: latest under social_forecast/checkpoints)")
    ap.add_argument("--out", type=str, default="",
                    help="workflow output dir")
    ap.add_argument("--threshold", type=float, default=3.0)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--pred-windows", type=int, default=5)
    ap.add_argument("--template-llm", action="store_true",
                    help="force template report (no DeepSeek call)")
    ap.add_argument("--skip-anomaly", action="store_true")
    ap.add_argument("--skip-forecast", action="store_true")
    ap.add_argument("--skip-llm", action="store_true")
    args = ap.parse_args()

    from workflow.forecast_ai.pipeline import ForecastAIWorkflow

    wf = ForecastAIWorkflow(
        checkpoint=Path(args.ckpt) if args.ckpt else None,
        out_dir=Path(args.out) if args.out else None,
        threshold=args.threshold,
        top_events=args.top,
        template_llm=args.template_llm,
        skip_anomaly=args.skip_anomaly,
        skip_forecast=args.skip_forecast,
        skip_llm=args.skip_llm,
        pred_windows=args.pred_windows,
    )
    result = wf.run()
    print("\n==== workflow done ====")
    print(f"ok={result.ok}")
    for k, v in result.artifacts.items():
        print(f"  {k}: {v}")
    if result.errors:
        print("errors:")
        for e in result.errors:
            print(" -", e[:500])
    if result.report_preview:
        print("\n----- report preview -----")
        print(result.report_preview[:1000])
    raise SystemExit(0 if result.ok else 1)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
