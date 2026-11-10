# -*- coding: utf-8 -*-
"""事件传播时序分析：用「博文 → 评论」的时间滞后刻画传播节奏。

为什么做这个而不是跨平台对照：
  数据集A（501K 条 / 5 平台）与政策事件的时间窗不重叠（B 是 2018-2022，
  A 主要 2023-2026），加时间窗过滤后命中降到 0-3 条，跨平台对照不可做。
  但政策舆情数据集自带「博文 + 评论」成对数据，这是同一份数据里真实存在的
  传播信号 —— 评论相对博文的滞后，就是信息从发布扩散到讨论的时间差。

能做的范围（不夸大）：只有上海落户、新冠两个事件同时具备博文与评论。
三孩 54,722 条全是评论、无对应博文；算法/个人信息/房地产税只有博文。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

B = Path(r"D:\HuaweiMoveData\Users\32002\Desktop\social-sense\tmp\datasetB\政策舆情研究数据集")
OUT = Path(r"D:\HuaweiMoveData\Users\32002\Desktop\social-sense\social_forecast\data\events\propagation")

CASES = {
    "shanghai_luohu": {
        "name": "上海非沪籍高校毕业生落户政策",
        "post": (B / "上海非沪籍高校毕业生落户相关政策的舆情数据" / "数据" / "博文数据.csv", "time"),
        "comment": (B / "上海非沪籍高校毕业生落户相关政策的舆情数据" / "数据" / "评论数据.csv", "time"),
    },
    "xinguan": {
        "name": "新冠疫情政策",
        "post": (B / "新冠疫情政策数据" / "blog_csv.csv", "发布时间"),
        "comment": (B / "新冠疫情政策数据" / "comments_csv.csv", "评论发布时间"),
    },
}

MAX_LAG = 7


def load_daily(path: Path, col: str) -> pd.Series:
    df = pd.read_csv(path, low_memory=False, on_bad_lines="skip")
    t = pd.to_datetime(df[col], errors="coerce")
    t = t.dropna()
    if t.empty:
        return pd.Series(dtype=float)
    # 微博时间可能带时区也可能不带，统一去时区后取日期
    try:
        t = t.dt.tz_localize(None)
    except (TypeError, AttributeError):
        pass
    return t.dt.normalize().value_counts().sort_index().astype(float)


def fit_tau(series: pd.Series) -> float | None:
    """对日度序列拟合指数衰减 τ（以峰值为起点，用峰值后 14 天）。"""
    if series.empty:
        return None
    y = series.to_numpy(dtype=float)
    pk = int(y.argmax())
    post = y[pk + 1 : pk + 15]
    if len(post) < 3 or y[pk] <= 0:
        return None
    best_err, best = float("inf"), None
    for tau in np.arange(0.5, 30.01, 0.25):
        pred = y[pk] * np.exp(-np.arange(1, len(post) + 1) / tau)
        err = float(np.mean(np.abs(pred - post)) / max(float(np.mean(post)), 1e-9))
        if err < best_err:
            best_err, best = err, float(tau)
    return best


def cross_lag(post: pd.Series, comment: pd.Series) -> tuple[int, float]:
    """找评论相对博文的最佳滞后（0..MAX_LAG 天），按相关性归一化。"""
    idx = post.index.union(comment.index)
    p = post.reindex(idx, fill_value=0.0).to_numpy()
    c = comment.reindex(idx, fill_value=0.0).to_numpy()
    best_lag, best_r = 0, -1.0
    if p.std() == 0 or c.std() == 0:
        return 0, 0.0
    for lag in range(0, MAX_LAG + 1):
        c2 = np.concatenate([np.zeros(lag), c[: len(c) - lag]]) if lag else c
        if c2.std() == 0:
            continue
        r = float(np.corrcoef(p, c2)[0, 1])
        if not np.isnan(r) and r > best_r:
            best_r, best_lag = r, lag
    return best_lag, round(best_r, 4)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {}
    for eid, cfg in CASES.items():
        post_path, post_col = cfg["post"]
        cmt_path, cmt_col = cfg["comment"]
        if not post_path.exists() or not cmt_path.exists():
            print(f"  ✗ {eid}: 文件缺失")
            continue

        post = load_daily(post_path, post_col)
        cmt = load_daily(cmt_path, cmt_col)
        if post.empty or cmt.empty:
            print(f"  ✗ {eid}: 时间解析为空")
            continue

        lag, r = cross_lag(post, cmt)
        post_peak = post.idxmax()
        cmt_peak = cmt.idxmax()
        peak_lag = int((cmt_peak - post_peak).days)

        # 统一到共同日历（便于前端叠加两条曲线）
        idx = post.index.union(cmt.index)
        post_f = post.reindex(idx, fill_value=0.0)
        cmt_f = cmt.reindex(idx, fill_value=0.0)

        data = {
            "event_id": eid,
            "name": cfg["name"],
            "post_count": int(post.sum()),
            "comment_count": int(cmt.sum()),
            "comment_per_post": round(float(cmt.sum() / max(post.sum(), 1)), 2),
            "post_days": int(len(post)),
            "comment_days": int(len(cmt)),
            "start": str(idx.min().date()),
            "end": str(idx.max().date()),
            "best_lag_days": lag,
            "best_lag_corr": r,
            "post_peak_day": str(post_peak.date()),
            "comment_peak_day": str(cmt_peak.date()),
            "peak_lag_days": peak_lag,
            "post_tau_days": fit_tau(post),
            "comment_tau_days": fit_tau(cmt),
            "series": {
                "dates": [str(d.date()) for d in idx],
                "post": [int(v) for v in post_f.to_numpy()],
                "comment": [int(v) for v in cmt_f.to_numpy()],
            },
        }
        (OUT / f"{eid}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        summary[eid] = {k: v for k, v in data.items() if k != "series"}

        print(f"  {eid:18} 博文 {int(post.sum()):>7,} 条 / 评论 {int(cmt.sum()):>7,} 条")
        print(f"     评论:博文 = {data['comment_per_post']}   最佳滞后 {lag} 天 (r={r})")
        print(f"     博文峰值 {post_peak.date()}  评论峰值 {cmt_peak.date()}  峰差 {peak_lag} 天")
        print(f"     τ 博文 {data['post_tau_days']} 天 / 评论 {data['comment_tau_days']} 天")
        print()

    (OUT / "_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  已完成 {len(summary)} 个事件的传播时序 → {OUT}")


if __name__ == "__main__":
    main()
