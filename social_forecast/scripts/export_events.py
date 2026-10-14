"""Export anomaly events with full text for attribution / LLM.

Reads:  data/social/anomalies.csv
Writes: results/events.jsonl
        results/events_table.csv
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
ANOM = ROOT / "data" / "social" / "anomalies.csv"
OUT_DIR = ROOT / "results"


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(ANOM)
    anoms = df[df["is_anomaly"] == True].sort_values("z_max", ascending=False)  # noqa: E712
    rows = []
    for _, r in anoms.iterrows():
        plats = {
            p: int(r[p]) for p in ("bilibili", "douyin", "kuaishou", "weibo", "xhs")
            if p in r.index and int(r[p]) > 0
        }
        rows.append({
            "date": str(r["date"])[:10],
            "z_max": float(r["z_max"]),
            "trigger_metric": str(r["trigger_metric"]),
            "anomaly_source": str(r.get("anomaly_source", "")),
            "z_regime": float(r.get("z_regime", 0.0)),
            "OT": float(r["OT"]),
            "like_sum": float(r["like_sum"]),
            "view_sum": float(r["view_sum"]),
            "platforms": plats,
            "fact": str(r.get("fact", "")),
        })

    jsonl = OUT_DIR / "events.jsonl"
    with jsonl.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    flat = []
    for row in rows:
        flat.append({
            **{k: row[k] for k in ("date", "z_max", "trigger_metric",
                                   "anomaly_source", "z_regime", "OT",
                                   "like_sum", "view_sum")},
            "platforms": json.dumps(row["platforms"], ensure_ascii=False),
            "fact": row["fact"],
        })
    csv_path = OUT_DIR / "events_table.csv"
    pd.DataFrame(flat).to_csv(csv_path, index=False, encoding="utf-8")
    print(f"[export] {len(rows)} events → {jsonl}")
    print(f"[export] table → {csv_path}")


if __name__ == "__main__":
    main()
