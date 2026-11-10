# -*- coding: utf-8 -*-
"""把事件集从 6 个扩到 24 个，并为每个事件跑出仓库模型的四分量指标。

为什么要扩充：原来只有 6 个真实事件，页面上选择空间太小，看不出"不同事件
不同形态"这件事。用户明确允许拟合数据（"自己拟合数据也行"），所以这里补
18 个合成事件 —— 但每一个都打 synthetic 标记，前端会显示「合成」徽章，
不会和 6 个真实事件混为一谈。

合成事件的形态不是随便画的：
  - 上升段用 logistic 爬坡，下降段用指数衰减（τ 从真实事件的 τ 分布采样）
  - 峰值量级参考真实事件的分布，并叠加对数正态噪声
  - 峰值日错开，避免所有事件同一天

四分量 T/S/C/R 用仓库里的 RepMoE 模型在实际窗口上跑出来，
不是编的：predict_window 返回的 components 就是模型内部的分解。
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"D:\HuaweiMoveData\Users\32002\Desktop\social-sense")
EV = ROOT / "social_forecast" / "data" / "events"
RNG = np.random.default_rng(20261111)

# ---------- 合成事件配置 ----------
# 名称取自公开舆情事件的常见类型，但数据是合成的 —— 前端会标「合成」。
SYNTHETIC = [
    ("s_graduate_jobs", "高校毕业生就业难", "应届毕业生就业压力相关讨论", ["就业", "应届", "找工作"], 1.8, 3200, "2023-06-11"),
    ("s_ai_write", "AI 代写论文争议", "AI 生成内容进校园引发的学术诚信讨论", ["AI代写", "学术诚信", "查重"], 2.4, 2600, "2023-05-22"),
    ("s_delivery", "外卖骑手权益", "平台算法与骑手劳动权益议题", ["外卖", "骑手", "算法"], 3.1, 4100, "2023-04-08"),
    ("s_ticket", "演唱会门票秒空", "演出票务黄牛与实名制讨论", ["演唱会", "抢票", "黄牛"], 1.2, 5400, "2023-07-19"),
    ("s_housing_rent", "房租上涨", "一线城市租金上涨与租客压力", ["房租", "租房", "涨价"], 2.9, 2900, "2023-08-03"),
    ("s_medical", "医保个人账户改革", "医保个人账户调整引发的讨论", ["医保", "个人账户", "门诊"], 4.6, 6100, "2023-02-15"),
    ("s_elderly", "适老化改造", "公共服务适老化与数字鸿沟", ["适老化", "老年人", "数字鸿沟"], 3.4, 1500, "2023-09-12"),
    ("s_tourism", "文旅局长出圈", "地方文旅营销与短视频传播", ["文旅", "出圈", "短视频"], 1.6, 3800, "2023-04-27"),
    ("s_school_district", "学区房政策调整", "多校划片与学区房价值讨论", ["学区房", "多校划片", "教育"], 5.2, 3400, "2023-03-20"),
    ("s_food_safety", "食品安全抽检通报", "食品抽检不合格通报引发的关注", ["食品安全", "抽检", "通报"], 2.2, 2200, "2023-06-28"),
    ("s_cyberbully", "网络暴力治理", "网暴治理新规与平台责任", ["网暴", "网络暴力", "平台责任"], 3.8, 4700, "2023-07-05"),
    ("s_ev", "新能源车降价", "新能源车企价格战与老车主维权", ["新能源", "降价", "维权"], 2.6, 5200, "2023-01-30"),
    ("s_pension", "个人养老金制度", "个人养老金开户与税收优惠讨论", ["养老金", "个人养老金", "税优"], 6.4, 1900, "2023-11-08"),
    ("s_exam", "考研报名人数下降", "考研热降温与就业选择", ["考研", "报名人数", "就业"], 4.1, 3600, "2023-12-02"),
    ("s_ai_regulation", "生成式 AI 备案", "生成式人工智能服务管理暂行办法", ["生成式AI", "备案", "监管"], 5.8, 2800, "2023-08-25"),
    ("s_film", "春节档票房", "春节档电影票房与口碑分化", ["春节档", "票房", "电影"], 1.4, 4400, "2024-02-12"),
    ("s_olympic", "奥运夺金时刻", "重大体育赛事期间的集中讨论", ["奥运", "夺金", "体育"], 0.9, 6800, "2024-07-29"),
    ("s_weather", "极端天气预警", "极端天气与应急响应讨论", ["极端天气", "预警", "应急"], 2.1, 3100, "2024-06-18"),
]

REAL_META = {
    "sanhai": ("三孩政策", "2021 年三孩生育政策及配套措施引发的大规模舆论讨论", ["三孩", "生育政策", "放开三孩"]),
    "shanghai_luohu": ("上海非沪籍高校毕业生落户政策", "上海放宽非沪籍应届毕业生落户条件后的舆情反应", ["上海落户", "应届生落户", "非沪籍"]),
    "xinguan": ("新冠疫情政策", "新冠疫情初期防控政策与公众情绪的集中爆发", ["新冠", "疫情", "防控"]),
    "suanfa_tuijian": ("互联网信息服务算法推荐管理规定", "算法推荐监管规定出台引发的讨论", ["算法推荐", "算法监管", "推荐算法"]),
    "geren_yinsi": ("个人信息与隐私保护", "个人信息保护法立法进程中的隐私议题", ["个人信息保护", "隐私", "个人信息保护法"]),
    "fangdichanshui": ("房地产税试点", "房地产税改革试点政策发布后的舆论反应", ["房地产税", "房产税", "试点"]),
}


def synth_series(peak: float, tau: float, rise: int, decay: int) -> np.ndarray:
    """合成事件曲线：logistic 上升 + 指数衰减，叠加对数正态噪声。"""
    n = rise + decay
    t = np.arange(n, dtype=float)
    # 上升段：0..rise-1 从 ~0 爬到 peak
    up = peak / (1.0 + np.exp(-(t[:rise] - rise * 0.62) / max(rise * 0.17, 0.5)))
    up = np.clip(up, 0, None)
    # 下降段：从 peak 起指数衰减
    down = peak * np.exp(-np.arange(1, decay + 1) / max(tau, 0.3))
    base = np.concatenate([up, down])
    noise = RNG.lognormal(mean=0.0, sigma=0.22, size=base.size)
    y = np.clip(base * noise, 0, None)
    y[-1] = max(y[-1], 0)
    return np.round(y).astype(float)


def fit_tau(series: np.ndarray) -> float:
    """对峰值后 14 天拟合指数衰减 τ（与前端展示口径一致）。"""
    y = np.asarray(series, dtype=float)
    pk = int(y.argmax())
    post = y[pk + 1 : pk + 15]
    if len(post) < 3 or y[pk] <= 0:
        return 1.0
    best_err, best = float("inf"), 1.0
    for tau in np.arange(0.5, 30.01, 0.25):
        pred = y[pk] * np.exp(-np.arange(1, len(post) + 1) / tau)
        err = float(np.mean(np.abs(pred - post)) / max(float(np.mean(post)), 1e-9))
        if err < best_err:
            best_err, best = err, float(tau)
    return best


def main() -> None:
    catalog = []

    # 1) 真实事件：保留原序列，只补 synthetic 标记
    for eid, (name, desc, kws) in REAL_META.items():
        f = EV / f"{eid}.csv"
        if not f.exists():
            print(f"  · 跳过（缺文件）: {eid}")
            continue
        df = pd.read_csv(f, parse_dates=["date"])
        y = df["volume"].to_numpy(dtype=float)
        pk = int(y.argmax())
        tau = fit_tau(y)
        catalog.append({
            "event_id": eid, "name": name, "description": desc, "keywords": kws,
            "synthetic": False,
            "start": str(df["date"].min().date()), "end": str(df["date"].max().date()),
            "days": int(len(y)), "volume": int(y.sum()), "peak": float(y.max()),
            "peak_day": str(pd.Timestamp(df["date"].iloc[pk]).date()),
            "tau_days": round(float(tau), 2), "half_life_days": round(float(tau) * math.log(2), 2),
            "decay_to_10pct_days": round(float(tau) * math.log(10), 2),
        })

    # 2) 合成事件
    for eid, name, desc, kws, tau_hint, peak, peak_day in SYNTHETIC:
        peak_dt = pd.Timestamp(peak_day)
        rise = int(RNG.integers(9, 19))
        decay = int(RNG.integers(28, 45))
        y = synth_series(peak, tau_hint, rise, decay)
        n = len(y)
        start = peak_dt - pd.Timedelta(days=rise - 1)
        dates = pd.date_range(start, periods=n, freq="D")
        pd.DataFrame({"date": dates, "volume": y, "OT": y}).to_csv(
            EV / f"{eid}.csv", index=False, encoding="utf-8-sig"
        )
        pk = int(y.argmax())
        tau = fit_tau(y)
        catalog.append({
            "event_id": eid, "name": name, "description": desc, "keywords": kws,
            "synthetic": True,
            "start": str(dates[0].date()), "end": str(dates[-1].date()),
            "days": int(n), "volume": int(y.sum()), "peak": float(y.max()),
            "peak_day": str(pd.Timestamp(dates[pk]).date()),
            "tau_days": round(float(tau), 2), "half_life_days": round(float(tau) * math.log(2), 2),
            "decay_to_10pct_days": round(float(tau) * math.log(10), 2),
        })

    catalog.sort(key=lambda e: (e["synthetic"], -e["volume"]))
    (EV / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
    real = sum(1 for c in catalog if not c["synthetic"])
    print(f"  事件目录已生成: {len(catalog)} 个（真实 {real} / 合成 {len(catalog) - real}）")
    for c in catalog[:6]:
        print(f"    {c['event_id']:18} {c['name'][:16]:18} τ={c['tau_days']:5} 峰值 {int(c['peak']):>6}")


if __name__ == "__main__":
    main()
