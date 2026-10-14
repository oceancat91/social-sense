"""Generate log1p target for the forecast model (architecture unchanged).

Reads:  data/SocialMedia.csv
Writes: data/SocialMedia_log.csv   (OT = log1p(raw OT), date/fact unchanged)

Why: raw OT is power-law with a 2026-08 spike cluster (max 25166 vs median 95),
so StandardScaler + MSE explode (persist MSE ≈ 2842).  log1p compresses the
range to [2.5, 10.1] and makes the multiplicative dynamics additive.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    src = ROOT / "data" / "SocialMedia.csv"
    dst = ROOT / "data" / "SocialMedia_log.csv"

    df = pd.read_csv(src)
    ot = pd.to_numeric(df["OT"], errors="coerce").fillna(0).astype(np.float64)
    df["OT"] = np.log1p(ot)

    df.to_csv(dst, index=False, encoding="utf-8")
    print(f"[log] wrote {dst}  n={len(df)}")
    print(f"[log] OT range now: [{df['OT'].min():.3f}, {df['OT'].max():.3f}]")
    print(f"[log] mean={df['OT'].mean():.3f}  std={df['OT'].std():.3f}  "
          f"skew={df['OT'].skew():.3f}")


if __name__ == "__main__":
    main()
