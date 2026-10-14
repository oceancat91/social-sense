"""Delegate to social-sense workflow.forecast_ai (keeps one entry from social_forecast/)."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT.parent / "workflow" / "forecast_ai" / "run_workflow.py"

if __name__ == "__main__":
    if not ENTRY.exists():
        raise SystemExit(f"missing workflow entry: {ENTRY}")
    sys.argv[0] = str(ENTRY)
    runpy.run_path(str(ENTRY), run_name="__main__")
