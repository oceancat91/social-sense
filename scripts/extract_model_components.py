# -*- coding: utf-8 -*-
"""为每个事件跑仓库 RepMoE 模型的四分量分解（T/S/C/R）与方向/尖峰指标。

为什么要单独跑这一步：前端原来只展示指数衰减的 τ 和半衰期，这些是统计拟合量，
不是"模型跑出来的项"。用户明确要求指标里要有仓库模型输出的项 —— 之前的
旧面板里就是 ŷ = T̂ + Ŝ + Ĉ + R̂ 四分量 + 方向 + 尖峰预警，这些不能丢。

四分量是真跑模型得到的，不是编的：
  - 用事件自身的 28 天窗口（log1p + 事件自身 scaler，避免全网尺度不匹配）
  - 调 predict_window，取返回的 components
  - 同时取 direction_delta / spike_gain 两个模型侧指标

注意：模型的绝对精度在事件上不好（已实测 MAPE≈1），所以这里只把四分量当作
"模型如何解释这段曲线"的定性分解，不宣称它是精确预测。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(r"D:\HuaweiMoveData\Users\32002\Desktop\social-sense")
EV = ROOT / "social_forecast" / "data" / "events"
sys.path.insert(0, str(ROOT))


def main() -> None:
    from workflow.forecast_ai.adapter import load_forecast_model

    model = load_forecast_model()
    bundle = model.bundle
    seq_len = int(bundle.seq_len)
    pred_len = int(bundle.pred_len)
    print(f"  模型: seq_len={seq_len} pred_len={pred_len}")

    out = {}
    ok = fail = 0
    for f in sorted(EV.glob("*.csv")):
        if f.stem.startswith("_"):
            continue
        eid = f.stem
        df = pd.read_csv(f, parse_dates=["date"])
        y = df["volume"].to_numpy(dtype=float)
        if len(y) < seq_len:
            print(f"  · {eid}: 序列仅 {len(y)} 天，不足 {seq_len}，跳过")
            fail += 1
            continue

        pk = int(y.argmax())
        start = max(0, min(pk - seq_len // 2, len(y) - seq_len))
        window_raw = y[start : start + seq_len]
        window = np.log1p(window_raw)

        old_mean = np.array(bundle.scaler_mean, copy=True)
        old_scale = np.array(bundle.scaler_scale, copy=True)
        try:
            bundle.scaler_mean = np.asarray([float(window.mean())])
            bundle.scaler_scale = np.asarray([float(window.std()) or 1.0])
            r = model.predict(window, t0=start)
        except Exception as e:  # noqa: BLE001
            print(f"  ✗ {eid}: 推理失败 {type(e).__name__}: {str(e)[:70]}")
            fail += 1
            continue
        finally:
            bundle.scaler_mean = old_mean
            bundle.scaler_scale = old_scale

        comps = r.get("components") or {}
        comp = {}
        for k in ("T", "S", "C", "R"):
            arr = comps.get(k)
            if arr is None:
                comp[k] = []
                continue
            comp[k] = [round(float(v), 4) for v in np.atleast_1d(np.asarray(arr, dtype=float)).ravel()]

        out[eid] = {
            "event_id": eid,
            "window_start": int(start),
            "window_dates": [
                str(pd.Timestamp(df["date"].iloc[i]).date()) for i in range(start, start + seq_len)
            ],
            "window_volume": [round(float(v), 2) for v in window_raw],
            "window_log": [round(float(v), 4) for v in window],
            "components": comp,
            "component_scale": "标准化空间（与模型内部一致，非声量绝对值）",
            "yhat_raw": [round(float(v), 2) for v in np.atleast_1d(np.asarray(r.get("yhat_raw"), dtype=float)).ravel()],
            "direction_delta": round(float(r.get("direction_delta") or 0.0), 4),
            "spike_gain": round(float(r.get("spike_gain") or 0.0), 4),
            "fire": round(float(r.get("fire") or 0.0), 4),
            "model": {
                "name": "RepMoE (lite, pl6, L28)",
                "checkpoint": str(bundle.__class__.__name__),
                "seq_len": seq_len,
                "pred_len": pred_len,
                "scaler": "事件自身窗口的 log1p 统计量",
            },
            "caveat": "四分量表示模型如何分解这段曲线，属定性解释；事件上绝对精度有限。",
        }
        ok += 1

    (EV / "_components.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"  完成 {ok} 个，失败 {fail} 个 → _components.json")

    # 抽一个事件展示分量形状
    sample = "sanhai" if "sanhai" in out else next(iter(out))
    c = out[sample]["components"]
    print(f"\n  示例 {sample} 的四分量（前 6 步）:")
    for k in ("T", "S", "C", "R"):
        print(f"    {k}: {c[k][:6]}")


if __name__ == "__main__":
    main()
