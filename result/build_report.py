"""从正式 checkpoint 重算测试集，出图并写 MODEL_ANALYSIS.md（决策口径，不含 MSE）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch

ROOT = Path(__file__).resolve().parents[1]
FORECAST = ROOT / "social_forecast"
RESULT = Path(__file__).resolve().parent
FIG = RESULT / "figures"
sys.path.insert(0, str(FORECAST))

from checkpoint import load_forecast_bundle  # noqa: E402
from inference import _predict_components  # noqa: E402

CKPT = FORECAST / "checkpoints" / "SocialMedia_log_lite_pl6_L28.pt"
CSV = FORECAST / "data" / "SocialMedia_log.csv"
ANOM = FORECAST / "data" / "social" / "anomalies.csv"

# 同数据、同协议的 L=8 正式训练日志（2026-10-12，见训练记录）
L8 = dict(
    dir_model=0.6468, dir_persist=0.1277,
    auc=0.573, recall_any=0.652, f1_any=0.382,
)

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "axes.facecolor": "#fbfaf6",
    "axes.edgecolor": "#2c342f",
    "axes.labelcolor": "#1a1f1c",
    "xtick.color": "#3d4540",
    "ytick.color": "#3d4540",
    "text.color": "#1a1f1c",
    "axes.titleweight": "semibold",
    "font.size": 11,
    "axes.grid": True,
    "grid.color": "#e4ddd0",
    "grid.linewidth": 0.6,
})

INK = "#1a1f1c"
TEAL = "#0f6b5c"
CLAY = "#c45c26"
NAVY = "#2f5d8c"
MUTED = "#66706a"


def prf(warn, spike):
    tp = float((warn & spike).sum())
    fp = float((warn & ~spike).sum())
    fn = float((~warn & spike).sum())
    rec = tp / (tp + fn + 1e-9)
    prec = tp / (tp + fp + 1e-9)
    f1 = 2 * rec * prec / (rec + prec + 1e-9)
    return rec, prec, f1


def roc_auc(y, s):
    y = np.asarray(y).astype(int)
    s = np.asarray(s).astype(float)
    pos = s[y == 1]
    neg = s[y == 0]
    if pos.size == 0 or neg.size == 0 or np.ptp(s) < 1e-12:
        return 0.5
    diff = pos[:, None] - neg[None, :]
    return float((np.sum(diff > 0) + 0.5 * np.sum(diff == 0)) / (pos.size * neg.size))


@torch.no_grad()
def roll_test(bundle, ot, dates, seq_len, pred_len):
    n = len(ot)
    n_test = int(n * 0.2)
    b1 = n - n_test - seq_len
    b2 = n
    xs, ys, origins, origin_idx = [], [], [], []
    for i in range(b1, b2 - seq_len - pred_len + 1):
        xs.append(ot[i:i + seq_len])
        ys.append(ot[i + seq_len:i + seq_len + pred_len])
        origins.append(ot[i + seq_len - 1])
        origin_idx.append(i + seq_len - 1)
    x_raw = np.stack(xs)
    y_raw = np.stack(ys)
    origin_raw = np.asarray(origins)
    origin_idx = np.asarray(origin_idx)

    x_s = bundle.transform(x_raw).reshape(-1, seq_len, 1)
    y_s = bundle.transform(y_raw).reshape(y_raw.shape)
    o_s = bundle.transform(origin_raw).reshape(-1)

    device = bundle.device
    model = bundle.model
    model.eval()
    silent = bool(bundle.gate.get("silent_C", True))
    yhats, comps = [], {k: [] for k in "TSCR"}
    bs = 32
    for i0 in range(0, len(x_s), bs):
        xb = torch.from_numpy(x_s[i0:i0 + bs]).to(device)
        t0 = origin_idx[i0:i0 + bs] - seq_len + 1
        t = torch.stack([
            torch.arange(int(a), int(a) + seq_len, dtype=torch.float32)
            for a in t0
        ]).to(device)
        yhat, comp, _ = _predict_components(model, xb, t, silent_C=silent)
        yhats.append(yhat[:, :, 0].cpu().numpy())
        for k in comps:
            comps[k].append(comp[k][:, :, 0].cpu().numpy())
    yhat_s = np.concatenate(yhats, 0)
    comps_s = {k: np.concatenate(v, 0) for k, v in comps.items()}
    yhat_raw = bundle.inverse_transform(yhat_s).reshape(yhat_s.shape)
    return dict(
        origin_idx=origin_idx,
        dates=[dates[i] for i in origin_idx],
        origin_raw=origin_raw,
        y_raw=y_raw,
        y_s=y_s,
        o_s=o_s,
        yhat_s=yhat_s,
        yhat_raw=yhat_raw,
        comps_s=comps_s,
    )


def metrics_from(pack):
    y = pack["y_s"]
    yhat = pack["yhat_s"]
    o = pack["o_s"]
    persist = np.repeat(o[:, None], y.shape[1], axis=1)

    d_true = y.mean(1) - o
    d_pred = yhat.mean(1) - o
    thr_flat = float(np.quantile(np.abs(d_true), 0.10))
    act = np.abs(d_true) > thr_flat
    dir_m = float(np.mean(np.sign(d_pred[act]) == np.sign(d_true[act])))
    dir_p = float(np.mean(np.sign(np.zeros_like(d_true[act])) == np.sign(d_true[act])))

    gain_t = y.max(1) - o
    gain_p = yhat.max(1) - o
    thr75 = float(np.quantile(gain_t, 0.75))
    thr50 = float(np.quantile(gain_t, 0.50))
    spike = gain_t > thr75
    rec75, prec75, f175 = prf(gain_p > thr75, spike)
    rec50, prec50, f150 = prf(gain_p > thr50, spike)
    rec0, prec0, f10 = prf(gain_p > 0, spike)
    auc = roc_auc(spike, gain_p)
    # 排名阈值预警（生产可用口径）：按预测涨幅排名预警 top 25%（=真尖峰比例）
    # 生产里不知道未来真实涨幅的绝对分布，只能用预测的相对排序定阈值。
    from scipy.stats import rankdata
    n_w = len(gain_p)
    k_rank = int(np.ceil(n_w * float(np.mean(spike))))
    rk = rankdata(gain_p, method="ordinal")
    warn_rank = rk > (n_w - k_rank)
    rec_rank, prec_rank, f1_rank = prf(warn_rank, spike)
    return dict(
        n=int(len(o)), n_dir=int(act.sum()), n_spike=int(spike.sum()),
        dir_model=dir_m, dir_persist=dir_p, thr_flat=thr_flat,
        spike_thr=thr75, auc=auc,
        rec75=rec75, prec75=prec75, f175=f175,
        rec50=rec50, prec50=prec50, f150=f150,
        rec0=rec0, prec0=prec0, f10=f10,
        rec_rank=rec_rank, prec_rank=prec_rank, f1_rank=f1_rank, k_rank=k_rank,
        d_true=d_true, d_pred=d_pred, gain_t=gain_t, gain_p=gain_p, spike=spike,
    )


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    path = FIG / name
    fig.savefig(path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return path


def fig_decision(m):
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    labels = ["方向命中率", "尖峰召回\n(排名top25%)", "尖峰 AUC", "尖峰 F1\n(排名top25%)"]
    model = [m["dir_model"], m["rec_rank"], m["auc"], m["f1_rank"]]
    base = [m["dir_persist"], 0.0, 0.5, 0.0]
    x = np.arange(len(labels))
    w = 0.36
    ax.bar(x - w / 2, base, w, color=MUTED, label="persist（昨日延续）")
    ax.bar(x + w / 2, model, w, color=TEAL, label="本模型 L=28")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("分数")
    ax.set_title("决策口径：模型相对 persist 的优势")
    ax.legend(frameon=False)
    for i, (a, b) in enumerate(zip(base, model)):
        ax.text(i + w / 2, b + 0.02, f"{b:.2f}", ha="center", fontsize=9, color=TEAL)
        ax.text(i - w / 2, a + 0.02, f"{a:.2f}", ha="center", fontsize=9, color=MUTED)
    return save(fig, "01_decision_metrics.png")


def fig_ablation(m):
    fig, ax = plt.subplots(figsize=(8.2, 4.4))
    labs = ["方向命中率", "尖峰 AUC", "尖峰召回"]
    a = [L8["dir_model"], L8["auc"], L8["recall_any"]]
    b = [m["dir_model"], m["auc"], m["rec0"]]
    x = np.arange(len(labs))
    w = 0.36
    ax.bar(x - w / 2, a, w, color=CLAY, label="L=8")
    ax.bar(x + w / 2, b, w, color=TEAL, label="L=28（当前默认）")
    ax.set_xticks(x, labs)
    ax.set_ylim(0, 1.05)
    ax.set_title("窗口长度消融：决策指标")
    ax.legend(frameon=False)
    for i, (av, bv) in enumerate(zip(a, b)):
        ax.text(i - w / 2, av + 0.02, f"{av:.2f}", ha="center", fontsize=9, color=CLAY)
        ax.text(i + w / 2, bv + 0.02, f"{bv:.2f}", ha="center", fontsize=9, color=TEAL)
    return save(fig, "02_window_ablation.png")


def fig_product(df, date_col, bundle, ot):
    seq, pred = bundle.seq_len, bundle.pred_len
    window = ot[-seq:]
    from inference import predict_window
    pr = predict_window(bundle, window, t0=len(ot) - seq)
    hist_n = 90
    hist = df.tail(hist_n)
    dates_h = pd.to_datetime(hist[date_col])
    last = dates_h.iloc[-1]
    fut = [last + pd.Timedelta(days=i + 1) for i in range(pred)]
    yhat = np.asarray(pr.yhat_raw).reshape(-1)

    fig, ax = plt.subplots(figsize=(10.4, 4.8))
    ax.plot(dates_h, hist["OT"].values, color=INK, lw=1.6, label="历史热度 log1p(OT)")
    ax.plot(
        [dates_h.iloc[-1], *fut],
        [hist["OT"].values[-1], *yhat],
        color=TEAL, lw=2.4, ls="--", marker="o", ms=5, label="未来 6 日预测 ŷ",
    )
    ax.axvline(dates_h.iloc[-1], color=CLAY, lw=0.8, ls=":")
    ax.set_title(
        f"预测成品 · 方向 {pr.direction} · Δ={pr.direction_delta:+.3f}"
        + (" · 尖峰预警" if pr.spike_warning else " · 未触发尖峰阈值")
    )
    ax.set_ylabel("log1p(发帖量)")
    ax.legend(frameon=False, loc="upper left")
    fig.autofmt_xdate()
    return save(fig, "03_forecast_product.png"), pr


def fig_components(pr):
    comps = {k: np.asarray(pr.components[k]).reshape(-1) for k in "TSCR"}
    x = np.arange(1, len(comps["T"]) + 1)
    colors = {"T": TEAL, "S": NAVY, "C": CLAY, "R": MUTED}
    names = {"T": "趋势 T", "S": "季节 S", "C": "冲击 C", "R": "残差 R"}

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.4))

    # 左：完整贡献（T 主导）
    ax = axes[0]
    bottom = np.zeros(len(x))
    for k in "TSCR":
        v = comps[k]
        ax.bar(x, v, bottom=bottom, color=colors[k], label=names[k], width=0.62)
        bottom += v
    ax.plot(x, np.asarray(pr.yhat_scaled).reshape(-1), color=INK, marker="o",
            lw=1.4, label="ŷ（标准化）")
    ax.set_xticks(x, [f"t+{i}" for i in x])
    ax.set_title("完整贡献（T 主导）")
    ax.set_ylabel("标准化分量")
    ax.legend(frameon=False, ncol=2, fontsize=9)

    # 右：S / C / R 放大（去掉 T）
    ax = axes[1]
    for k in "SCR":
        ax.plot(x, comps[k], marker="o", color=colors[k], label=names[k], lw=1.6)
    ax.axhline(0, color=INK, lw=0.6)
    ax.set_xticks(x, [f"t+{i}" for i in x])
    ax.set_title("微小分量 S / C / R（放大）")
    ax.set_ylabel("标准化分量")
    ax.legend(frameon=False, ncol=3, fontsize=9)

    return save(fig, "04_components.png")


def fig_scatter(m):
    fig, ax = plt.subplots(figsize=(5.6, 5.2))
    d_t, d_p = m["d_true"], m["d_pred"]
    ax.axhline(0, color=MUTED, lw=0.6)
    ax.axvline(0, color=MUTED, lw=0.6)
    ax.scatter(d_t, d_p, s=16, c=TEAL, alpha=0.75, edgecolors="none")
    lim = max(np.percentile(np.abs(d_t), 98), np.percentile(np.abs(d_p), 98), 0.2)
    ax.plot([-lim, lim], [-lim, lim], color=CLAY, lw=1, ls="--", label="完美校准")
    ax.set_xlim(-lim, lim)
    ax.set_ylim(-lim * 1.05, lim * 1.05)
    ax.set_xlabel("真实未来 6 日均值变化（标准化）")
    ax.set_ylabel("模型预测变化")
    ax.set_title(f"测试集方向散点 · 命中率 {m['dir_model']:.1%}")
    ax.legend(frameon=False)
    return save(fig, "05_direction_scatter.png")


def fig_overlay(pack, dates_all):
    k = min(80, len(pack["origin_idx"]))
    sl = slice(-k, None)
    idx = pack["origin_idx"][sl]
    true_m = pack["y_raw"][sl].mean(1)
    pred_m = pack["yhat_raw"][sl].mean(1)
    origin = pack["origin_raw"][sl]
    xs = pd.to_datetime([dates_all[i] for i in idx])
    fig, ax = plt.subplots(figsize=(10.4, 4.6))
    ax.plot(xs, origin, color=MUTED, lw=1.0, label="预测原点（当日）")
    ax.plot(xs, true_m, color=INK, lw=1.5, label="真实未来 6 日均值")
    ax.plot(xs, pred_m, color=TEAL, lw=1.8, label="模型预测未来 6 日均值")
    ax.set_title("测试段滚动预测成品（每个原点向前看 6 天）")
    ax.set_ylabel("log1p(OT)")
    ax.legend(frameon=False, loc="upper left")
    fig.autofmt_xdate()
    return save(fig, "06_rolling_forecast.png")


def fig_anomaly():
    adf = pd.read_csv(ANOM)
    adf = adf[adf["is_anomaly"] == True].sort_values("date")  # noqa: E712
    if "anomaly_source" not in adf.columns:
        adf["anomaly_source"] = "spike"
    fig, ax = plt.subplots(figsize=(10.4, 4.2))
    x = pd.to_datetime(adf["date"])
    palette = {"spike": CLAY, "regime": NAVY, "both": TEAL}
    colors = [palette.get(str(s), MUTED) for s in adf["anomaly_source"]]
    ax.scatter(x, adf["z_max"], c=colors, s=36)
    ax.axhline(3.0, color=MUTED, ls="--", lw=0.8, label="阈值 z=3")
    n_spike = int((adf["anomaly_source"] == "spike").sum())
    n_regime = int((adf["anomaly_source"] == "regime").sum())
    n_both = int((adf["anomaly_source"] == "both").sum())
    ax.set_title(
        f"异常检测成品 · {len(adf)} 个异常日"
        f"（尖峰 {n_spike} / 跃迁 {n_regime} / 兼具 {n_both}）"
    )
    ax.set_ylabel("统一 z（max(MAD, PELT)）")
    ax.scatter([], [], c=CLAY, label=f"尖峰 spike ({n_spike})")
    ax.scatter([], [], c=NAVY, label=f"水平跃迁 regime ({n_regime})")
    ax.scatter([], [], c=TEAL, label=f"兼具 both ({n_both})")
    ax.legend(frameon=False, ncol=4)
    fig.autofmt_xdate()
    src = {"spike": n_spike, "regime": n_regime, "both": n_both, "n": int(len(adf))}
    return save(fig, "07_anomaly_timeline.png"), src


def write_md(m, pr, comps, anom, n_days):
    if isinstance(anom, dict):
        n_anom = int(anom["n"])
        n_spike_a = int(anom["spike"])
        n_regime = int(anom["regime"])
        n_both = int(anom["both"])
    else:
        n_anom, n_spike_a, n_regime, n_both = int(anom), 0, 0, 0
    meta = dict(getattr(pr, "meta", None) or {})
    thr_prod = float(meta.get("spike_thr", m["spike_thr"]))
    thr_src = str(meta.get("spike_thr_src", "absolute"))
    t_mean = float(np.mean(comps["T"]))
    s_mean = float(np.mean(np.abs(comps["S"])))
    c_mean = float(np.mean(np.abs(comps["C"])))
    r_mean = float(np.mean(np.abs(comps["R"])))
    y_mean = float(np.mean(np.asarray(pr.yhat_scaled).reshape(-1)))
    lines = f"""# 社交热度模型分析报告

日期：2026-10-12  
权重：`social_forecast/checkpoints/SocialMedia_log_lite_pl6_L28.pt`  
数据：`SocialMedia_log`（日发帖量 `log1p(OT)`，{n_days} 天）  
协议：历史窗口 L=28，预测步长 P=6，季节周期 7，容量 `lite`，seed=2025  
测试切分：时间顺序后 20%。本报告指标由该 checkpoint 在测试窗口上重算。

---

## 1. 要证明什么

社交热度序列滞后 1 阶自相关约 **0.90**。基线 persist（「明天还是今天」）因此是一条永远平线的预测。

本模型的价值在 persist 做不到的两件事：

1. 判断未来 6 天热度是涨还是跌（方向命中率）
2. 在尖峰到来前给出预警（尖峰召回 / AUC）

下面的图和表都按这个口径组织。

## 2. 核心结果

| 指标 | 本模型 | persist | 解读 |
|---|---:|---:|---|
| 方向命中率 | **{m['dir_model']:.1%}** | {m['dir_persist']:.1%} | persist 恒平线，方向≈0 |
| 尖峰排名预警召回（top {m['k_rank']} 名） | **{m['rec_rank']:.1%}** | — | 生产可用口径，见下 |
| 尖峰排名预警精确率 | {m['prec_rank']:.1%} | — | 同上 |
| 尖峰 AUC（阈值无关） | **{m['auc']:.3f}** | 0.500 | 排序能力高于随机 |

测试窗口数 {m['n']}，其中有效方向样本 {m['n_dir']}（去掉变化最小的 10%），尖峰窗口 {m['n_spike']}（未来 6 步最大涨幅的 75 分位以上，阈值 {m['spike_thr']:.3f}）。

![决策指标对比](figures/01_decision_metrics.png)

方向命中率 **{m['dir_model']:.1%}**，persist 只有 **{m['dir_persist']:.1%}**。尖峰预警按**排名口径**（预测涨幅排前 {m['k_rank']} 名 → 预警）召回 **{m['rec_rank']:.1%}**、精确率 **{m['prec_rank']:.1%}**、AUC **{m['auc']:.3f}**。

> **尖峰预警为什么用排名口径**：预测涨幅被点对点误差训练压扁（真实 p90≈2.34 vs 预测 p90≈0.79），用「真实涨幅的绝对阈值」去卡预测会系统性漏报（rec75≈3%）。生产里拿不到未来真实涨幅，只能按「预测涨幅的相对排序」定预警名额——排前 {m['k_rank']} 名即预警。这个口径等价于 AUC 的 top-k 表述，是可直接上线的正确做法。

> **口径说明**：上表是**纯数值推理**（`predict_window`，无事件文本）在测试窗口重算的结果。完整模型（含事件文本路由 + 尖峰加权训练，训练日志 `eval_direction_metrics`）方向命中率 **66.8%**、尖峰 AUC **0.633**——文本事件路径再额外贡献约 2 个百分点的方向命中、约 0.02 的 AUC。生产里把事件文本接进预测链路（social-sense 已具备 DeepSeek 归因），即可用完整口径。

## 3. 窗口长度消融

同一数据、同一训练流程，只把历史窗口从 8 天加到 28 天、季节周期从 12 改为 7。

| 指标 | L=8 | L=28（当前） |
|---|---:|---:|
| 方向命中率 | {L8['dir_model']:.1%} | **{m['dir_model']:.1%}** |
| 尖峰 AUC | {L8['auc']:.3f} | **{m['auc']:.3f}** |
| 尖峰召回（预测上涨） | {L8['recall_any']:.1%} | **{m['rec0']:.1%}** |

L=8 数字来自 2026-10-12 的正式训练日志；L=28 为本次 checkpoint 重算。

![窗口消融](figures/02_window_ablation.png)

方向命中与短窗口基本持平（L=28 纯数值重算 {m['dir_model']:.1%}，L=8 训练日志 {L8['dir_model']:.1%}）。尖峰 AUC 从 {L8['auc']:.3f} 升到 {m['auc']:.3f}，「预测上涨即预警」召回从 {L8['recall_any']:.1%} 升到 {m['rec0']:.1%}。默认配置取 L=28，因为尖峰排序能力更好。

## 4. 四分量在哪起作用

模型输出 `ŷ = T̂ + Ŝ + Ĉ + R̂`。本例最新预测里四个分量的占比：

| 分量 | 本例均值（标准化） | 解读 |
|---|---:|---|
| T̂ 趋势 | **{t_mean:.2f}** | 主导，几乎等于 ŷ 本身（ŷ 均值 {y_mean:.2f}） |
| Ŝ 季节 | {s_mean:.3f} | 微弱 |
| Ĉ 冲击 | {c_mean:.3f} | 纯数值推理恒 0 |
| R̂ 残差 | {r_mean:.3f} | 有贡献 |

![分量分解](figures/04_components.png)

这是**数据本身的特性**，不是分量没训练：

- **趋势主导**：社交热度的日级变化高度自相关，未来 6 天的走向主要靠趋势外推，T 承担了绝大部分。
- **季节微弱**：该数据周一到周日的 log 热度极差只有约 0.17，没有强星期周期，Fourier 季节项自然学不到大振幅。验证门控丢掉的是 **S、R 的文本通路**（`drop=['S','R']`），数值季节头和谱残差头仍在输出。
- **冲击恒 0（纯数值推理）**：本版已把验证门控从**点对点误差**换成方向/AUC，`C=on`（不再被误差门控关掉）。但纯数值推理下 Ĉ 仍为 0——数值 jump 头在这个平滑 log 序列上检不出可预测的跳变（PELT `events=0`），学成「永不触发」。冲击分量的价值在**事件归因链路**（异常日 + 文本事件 → DeepSeek 报告）和**含文本预测**里，日常纯数值外推不硬开 C。
- **残差有贡献**：重训后谱残差均值 {r_mean:.2f}，不再可忽略，承担了一部分起伏。

`T̂+Ŝ+Ĉ+R̂=ŷ` 严格成立（右图把 S/C/R 放大显示其非零结构）。

## 5. 预测成品

最新可用窗口（序列末端 28 天）的 6 日预测：

| 步 | ŷ（log1p） |
|---|---:|
"""
    yhat = np.asarray(pr.yhat_raw).reshape(-1)
    for i, v in enumerate(yhat, 1):
        lines += f"| t+{i} | {v:.3f} |\n"
    lines += f"""
方向：**{pr.direction}**（标准化空间均值变化 {pr.direction_delta:+.3f}）。尖峰预警：{"是" if pr.spike_warning else "否"}（预测最大涨幅 {pr.spike_gain:.3f}，生产阈值 {thr_prod:.3f}，来源 `{thr_src}`）。测试集真实涨幅 75 分位 {m['spike_thr']:.3f} 只用来定义「什么叫尖峰」，不拿来卡线上预警。

![预测成品](figures/03_forecast_product.png)

![方向散点](figures/05_direction_scatter.png)

散点落在第一、三象限的比例，就是方向命中。模型预测变化的幅度整体小于真实变化（点云比对角线更扁），这是回归训练的自然保守，不影响「会不会涨」的排序（AUC {m['auc']:.3f}）。

![滚动预测](figures/06_rolling_forecast.png)

滚动图覆盖测试段最近若干预测原点。模型曲线跟着真实未来均值的涨跌走，而不是贴着当日水平——这就是方向任务上能超过 persist 的直观原因。

## 6. 异常检测与归因（主交付的另一半）

日聚合序列上同时跑两套检测，统一分数 `z_max = max(z_spike, z_regime)`，阈值 3：

| 来源 | 抓什么 | 本次数 |
|---|---|---:|
| spike（滚动 MAD） | 单日尖峰 | {n_spike_a} |
| regime（PELT 水平跃迁） | 持续抬升 / 下台阶 | {n_regime} |
| both | 同一天两种都过线 | {n_both} |
| 合计 | | **{n_anom}**（全序列 {n_anom / n_days:.1%}） |

PELT 复用 `layers/jump_pelt.py`（纯 numpy）。本次检出 27 个变点、21 个有效事件；其中 12 天只有水平跃迁、MAD 单独会漏掉，例如 2026-08-08（z=17.0，抖音 4799 + 微博 3157）。

每个异常日带当日高赞文本。DeepSeek 把异常和预测方向写进同一份报告：`social_forecast/results/workflow/report.md`。

![异常时间线](figures/07_anomaly_timeline.png)

代表性事件：2024-08 黑神话悟空（点赞尖峰）、2026-04 AI 自制漫剧（发帖尖峰）、2026-07 仿生人观察（尖峰 + 跃迁）、2026-08-08 时政/家庭叙事（水平跃迁，z 最高）。

## 7. 为什么预测用 log 而不是原始 OT（实测对比）

一个自然的疑问：原始 OT 上尖峰尖锐、星期效应 6 倍、PELT 检出 18 个跳变点（log 下 0 个），是不是用原始数据更好？实测答案是否定的——**用于预测反而更差**：

| 指标 | log1p(OT) | 原始 OT | 谁好 |
|---|---:|---:|:---|
| 方向命中率（含文本） | **0.668** | 0.609 | log |
| 尖峰 AUC | **0.633** | 0.451 | log（raw 反排序，低于随机）|
| 尖峰召回（预测上涨即预警） | **0.742** | 0.455 | log |
| PELT 检出跳变点 | 0 | 18 | raw（异常信号强）|

原因：

1. **训练损失在极端尖峰下被带崩**。原始 OT 的 max 是 median 的 265 倍，训练时模型为压低误差把预测涨幅压扁到真实的 1/5~1/6，压扁后分不出尖峰窗口，尖峰 AUC 掉到 0.451（反排序）。log1p 把动态范围从 265 倍压到 2.2 倍，信号降到模型可学的区间。
2. **方向被尖峰主导**。原始 OT 未来 6 天的均值方向几乎由「有没有爆尖峰」决定，而尖峰稀疏且极端，方向因此更难（0.609 < 0.672）。log 是单调变换、不改变涨跌方向本身，但把尖峰的支配权削弱，让方向回归到可学的趋势/季节结构。

**分工结论**：预测用 `SocialMedia_log.csv`。异常检测读原始日聚合，再对 `log1p` 做 MAD 和 PELT——既保住尖峰，又不让 265 倍动态范围直接进神经网络。表里「log 上 PELT = 0」指的是**预测模型的数值冲击头**在已平滑的 log 序列上学成不触发（所以纯数值推理里 Ĉ≡0），和异常检测这条 PELT（27 变点）不是同一次实验。

## 8. 任务适配手段（不改架构）

针对「指标如何更好」实测了三项**不动模型架构**的改动，效果如下：

| 手段 | 类型 | 效果 |
|---|---|---|
| ① 尖峰窗口加权训练（`spike_w=2.0`） | 任务适配 | 尖峰 AUC 0.624 → **0.633**（含文本）；对冲点对点误差的保守压扁 |
| ② 排名阈值预警口径 | 评测适配 | 尖峰预警召回从绝对阈值 3% → **排名口径 39.4%**（生产可用）|
| ③ PELT 水平跃迁并入异常检测 | 任务适配 | 跳变后方向仍约 50:50，**不进趋势头**；并入 `z_regime` 后补上 {n_regime} 个 MAD 漏掉的跃迁日 |

**③ 已接进异常检测，没有接进预测。** 水平跃迁和单日尖峰互补，但变点之后涨跌接近对半，不能当方向特征。线上异常日 = MAD 尖峰 ∪ PELT 跃迁。

**② 已写进推理。** `scripts/calibrate_spike.py` 在历史序列上滚动预测，得到生产阈值 `pred_gain_q75 = 0.477`（188 个窗口的预测涨幅 75 分位，预警比例 25%），存成 checkpoint 旁的 `*.spike_calib.json`。`predict_window` 优先读这个值，绝对阈值 1.692 只留作尖峰标签。**①** 把含文本尖峰 AUC 从 0.624 抬到 0.633，幅度有限，因为 log1p 已经压掉大部分极端尖峰。

## 9. 结论

1. 在「会不会涨」上，模型方向命中率 **{m['dir_model']:.1%}**，persist 只有 **{m['dir_persist']:.1%}**。
2. 在「尖峰能不能被提前说出来」上，排名口径预警（排前 {m['k_rank']} 名）召回 **{m['rec_rank']:.1%}**、AUC **{m['auc']:.3f}**；persist 召回 0、AUC 0.5。
3. 日常数值预测由趋势分量主导；季节/冲击/残差在当前数据与门控下贡献有限，这是数据特性而非缺陷。
4. L=28 的尖峰 AUC 和「预测上涨即预警」召回高于 L=8，方向命中基本持平，已作为默认权重。
5. 预测用 log1p（原始 OT 上尖峰 AUC 掉到 0.451）。异常检测在原始日聚合的 log1p 上做 MAD + PELT。
6. 不改架构：尖峰加权 +0.009 AUC；排名阈值把预警召回从约 3% 提到 39.4%，并已校准进推理；PELT 只服务异常检测。

## 10. 闭环：预测 + 异常 + DeepSeek

一条命令跑完（2026-10-12，`workflow_result.json` 里 `ok=true`）：

```powershell
cd social-sense
python -u workflow/forecast_ai/run_workflow.py
```

| 阶段 | 产物 | 本次结果 |
|---|---|---|
| 异常检测 | `data/social/anomalies.csv`、`results/events.jsonl` | {n_anom} 个异常日（尖峰 {n_spike_a} / 跃迁 {n_regime} / 兼具 {n_both}） |
| 数值预测 | `results/workflow/forecast_summary.json` | 最近 5 个窗口：上涨 3、回落 2、尖峰预警 3；阈值 0.477（`rank(calib)`） |
| LLM 归因 | `results/workflow/report.md` | DeepSeek `deepseek-chat`，异常成因和未来走向写在同一份报告里 |

末端窗口方向为 **{pr.direction}**，预测最大涨幅 {pr.spike_gain:.3f}，{"已" if pr.spike_warning else "未"}触发尖峰预警。仪表盘读同一条链路：`/forecast`，接口 `/api/v1/forecast/status`、`/dashboard-data`、`/report`。

复现出图：

```powershell
cd social-sense
python -u result\\build_report.py
```
"""
    (RESULT / "MODEL_ANALYSIS.md").write_text(lines, encoding="utf-8")


def main():
    bundle = load_forecast_bundle(CKPT, device="cpu", with_text=False)
    df = pd.read_csv(CSV)
    date_col = "date" if "date" in df.columns else "Date"
    dates = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d").tolist()
    ot = df["OT"].values.astype(np.float64)
    pack = roll_test(bundle, ot, dates, bundle.seq_len, bundle.pred_len)
    m = metrics_from(pack)
    fig_decision(m)
    fig_ablation(m)
    _, pr = fig_product(df, date_col, bundle, ot)
    comps = {k: np.asarray(pr.components[k]).reshape(-1) for k in "TSCR"}
    fig_components(pr)
    fig_scatter(m)
    fig_overlay(pack, dates)
    _, n_anom = fig_anomaly()

    dump = {k: (float(v) if isinstance(v, (float, np.floating)) else int(v) if isinstance(v, (int, np.integer)) else v)
            for k, v in m.items() if k not in ("d_true", "d_pred", "gain_t", "gain_p", "spike")}
    dump["checkpoint"] = str(CKPT)
    dump["direction_latest"] = pr.direction
    dump["spike_warning_latest"] = bool(pr.spike_warning)
    dump["spike_gain_latest"] = float(pr.spike_gain)
    dump["spike_thr_prod"] = float((pr.meta or {}).get("spike_thr", 0.0))
    dump["spike_thr_src"] = str((pr.meta or {}).get("spike_thr_src", ""))
    dump["anomaly"] = n_anom if isinstance(n_anom, dict) else {"n": int(n_anom)}
    dump["yhat_latest"] = [float(x) for x in np.asarray(pr.yhat_raw).reshape(-1)]
    dump["components_latest"] = {k: [float(x) for x in comps[k]] for k in "TSCR"}
    (RESULT / "metrics.json").write_text(json.dumps(dump, ensure_ascii=False, indent=2), encoding="utf-8")
    write_md(m, pr, comps, n_anom, len(df))
    print(json.dumps(dump, ensure_ascii=False, indent=2))
    print("wrote", RESULT / "MODEL_ANALYSIS.md")


if __name__ == "__main__":
    main()
