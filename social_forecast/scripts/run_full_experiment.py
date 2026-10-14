"""Full experiment orchestrator (anomaly + text attribution + safe train).

Phases:
  A) anomaly detect (robust z, with text facts) → anomalies.csv
  B) export events with full text → results/events.jsonl
  C) LLM / template attribution report → data/social/report.md
  D) make log target (if missing)
  E) safe train on SocialMedia_log with anomaly-backed C library

GPU safety defaults (override via env):
  ABLATION_GPU_FRAC=0.40
  TEXT_CACHE_BS=1
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(cmd: list[str], env: dict | None = None):
    print("\n>>>", " ".join(cmd), flush=True)
    e = os.environ.copy()
    if env:
        e.update(env)
    r = subprocess.run(cmd, cwd=str(ROOT), env=e)
    if r.returncode != 0:
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(cmd)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-train", action="store_true",
                    help="only anomaly + text attribution (no GPU train)")
    ap.add_argument("--threshold", type=float, default=3.0,
                    help="anomaly z threshold (lower → more events)")
    ap.add_argument("--capacity", default="lite", choices=("lite", "base"))
    ap.add_argument("--template-llm", action="store_true",
                    help="force template report (skip Ollama)")
    args = ap.parse_args()

    # ---- GPU safety ----
    env = {
        "ABLATION_GPU_FRAC": os.environ.get("ABLATION_GPU_FRAC", "0.40"),
        "TEXT_CACHE_BS": os.environ.get("TEXT_CACHE_BS", "1"),
        "PYTORCH_ALLOC_CONF": "expandable_segments:True",
    }
    print(f"[exp] GPU frac={env['ABLATION_GPU_FRAC']}  TEXT_CACHE_BS={env['TEXT_CACHE_BS']}")

    # A) anomaly detect
    run([
        PY, "-u", "scripts/anomaly_detect.py",
        "--csv", "data/social/SocialMedia_daily_2023plus.csv",
        "--threshold", str(args.threshold),
        "--top", "30",
    ])

    # B) export events + text
    run([PY, "-u", "scripts/export_events.py"])

    # C) LLM / template report
    llm_cmd = [PY, "-u", "scripts/llm_reporter.py", "--top", "15"]
    if args.template_llm:
        llm_cmd.append("--template")
    run(llm_cmd)

    # D) log target
    if not (ROOT / "data" / "SocialMedia_log.csv").exists():
        run([PY, "-u", "scripts/make_log_target.py"])
    else:
        print("[exp] SocialMedia_log.csv exists — skip")

    if args.skip_train:
        print("\n[exp] --skip-train: done (anomaly + text attribution only)")
        return

    # E) safe train (anomaly BPs fill empty PELT library inside e2e)
    #    预测口径：方向命中率 + 尖峰预警（不拼 MSE）；L=28 让趋势头看更长历史。
    out = ROOT / "results" / f"SocialMedia_log_{args.capacity}_full.csv"
    run([
        PY, "-u", "test/test_event_response_e2e.py", "SocialMedia_log",
        "--pred_len", "6",
        "--calendar", "short",
        "--capacity", args.capacity,
        "--seq_len", "28",
        "--seasonal_period", "7",
        "--no_ctx",
        "--direction",
        "--out", str(out),
    ], env=env)

    print("\n[exp] ALL DONE")
    print(f"  events : results/events.jsonl")
    print(f"  report : data/social/report.md")
    print(f"  train  : {out}")
    print(f"  ckpt   : checkpoints/SocialMedia_log_{args.capacity}_pl6_L28.pt")
    print("  workflow: python -u scripts/run_workflow.py  (或 ../workflow/forecast_ai/run_workflow.py)")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
