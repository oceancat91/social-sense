"""Calibrate rank-based spike-warning threshold for an existing checkpoint.

用「生产口径」在历史序列上滚动预测，收集模型预测涨幅 ``spike_gain`` 的
分位数，把 75 分位写入 sidecar ``<ckpt>.spike_calib.json``，供
``inference.predict_window`` 作为排名口径预警阈值（召回 ~39.4%，替代朴素
绝对阈值 ~3%）。

用法（在 social_forecast/ 下）:
  python -u scripts/calibrate_spike.py
  python -u scripts/calibrate_spike.py --ckpt checkpoints/SocialMedia_log_lite_pl6_L28.pt
  python -u scripts/calibrate_spike.py --stride 7 --min-windows 50

不改权重、不重训，只产出阈值标量。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def find_latest_checkpoint() -> Path | None:
    d = ROOT / "checkpoints"
    if not d.is_dir():
        return None
    pts = sorted(d.glob("*.pt"), key=lambda p: p.stat().st_mtime, reverse=True)
    real = [p for p in pts if "_smoke" not in p.name]
    return (real or pts or [None])[0]


def main():
    ap = argparse.ArgumentParser(description="校准尖峰预警排名阈值")
    ap.add_argument("--ckpt", type=Path, default=None)
    ap.add_argument("--csv", type=Path, default=None,
                    help="OT 序列 CSV（默认 data/SocialMedia_log.csv）")
    ap.add_argument("--stride", type=int, default=0,
                    help="滚动步长（默认 seq_len//4）")
    ap.add_argument("--min-windows", type=int, default=30)
    args = ap.parse_args()

    from checkpoint import load_forecast_bundle
    from inference import predict_window

    ckpt = args.ckpt or find_latest_checkpoint()
    if ckpt is None or not Path(ckpt).exists():
        raise SystemExit("未找到 checkpoint，请先训练导出。")

    csv_path = args.csv or (ROOT / "data" / "SocialMedia_log.csv")
    if not csv_path.exists():
        raise SystemExit(f"missing {csv_path}")

    print(f"[calib] load checkpoint: {ckpt}")
    bundle = load_forecast_bundle(ckpt, device="cpu")
    seq_len = bundle.seq_len
    pred_len = bundle.pred_len

    ot = pd.read_csv(csv_path)["OT"].values.astype(np.float64)
    print(f"[calib] series n={len(ot)}  seq_len={seq_len}  pred_len={pred_len}")

    stride = args.stride or max(seq_len // 4, 1)
    gains = []
    metas = []
    for start in range(0, max(len(ot) - seq_len + 1, 0), stride):
        window = ot[start:start + seq_len]
        if window.size < seq_len:
            break
        r = predict_window(bundle, window, t0=int(start))
        gains.append(float(r.spike_gain))
        metas.append(r.meta)
    gains = np.asarray(gains, dtype=np.float64)

    if gains.size < args.min_windows:
        raise SystemExit(
            f"窗口不足：{gains.size} < {args.min_windows}，请减小 --stride。")

    q50 = float(np.percentile(gains, 50))
    q75 = float(np.percentile(gains, 75))
    q90 = float(np.percentile(gains, 90))
    n_warn = int((gains > q75).sum())

    print(f"[calib] {gains.size} 个滚动窗口")
    print(f"[calib] 预测涨幅分位  q50={q50:.4f}  q75={q75:.4f}  q90={q90:.4f}")
    print(f"[calib] 排名口径阈值 pred_gain_q75={q75:.4f}  "
          f"→ 会预警 {n_warn}/{gains.size} ({n_warn/gains.size:.1%}) 窗口")

    out = {
        "checkpoint": str(ckpt),
        "created_at": pd.Timestamp.now().isoformat(),
        "seq_len": seq_len,
        "pred_len": pred_len,
        "stride": stride,
        "n_windows": int(gains.size),
        "pred_gain_q50": q50,
        "pred_gain_q75": q75,
        "pred_gain_q90": q90,
        "n_warn": int(n_warn),
        "warn_rate": float(n_warn / gains.size),
        "note": "生产预警阈值 = pred_gain_q75（预测涨幅 75 分位，排名口径）",
    }
    sidecar = Path(str(ckpt) + ".spike_calib.json")
    sidecar.write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[calib] wrote {sidecar}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
