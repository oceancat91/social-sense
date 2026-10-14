"""Aggregate social-media posts into model-ready daily time series + facts.

Reads:
  dataset_unzipped/数据集/cleaned/all_cleaned.csv

Writes:
  data/social/SocialMedia_daily.csv          # all platforms, daily
  data/social/SocialMedia_<platform>_daily.csv
  data/social/SocialMedia_daily_2023plus.csv # denser recent window
  data/social/figures/*.png

Schema (compatible with test_dssaa_forecast.load_pack):
  date, Date, OT, fact, n_posts, like_sum, comment_sum, share_sum, view_sum
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "dataset_unzipped" / "数据集" / "cleaned" / "all_cleaned.csv"
OUT_DIR = ROOT / "data" / "social"
FIG_DIR = OUT_DIR / "figures"

# matplotlib: prefer fonts that cover CJK if present
plt.rcParams["axes.unicode_minus"] = False
for font in ("Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"):
    try:
        plt.rcParams["font.sans-serif"] = [font]
        break
    except Exception:
        pass


def _clean_text(s: str, max_chars: int = 120) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    if len(s) > max_chars:
        s = s[: max_chars - 1] + "…"
    return s


def _build_fact(group: pd.DataFrame, day: pd.Timestamp, top_k: int = 5) -> str:
    """Pick top-k liked posts of the day → 'YYYY-MM-DD: text; ...'."""
    g = group.sort_values("like_count", ascending=False)
    parts = []
    seen = set()
    for _, row in g.iterrows():
        t = _clean_text(row["text"])
        if not t or t in seen:
            continue
        seen.add(t)
        parts.append(f"{day.strftime('%Y-%m-%d')}: {t}")
        if len(parts) >= top_k:
            break
    return "; ".join(parts)


def aggregate_daily(
    df: pd.DataFrame,
    top_k: int = 5,
    platform: str | None = None,
) -> pd.DataFrame:
    work = df if platform is None else df[df["platform"] == platform].copy()
    if work.empty:
        return pd.DataFrame()

    work = work.dropna(subset=["day"]).copy()
    rows = []
    for day, g in work.groupby("day", sort=True):
        rows.append(
            {
                "date": day.strftime("%Y-%m-%d"),
                "Date": day.strftime("%Y-%m-%d"),
                "OT": float(len(g)),  # primary target: daily post volume
                "n_posts": int(len(g)),
                "like_sum": int(g["like_count"].fillna(0).sum()),
                "comment_sum": int(g["comment_count"].fillna(0).sum()),
                "share_sum": int(g["share_count"].fillna(0).sum()),
                "view_sum": int(g["view_count"].fillna(0).sum()),
                "fact": _build_fact(g, day, top_k=top_k),
            }
        )
    out = pd.DataFrame(rows)
    # fill calendar gaps with zeros (keeps regular time series)
    if not out.empty:
        full_idx = pd.date_range(out["date"].iloc[0], out["date"].iloc[-1], freq="D")
        out["date"] = pd.to_datetime(out["date"])
        out = out.set_index("date").reindex(full_idx)
        out.index.name = "date"
        for c in ("OT", "n_posts", "like_sum", "comment_sum", "share_sum", "view_sum"):
            out[c] = out[c].fillna(0)
        out["fact"] = out["fact"].fillna("")
        out["Date"] = out.index.strftime("%Y-%m-%d")
        out = out.reset_index().rename(columns={"index": "date"})
        out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out


def plot_overview(daily: pd.DataFrame, by_plat: dict[str, pd.DataFrame], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    d = daily.copy()
    d["date"] = pd.to_datetime(d["date"])

    # 1) OT (post volume) + likes
    fig, axes = plt.subplots(2, 1, figsize=(14, 7), sharex=True)
    axes[0].plot(d["date"], d["OT"], color="#1f77b4", lw=0.8)
    axes[0].set_ylabel("OT = daily posts")
    axes[0].set_title("SocialMedia daily volume (all platforms)")
    axes[0].grid(True, alpha=0.3)
    axes[1].plot(d["date"], d["like_sum"], color="#d62728", lw=0.8)
    axes[1].set_ylabel("like_sum")
    axes[1].set_xlabel("date")
    axes[1].grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "01_ot_and_likes.png", dpi=150)
    plt.close(fig)

    # 2) log1p OT (see structure without 2026 spike dominating)
    fig, ax = plt.subplots(figsize=(14, 4))
    ax.plot(d["date"], np.log1p(d["OT"]), color="#2ca02c", lw=0.9)
    ax.set_ylabel("log1p(OT)")
    ax.set_title("log1p daily posts")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "02_log_ot.png", dpi=150)
    plt.close(fig)

    # 3) per-platform stacked / overlay (recent if long)
    fig, ax = plt.subplots(figsize=(14, 5))
    for name, pdf in by_plat.items():
        if pdf.empty:
            continue
        p = pdf.copy()
        p["date"] = pd.to_datetime(p["date"])
        ax.plot(p["date"], np.log1p(p["OT"]), lw=0.8, label=name, alpha=0.85)
    ax.set_ylabel("log1p(OT)")
    ax.set_title("Per-platform daily posts (log1p)")
    ax.legend(ncol=5, fontsize=8)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(out_dir / "03_platform_log_ot.png", dpi=150)
    plt.close(fig)

    # 4) yearly totals
    d["year"] = d["date"].dt.year
    yearly = d.groupby("year")["OT"].sum()
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar(yearly.index.astype(str), yearly.values, color="#9467bd")
    ax.set_ylabel("total posts")
    ax.set_title("Posts per year")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(out_dir / "04_yearly_posts.png", dpi=150)
    plt.close(fig)

    # 5) 2023+ zoom (model-friendly window)
    recent = d[d["date"] >= "2023-01-01"]
    if len(recent) > 10:
        fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
        axes[0].plot(recent["date"], recent["OT"], color="#1f77b4", lw=0.9)
        axes[0].set_ylabel("OT")
        axes[0].set_title("2023+ daily OT / likes / views")
        axes[0].grid(True, alpha=0.3)
        axes[1].plot(recent["date"], recent["like_sum"], color="#d62728", lw=0.9)
        axes[1].set_ylabel("likes")
        axes[1].grid(True, alpha=0.3)
        axes[2].plot(recent["date"], recent["view_sum"], color="#ff7f0e", lw=0.9)
        axes[2].set_ylabel("views")
        axes[2].set_xlabel("date")
        axes[2].grid(True, alpha=0.3)
        fig.tight_layout()
        fig.savefig(out_dir / "05_recent_2023plus.png", dpi=150)
        plt.close(fig)

    # 6) weekday pattern (2023+)
    if len(recent) > 10:
        tmp = recent.copy()
        tmp["weekday"] = tmp["date"].dt.dayofweek
        means = tmp.groupby("weekday")["OT"].mean()
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            means.reindex(range(7)).values,
            color="#17becf",
        )
        ax.set_ylabel("mean OT")
        ax.set_title("2023+ mean posts by weekday")
        fig.tight_layout()
        fig.savefig(out_dir / "06_weekday_pattern.png", dpi=150)
        plt.close(fig)

    # 7) fact coverage
    fact_ratio = (d["fact"].astype(str).str.len() > 0).mean()
    recent_ratio = (
        (recent["fact"].astype(str).str.len() > 0).mean() if len(recent) else 0.0
    )
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(["all days", "2023+"], [fact_ratio, recent_ratio], color=["#7f7f7f", "#1f77b4"])
    ax.set_ylim(0, 1)
    ax.set_ylabel("fraction of days with non-empty fact")
    ax.set_title("Text (fact) coverage after aggregation")
    for i, v in enumerate([fact_ratio, recent_ratio]):
        ax.text(i, v + 0.02, f"{v:.1%}", ha="center")
    fig.tight_layout()
    fig.savefig(out_dir / "07_fact_coverage.png", dpi=150)
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--top-k", type=int, default=5, help="top posts per day into fact")
    ap.add_argument("--start", type=str, default=None, help="optional YYYY-MM-DD filter")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[agg] reading {args.src}")
    usecols = [
        "platform",
        "publish_time",
        "text",
        "like_count",
        "comment_count",
        "share_count",
        "view_count",
    ]
    df = pd.read_csv(args.src, usecols=usecols, low_memory=False)
    df["dt"] = pd.to_datetime(df["publish_time"], errors="coerce", utc=True)
    df = df.dropna(subset=["dt"])
    # store calendar day in local China time for social data
    df["day"] = df["dt"].dt.tz_convert("Asia/Shanghai").dt.floor("D").dt.tz_localize(None)
    if args.start:
        df = df[df["day"] >= pd.Timestamp(args.start)]

    for c in ("like_count", "comment_count", "share_count", "view_count"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(np.int64)

    print(f"[agg] rows={len(df)} platforms={sorted(df['platform'].dropna().unique())}")

    # all platforms
    daily = aggregate_daily(df, top_k=args.top_k, platform=None)
    path_all = OUT_DIR / "SocialMedia_daily.csv"
    daily.to_csv(path_all, index=False, encoding="utf-8")
    print(f"[agg] wrote {path_all}  n={len(daily)}")

    # 2023+ denser window (better for forecasting demos)
    daily_recent = daily[daily["date"] >= "2023-01-01"].reset_index(drop=True)
    path_recent = OUT_DIR / "SocialMedia_daily_2023plus.csv"
    daily_recent.to_csv(path_recent, index=False, encoding="utf-8")
    print(f"[agg] wrote {path_recent}  n={len(daily_recent)}")

    # per platform
    by_plat = {}
    for plat in sorted(df["platform"].dropna().unique()):
        pdf = aggregate_daily(df, top_k=args.top_k, platform=plat)
        by_plat[plat] = pdf
        outp = OUT_DIR / f"SocialMedia_{plat}_daily.csv"
        pdf.to_csv(outp, index=False, encoding="utf-8")
        print(f"[agg] wrote {outp}  n={len(pdf)}")

    print("[viz] plotting …")
    plot_overview(daily, by_plat, FIG_DIR)
    print(f"[viz] figures → {FIG_DIR}")

    # short summary for terminal
    print("\n=== summary ===")
    print(
        daily[["OT", "like_sum", "view_sum"]]
        .describe()
        .round(2)
        .to_string()
    )
    print(
        f"fact non-empty days: "
        f"{(daily['fact'].str.len() > 0).sum()}/{len(daily)}"
    )
    print(
        f"2023+ days: {len(daily_recent)}, "
        f"OT mean={daily_recent['OT'].mean():.1f}, "
        f"OT max={daily_recent['OT'].max():.0f}"
    )


if __name__ == "__main__":
    main()
