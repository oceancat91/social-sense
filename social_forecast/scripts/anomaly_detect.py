"""Anomaly detection + event attribution on aggregated social data.

Method: robust rolling z-score (median + MAD) on log1p-transformed
engagement series.  MAD is robust to the sparse/spiky nature of OT and to
the collection bias, unlike mean/std z-score.

Inputs:
  data/social/SocialMedia_daily_2023plus.csv
  data/social/SocialMedia_<platform>_daily.csv  (for attribution)

Outputs:
  data/social/anomalies.csv
  data/social/figures/*_anomaly.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOCIAL = ROOT / "data" / "social"
FIG_DIR = SOCIAL / "figures"

plt.rcParams["axes.unicode_minus"] = False
for font in ("Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"):
    try:
        plt.rcParams["font.sans-serif"] = [font]
        break
    except Exception:
        pass

# (series column, display name, color) — all log1p'd for detection
METRICS = [
    ("OT", "OT (posts)", "#1f77b4"),
    ("like_sum", "likes", "#d62728"),
    ("view_sum", "views", "#ff7f0e"),
]

MAD_SCALE = 0.6744897501960817  # 1 / Phi^{-1}(0.75)


def robust_zscore(s: pd.Series, window: int = 30, min_periods: int = 10) -> pd.Series:
    """Rolling median + MAD z-score. NaN → 0 (not enough history)."""
    med = s.rolling(window, min_periods=min_periods).median()
    mad = (s - med).abs().rolling(window, min_periods=min_periods).median()
    z = MAD_SCALE * (s - med) / (mad + 1e-6)
    return z.fillna(0.0)


def detect_regime_change(ot_log: np.ndarray) -> dict | None:
    """PELT L2 level-shift 检测（复用 layers.jump_pelt，纯 numpy）。

    MAD 只抓「单日尖峰」，抓不住「持续 level 跃迁」（regime change）。
    这里用 PELT 把 log1p(OT) 切成平稳段，把变点处的 level-shift 幅度
    归一化成与 spike z 同量级的 ``z_regime``，作为异常检测的第二维度。

    返回 dict(z_regime, is_regime_change, regime_amp, n_bps, n_events)；
    若 PELT 不可用则返回 None（优雅降级）。
    """
    try:
        from layers.jump_pelt import detect_jumps, _noise_sigma
    except Exception as e:  # noqa: BLE001
        print(f"[anomaly] PELT 不可用，跳过 regime 维度: {e}")
        return None

    x = np.asarray(ot_log, dtype=np.float64).reshape(-1)
    n = x.size
    z_regime = np.zeros(n, dtype=np.float64)
    is_regime = np.zeros(n, dtype=bool)
    regime_amp = np.zeros(n, dtype=np.float64)

    C, bps, events = detect_jumps(x)
    sigma = float(_noise_sigma(x))
    for e in events:
        s = int(e["start"])
        if 0 <= s < n:
            a = float(e["amp"])
            z = abs(a) / (sigma + 1e-8)
            is_regime[s] = True
            if z > z_regime[s]:
                z_regime[s] = z
                regime_amp[s] = a
    return {
        "z_regime": z_regime,
        "is_regime_change": is_regime,
        "regime_amp": regime_amp,
        "n_bps": len(bps),
        "n_events": len(events),
    }


def load_platform_series() -> pd.DataFrame:
    """Wide dataframe: date -> platform post counts (aligned, zero-filled)."""
    dfs = []
    for plat in ("bilibili", "douyin", "kuaishou", "weibo", "xhs"):
        p = SOCIAL / f"SocialMedia_{plat}_daily.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, usecols=["date", "OT"])
        df = df.rename(columns={"OT": plat})
        dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    out = dfs[0]
    for df in dfs[1:]:
        out = out.merge(df, on="date", how="outer")
    out = out.fillna(0)
    for c in out.columns:
        if c != "date":
            out[c] = out[c].astype(int)
    return out


def detect(
    daily: pd.DataFrame,
    window: int = 30,
    threshold: float = 3.5,
) -> pd.DataFrame:
    df = daily.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    # log1p transform for detection (handles sparse + heavy tail)
    zcols = []
    for col, _name, _c in METRICS:
        s = np.log1p(pd.to_numeric(df[col], errors="coerce").fillna(0))
        z = robust_zscore(s, window=window)
        df[f"z_{col}"] = z
        zcols.append(f"z_{col}")

    # spike score = max over metrics (any metric spiking → event)
    df["z_spike"] = df[zcols].max(axis=1)

    # PELT regime-change（level shift）维度：补 MAD 抓不住持续 level 跃迁的盲区
    ot_log = np.log1p(pd.to_numeric(df["OT"], errors="coerce").fillna(0)).values
    reg = detect_regime_change(ot_log)
    if reg is not None:
        df["z_regime"] = reg["z_regime"]
        df["is_regime_change"] = reg["is_regime_change"]
        df["regime_amp"] = reg["regime_amp"]
        print(f"[anomaly] PELT regime 检测：{reg['n_bps']} 变点 / "
              f"{reg['n_events']} 有效事件")
    else:
        df["z_regime"] = 0.0
        df["is_regime_change"] = False
        df["regime_amp"] = 0.0

    # unified anomaly score = max(spike, regime)，下游统一按 z_max 排序
    df["z_max"] = df[["z_spike", "z_regime"]].max(axis=1)
    df["is_anomaly"] = df["z_max"] > threshold

    # 来源标注：spike / regime / both
    df["anomaly_source"] = np.where(
        (df["z_spike"] > threshold) & (df["z_regime"] > threshold), "both",
        np.where(df["z_spike"] > threshold, "spike",
                 np.where(df["z_regime"] > threshold, "regime", "")))

    # top triggering metric（regime 主导时标 regime）
    df["trigger_metric"] = df[zcols].idxmax(axis=1).str.replace("z_", "")
    regime_win = df["z_regime"] > df["z_spike"]
    df.loc[regime_win, "trigger_metric"] = "regime"

    # attribution: platform shares on that day
    plat = load_platform_series()
    if not plat.empty:
        # normalize merge key to string
        plat["date"] = plat["date"].astype(str)
        df["date_str"] = df["date"].dt.strftime("%Y-%m-%d")
        df = df.merge(plat, left_on="date_str", right_on="date", how="left", suffixes=("", "_p"))
        df = df.drop(columns=["date_p"], errors="ignore")
        for c in plat.columns:
            if c != "date":
                df[c] = df[c].fillna(0).astype(int)

    return df


def report(df: pd.DataFrame, top_n: int = 15):
    anoms = df[df["is_anomaly"]].copy()
    print(f"\n[anomaly] {len(anoms)} anomalous days "
          f"out of {len(df)} ({len(anoms)/len(df):.1%})")
    if anoms.empty:
        return
    src = anoms["anomaly_source"].value_counts().to_dict()
    print(f"[anomaly] 来源分布: spike={src.get('spike', 0)} "
          f"regime={src.get('regime', 0)} both={src.get('both', 0)}")
    anoms = anoms.sort_values("z_max", ascending=False)
    print(f"\n=== top {min(top_n, len(anoms))} events by z_max ===")
    for _, r in anoms.head(top_n).iterrows():
        plat_share = ""
        for p in ("bilibili", "douyin", "kuaishou", "weibo", "xhs"):
            if p in r.index:
                v = int(r[p])
                if v > 0:
                    plat_share += f" {p}={v}"
        fact = str(r.get("fact", ""))[:90].replace("\n", " ")
        print(
            f"{r['date'].strftime('%Y-%m-%d')}  "
            f"z={r['z_max']:.1f}  trig={r['trigger_metric']}"
            f"[{r.get('anomaly_source', '')}]  "
            f"OT={int(r['OT'])}  likes={int(r['like_sum']):,}  "
            f"views={int(r['view_sum']):,}"
        )
        if plat_share:
            print(f"    platforms:{plat_share}")
        if fact:
            print(f"    fact: {fact}")


def plot(df: pd.DataFrame, threshold: float):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    d = df.copy()
    anoms = d[d["is_anomaly"]]

    fig, axes = plt.subplots(3, 1, figsize=(15, 9), sharex=True)
    for ax, (col, name, color) in zip(axes, METRICS):
        ax.plot(d["date"], np.log1p(d[col]), color=color, lw=0.9, label=name)
        ax.scatter(
            anoms["date"], np.log1p(anoms[col]),
            color="black", s=35, zorder=5, marker="x", label="anomaly",
        )
        ax.set_ylabel(f"log1p({col})")
        ax.set_title(name)
        ax.grid(True, alpha=0.3)
        ax.legend(loc="upper right", fontsize=8)
    axes[-1].set_xlabel("date")
    fig.suptitle(f"Anomaly detection (robust z > {threshold})", y=0.995)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "08_anomaly_detection.png", dpi=150)
    plt.close(fig)

    # z-score panel（spike z 与 regime z 叠加）
    fig, ax = plt.subplots(figsize=(15, 4))
    ax.plot(d["date"], d["z_spike"], color="#666666", lw=0.6, label="z_spike (MAD)")
    ax.plot(d["date"], d["z_regime"], color="#2f5d8c", lw=0.6, label="z_regime (PELT)")
    ax.plot(d["date"], d["z_max"], color="#333333", lw=0.9, label="z_max (unified)")
    ax.axhline(threshold, color="red", ls="--", lw=1, label=f"threshold {threshold}")
    reg = d[d["is_regime_change"]]
    if len(reg):
        ax.scatter(reg["date"], reg["z_regime"], color="#c45c26", s=40,
                   zorder=5, marker="^", label="regime change")
    ax.set_ylabel("z score")
    ax.set_title("Combined anomaly score (spike + regime)")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "09_anomaly_score.png", dpi=150)
    plt.close(fig)

    # monthly anomaly count (2023+)
    if len(anoms):
        tmp = anoms.copy()
        tmp["month"] = tmp["date"].dt.to_period("M").astype(str)
        cnt = tmp.groupby("month").size()
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.bar(cnt.index, cnt.values, color="#e377c2")
        ax.set_ylabel("anomalous days")
        ax.set_title("Anomalous days per month (2023+)")
        ax.tick_params(axis="x", rotation=45)
        fig.tight_layout()
        fig.savefig(FIG_DIR / "10_anomaly_monthly.png", dpi=150)
        plt.close(fig)


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=Path,
                    default=SOCIAL / "SocialMedia_daily_2023plus.csv")
    ap.add_argument("--window", type=int, default=30)
    ap.add_argument("--threshold", type=float, default=3.5)
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()

    daily = pd.read_csv(args.csv)
    print(f"[anomaly] loaded {args.csv}  n={len(daily)}")

    df = detect(daily, window=args.window, threshold=args.threshold)

    out_csv = SOCIAL / "anomalies.csv"
    df.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"[anomaly] wrote {out_csv}")

    report(df, top_n=args.top)
    plot(df, threshold=args.threshold)
    print(f"[viz] figures → {FIG_DIR}")


if __name__ == "__main__":
    main()
