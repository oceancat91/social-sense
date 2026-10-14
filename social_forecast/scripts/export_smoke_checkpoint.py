"""Export a lightweight smoke checkpoint without full training.

Builds Model (+ optional empty DSSAA weights skipped) with default lite config,
fits scaler on SocialMedia_log train split, optionally runs a few Adam steps
on pure-TS so the file is non-trivial — then saves via checkpoint.save_checkpoint.

Usage (from social_forecast/):
  python -u scripts\\export_smoke_checkpoint.py
  python -u scripts\\export_smoke_checkpoint.py --steps 0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from checkpoint import DEFAULT_CKPT_DIR, save_checkpoint  # noqa: E402
from models.a import Model  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="SocialMedia_log")
    ap.add_argument("--seq_len", type=int, default=28)
    ap.add_argument("--pred_len", type=int, default=6)
    ap.add_argument("--seasonal_period", type=int, default=7)
    ap.add_argument("--capacity", default="lite")
    ap.add_argument("--steps", type=int, default=3,
                    help="tiny Adam steps on last train window (0=init only)")
    ap.add_argument("--out", type=str, default="")
    args = ap.parse_args()

    csv_path = ROOT / "data" / f"{args.dataset}.csv"
    if not csv_path.exists():
        raise SystemExit(f"missing data: {csv_path}")

    import pandas as pd
    df = pd.read_csv(csv_path)
    raw = df["OT"].values.astype(np.float64).reshape(-1, 1)
    n = len(raw)
    n_train = int(n * 0.7)
    scaler = StandardScaler().fit(raw[:n_train])
    y = scaler.transform(raw).astype(np.float32).reshape(-1)

    cfg = SimpleNamespace(
        task_name="long_term_forecast",
        seq_len=args.seq_len, pred_len=args.pred_len, enc_in=1,
        d_ff=64, ema_alpha=0.05, ema_adapt="series", ema_learnable=True,
        seasonal_periods=args.seasonal_period, fourier_K=3, seasonal_adaptive=False,
        jump_hidden=32, jump_theta=0.5, jump_pos_weight=5.0,
        use_ds_saa=False, ds_saa_dim=64,
        c_mode="response", response_K=3, resid_n_bands=4,
        t_head="residual", trend_mode="mix", text_scale_gate=True,
        use_enc_T=False, use_enc_eq=False,
    )
    device = torch.device("cpu")  # smoke: always CPU to avoid GPU heat
    model = Model(cfg).to(device)
    model.decomp.fit_alpha(torch.from_numpy(y[:n_train]))

    if args.steps > 0 and n_train > args.seq_len + args.pred_len:
        # few steps on a single window — not a real train, just non-zero grads
        i0 = n_train - args.seq_len - args.pred_len
        x = torch.from_numpy(y[i0:i0 + args.seq_len]).view(1, -1, 1).to(device)
        yt = torch.from_numpy(
            y[i0 + args.seq_len:i0 + args.seq_len + args.pred_len]
        ).view(1, -1, 1).to(device)
        t = torch.arange(i0, i0 + args.seq_len, dtype=torch.float32).view(1, -1)
        opt = torch.optim.Adam(model.parameters(), lr=1e-3)
        loss_fn = nn.MSELoss()
        for _ in range(args.steps):
            T_hat, _, _ = model.forecast_trend(x)
            r1, _ = model.decomp(x)
            S_hat = model.forecast_seasonal(r1, t)
            _, _, _, r2, R, _ = model.decompose(x, t=t)
            R_hat = model.forecast_residual(R)
            yhat = T_hat + S_hat + R_hat
            loss = loss_fn(yhat, yt)
            opt.zero_grad()
            loss.backward()
            opt.step()
        print(f"[smoke] tiny-train steps={args.steps} last_loss={float(loss.detach()):.6f}")

    out = Path(args.out) if args.out else (
        DEFAULT_CKPT_DIR / f"{args.dataset}_{args.capacity}_pl{args.pred_len}_L{args.seq_len}_smoke.pt"
    )
    save_checkpoint(
        out,
        model=model,
        dssaa=None,
        configs=cfg,
        scaler_mean=scaler.mean_.tolist(),
        scaler_scale=scaler.scale_.tolist(),
        gate={
            "silent_C": True,
            "drop": ["T", "S", "R"],
            "theta": 0.5,
            "support_gate": False,
            "smoke": True,
        },
        response_lib={"bps": [], "snippets": [], "K": 0,
                      "templates": None, "centers": None},
        domain=args.dataset,
        capacity=args.capacity,
        metrics={"note": "smoke checkpoint — not a full e2e train"},
        extra={"smoke": True, "n_train": n_train},
    )
    print(f"[smoke] wrote {out}")
    print(f"[smoke] meta  {out.with_suffix('.meta.json')}")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
