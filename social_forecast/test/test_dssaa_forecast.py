"""Trial run: pure-TS staged pretrain → DS-SAA stage2/3 with cached text embeds.

Usage:
  python test/test_dssaa_forecast.py Climate --pred_len 6
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from models.a import Model  # noqa: E402
from layers.jump_pelt import detect_jumps  # noqa: E402
from layers.ds_saa import COMPONENTS, DSSAAModule  # noqa: E402
from layers.ds_saa_semantic import (  # noqa: E402
    DualSourceSemanticSpace,
    ExoEventBatch,
    encode_exo_events,
    load_gpt2_encoder,
)

SEQ_LEN = 8
PRED_LEN = 6
BATCH = 16
# slightly shorter than full TS script for a first DS-SAA trial
EPOCHS_T, EPOCHS_J, EPOCHS_R = 30, 20, 30
EPOCHS_S2, EPOCHS_S3 = 15, 10
LR, LR_S2, LR_S3 = 1e-3, 1e-3, 1e-4
ORTH_W = 0.05
ROUTE_W = 0.1
D_SAA = 64
MAX_EVENTS = 6
SEED = 2025


def continue_ema(t_last, y_fut, alpha):
    outs, t = [], t_last
    for i in range(y_fut.size(1)):
        t = alpha * y_fut[:, i] + (1.0 - alpha) * t
        outs.append(t)
    return torch.stack(outs, dim=1)


def load_pack(csv_path: Path):
    df = pd.read_csv(csv_path)
    y = df['OT'].values.astype(np.float64).reshape(-1, 1)
    n = len(y)
    n_train, n_test = int(n * 0.7), int(n * 0.2)
    n_val = n - n_train - n_test
    scaler = StandardScaler().fit(y[:n_train])
    y = scaler.transform(y).astype(np.float32)
    if 'fact' in df.columns:
        facts = df['fact'].fillna('').astype(str).tolist()
    else:
        facts = [''] * n
    if 'date' in df.columns:
        dates = [str(d)[:10] for d in df['date'].tolist()]
    elif 'Date' in df.columns:
        dates = [str(d)[:10] for d in df['Date'].tolist()]
    else:
        dates = [f'1970-01-{(i % 28) + 1:02d}' for i in range(n)]
    borders = {
        'train': (0, n_train),
        'val': (n_train - SEQ_LEN, n_train + n_val),
        'test': (n - n_test - SEQ_LEN, n),
    }
    return y, facts, dates, borders, n_train


def make_windows(y, facts, dates, border1, border2):
    seg = y[border1:border2]
    xs, ys, ts, fi, di = [], [], [], [], []
    tot = len(seg) - SEQ_LEN - PRED_LEN + 1
    for i in range(max(tot, 0)):
        abs_begin = border1 + i
        abs_end = abs_begin + SEQ_LEN - 1  # forecast origin
        xs.append(seg[i:i + SEQ_LEN])
        ys.append(seg[i + SEQ_LEN:i + SEQ_LEN + PRED_LEN])
        ts.append(np.arange(abs_begin, abs_begin + SEQ_LEN, dtype=np.float32))
        # aggregate facts across the WHOLE input window (not just the origin
        # step) so sparse news is not dropped; parse_fact_documents re-splits
        # them and date2idx anchors each document to its own step.
        win_facts = [facts[abs_begin + j] for j in range(SEQ_LEN)]
        fi.append('\n'.join(f for f in win_facts if f and str(f).strip()))
        di.append(dates[abs_begin:abs_begin + SEQ_LEN])
    return (
        torch.from_numpy(np.stack(xs)),
        torch.from_numpy(np.stack(ys)),
        torch.from_numpy(np.stack(ts)),
        fi, di,
    )


def load_pack_prior(csv_path: Path):
    """load_pack + ``prior_history_avg`` (the long-run seasonal prior the LLM
    knows).  This is the *historical knowledge* text/feature that the numeric
    model (an 8-step window + Fourier) cannot see, and is the true extra signal
    behind the "text helps" story.  Returns prior scaled with the SAME scaler
    as ``y`` so the two live on one scale."""
    y, facts, dates, borders, n_train = load_pack(csv_path)
    df = pd.read_csv(csv_path)
    prior = None
    if 'prior_history_avg' in df.columns:
        raw = df['prior_history_avg'].values.astype(np.float64).reshape(-1, 1)
        scaler = StandardScaler().fit(raw[:n_train])
        prior = scaler.transform(raw).astype(np.float32)
    return y, facts, dates, borders, n_train, prior


def make_windows_prior(y, prior, facts, dates, border1, border2):
    """make_windows + window ``prior`` aggregation (kept as exact numeric
    features; the LLM's *historical knowledge* is too precise for GPT-2 to
    re-encode as text, so we inject it numerically)."""
    seg = y[border1:border2]
    pseg = prior[border1:border2] if prior is not None else None
    xs, ys, ts, fi, di, pri = [], [], [], [], [], []
    tot = len(seg) - SEQ_LEN - PRED_LEN + 1
    for i in range(max(tot, 0)):
        abs_begin = border1 + i
        xs.append(seg[i:i + SEQ_LEN])
        ys.append(seg[i + SEQ_LEN:i + SEQ_LEN + PRED_LEN])
        ts.append(np.arange(abs_begin, abs_begin + SEQ_LEN, dtype=np.float32))
        win_facts = [facts[abs_begin + j] for j in range(SEQ_LEN)]
        fi.append('\n'.join(f for f in win_facts if f and str(f).strip()))
        di.append(dates[abs_begin:abs_begin + SEQ_LEN])
        if pseg is not None:
            pri.append(pseg[i:i + SEQ_LEN])
    pri_t = torch.from_numpy(np.stack(pri)) if pri else None
    return (
        torch.from_numpy(np.stack(xs)),
        torch.from_numpy(np.stack(ys)),
        torch.from_numpy(np.stack(ts)),
        fi, di, pri_t,
    )


@torch.no_grad()
def precompute_text(semantic, dssaa, xs, facts, dates, device, tag: str):
    """Cache H_endo + exo events for all samples (encode once).

    Also caches shared pool ``ALL`` (non-noise docs + weak route labels) for SRSA.
    """
    STRUCT_KEYS = ('target', 'intensity', 'duration', 'shape', 'confidence')

    def _pack_ev(ev):
        out = {
            'V': ev.V.detach().cpu(),
            'pos': ev.pos.detach().cpu(),
            'mask': ev.mask.detach().cpu(),
            'quality': ev.quality.detach().cpu(),
            'route_label': (ev.route_label if ev.route_label is not None
                            else torch.full(ev.mask.shape, -1, dtype=torch.long)
                            ).detach().cpu(),
        }
        for k in STRUCT_KEYS:
            t = getattr(ev, k, None)
            out[k] = None if t is None else t.detach().cpu()
        return out

    N = xs.size(0)
    # 小 batch + 定期清缓存，避免 GPT-2 编码把显卡打满导致黑屏/驱动重置
    import os as _os
    bs = int(_os.environ.get("TEXT_CACHE_BS", "2"))
    print(f'[text-cache] {tag}: N={N}  encode_bs={bs} ...')
    H = {c: [] for c in COMPONENTS}
    Hx = {c: [] for c in COMPONENTS}
    fp = []  # raw full-document pool (linear-probe feature)
    keys = list(COMPONENTS) + (['ALL'] if getattr(dssaa, 'use_srsa', False) else [])
    exo = {c: {k: [] for k in
               ['V', 'pos', 'mask', 'quality', 'route_label'] + list(STRUCT_KEYS)}
           for c in keys}
    mask_exo = []
    for i0 in range(0, N, bs):
        i1 = min(N, i0 + bs)
        windows = [xs[j, :, 0].numpy() for j in range(i0, i1)]
        fbatch = facts[i0:i1]
        dbatch = dates[i0:i1]
        with torch.no_grad():
            bundle = semantic(windows, fbatch, device=device, window_dates=dbatch)
            for c in COMPONENTS:
                H[c].append(bundle.H_endo[c].detach().cpu())
                Hx[c].append(bundle.H_exo[c].detach().cpu())
            # raw full-doc pool (no instruction) for the direct text→delta head
            d_enc = semantic.encoder.d_model
            pool = torch.zeros(len(fbatch), d_enc, device=device)
            nz = [j for j, f in enumerate(fbatch) if f and str(f).strip()]
            if nz:
                pool[nz] = semantic.encoder.encode(
                    [str(fbatch[j]) for j in nz], device=device)
            fp.append(pool.detach().cpu())
            mask_exo.append(bundle.mask_exo.detach().cpu())
            for c in COMPONENTS:
                ev = encode_exo_events(
                    semantic.encoder, fbatch, c, SEQ_LEN,
                    window_dates=dbatch, max_events=MAX_EVENTS, device=device,
                    pred_len=PRED_LEN)
                packed = _pack_ev(ev)
                for k, v in packed.items():
                    if v is not None:
                        exo[c][k].append(v)
            if 'ALL' in exo:
                ev = encode_exo_events(
                    semantic.encoder, fbatch, 'ALL', SEQ_LEN,
                    window_dates=dbatch, max_events=MAX_EVENTS, device=device,
                    pred_len=PRED_LEN, route_filter='all')
                packed = _pack_ev(ev)
                for k, v in packed.items():
                    if v is not None:
                        exo['ALL'][k].append(v)
        if device.type == "cuda":
            torch.cuda.empty_cache()
        if (i0 // bs) % 20 == 0:
            print(f'  {tag} {i1}/{N}')

    def cat_field(store, key):
        seq = store[key]
        if not seq:
            return None
        return torch.cat(seq, 0)

    cache = {
        'H_endo': {c: torch.cat(H[c], 0) for c in COMPONENTS},
        'H_exo': {c: torch.cat(Hx[c], 0) for c in COMPONENTS},
        'fact_pool': torch.cat(fp, 0),
        'mask_exo': torch.cat(mask_exo, 0),
        'exo': {
            c: {k: cat_field(exo[c], k) for k in exo[c]}
            for c in keys
        },
    }
    print(f'[text-cache] {tag} done. exo_rate='
          f'{float(cache["mask_exo"].mean()):.3f}')
    if 'ALL' in cache['exo']:
        print(f'  ALL exo occupancy='
              f'{float(cache["exo"]["ALL"]["mask"].mean()):.4f}')
    return cache


def _batch_to_exo(store, idx, device, V):
    def take(name):
        t = store.get(name)
        if t is None:
            return None
        return t[idx].to(device)
    return ExoEventBatch(
        V=V,
        pos=take('pos'),
        mask=take('mask'),
        quality=take('quality'),
        route_label=take('route_label'),
        target=take('target'),
        intensity=take('intensity'),
        duration=take('duration'),
        shape=take('shape'),
        confidence=take('confidence'),
    )


def gather_cache(cache, idx, device, dssaa):
    H_endo = {c: cache['H_endo'][c][idx].to(device) for c in COMPONENTS}
    H_exo = ({c: cache['H_exo'][c][idx].to(device) for c in COMPONENTS}
             if 'H_exo' in cache else None)
    fact_pool = (cache['fact_pool'][idx].to(device)
                 if 'fact_pool' in cache else None)
    mask_exo = cache['mask_exo'][idx].to(device)
    exo_by = {}
    for c in COMPONENTS:
        V = cache['exo'][c]['V'][idx].to(device)
        if dssaa.exo_proj is not None:
            V = dssaa.exo_proj[c](V)
        exo_by[c] = _batch_to_exo(cache['exo'][c], idx, device, V)
    if 'ALL' in cache['exo']:
        V = cache['exo']['ALL']['V'][idx].to(device)
        proj = getattr(dssaa, 'exo_proj_shared', None)
        if proj is not None:
            V = proj(V)
        elif dssaa.exo_proj is not None:
            V = dssaa.exo_proj['T'](V)
        exo_by['ALL'] = _batch_to_exo(cache['exo']['ALL'], idx, device, V)
    return H_endo, exo_by, mask_exo, H_exo, fact_pool


@torch.no_grad()
def eval_mse(model, xs, ys, ts, device, cache=None, dssaa=None, use_text=False):
    model.eval()
    loader = DataLoader(
        TensorDataset(
            xs, ys, ts,
            torch.arange(xs.size(0))),
        batch_size=BATCH, shuffle=False)
    se = ae = n = 0.0
    persist_se = 0.0
    for x, y, t, idx in loader:
        x, y, t = x.to(device), y.to(device), t.to(device)
        idx = idx.tolist()
        T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
        H_T = H_S = H_C = H_R = None
        gS = gC = gR = None
        if use_text and cache is not None and dssaa is not None:
            H_endo, exo_by, mask_exo, _, _ = gather_cache(cache, idx, device, dssaa)
            out = dssaa.enhance(T, S, r2, R, H_endo, exo_by, mask_exo)
            H_T, H_S = out.H_fusion['T'], out.H_fusion['S']
            H_C, H_R = out.H_fusion['C'], out.H_fusion['R']
            gS, gC, gR = out.gates['S'], out.gates['C'], out.gates['R']
        T_hat, _, _ = model.forecast_trend(x, H_T=H_T)
        S_hat = model.forecast_seasonal(r1, t, S_hist=S, H_S=H_S, gate_S=gS)
        C_hat, _ = model.forecast_jump(r2, C_hist, H_C=H_C, gate_C=gC)
        R_hat = model.forecast_residual(R, H_R=H_R, gate_R=gR)
        yhat = T_hat + S_hat + C_hat + R_hat
        persist = x[:, -1:].expand_as(y)
        se += ((yhat - y) ** 2).sum().item()
        ae += (yhat - y).abs().sum().item()
        persist_se += ((persist - y) ** 2).sum().item()
        n += y.numel()
    return se / n, ae / n, persist_se / n


def train_ts_backbone(model, loaders, n_train, y_all, borders, device):
    loss_fn = nn.MSELoss()
    with torch.no_grad():
        y_tr = torch.from_numpy(y_all[:n_train]).unsqueeze(0).to(device)
        t_tr = torch.arange(n_train, device=device, dtype=torch.float32)
        r1_tr, _ = model.decomp(y_tr)
        model.seasonal.fit_std(r1_tr)
        model.seasonal.fit_least_squares(r1_tr, t=t_tr)

    # Both trend heads are trained on their own output (plain ΔMLP and the
    # scale-equivariant ΔMLP_eq); the scale-OOD mix is only used downstream
    # once fit_scale_gate() has been called.
    eq_params = list(getattr(model, 'delta_mlp_eq', nn.Identity()).parameters())
    # NOTE: the shape reservoir (enc_T_eq / enc_T / ...) is intentionally NOT
    # in opt_t — it is a fixed random projection (reservoir) whose parameters
    # are never trained (see models/a.py, forecast_trend uses no_grad on it).
    opt_t = torch.optim.Adam(
        list(model.decomp.parameters()) + list(model.delta_mlp.parameters()) + eq_params,
        lr=LR)
    for ep in range(1, EPOCHS_T + 1):
        model.train(); tot = n = 0
        a = model.decomp.alpha
        for x, yb, t, _ in loaders['train']:
            x, yb = x.to(device), yb.to(device)
            T_hat, _, T = model.forecast_trend(x)
            target = continue_ema(T[:, -1].detach(), yb, a.detach())
            if getattr(model, '_T_hat_eq', None) is not None:
                loss = loss_fn(model._T_hat_plain, target) + loss_fn(model._T_hat_eq, target)
            else:
                loss = loss_fn(T_hat, target)
            opt_t.zero_grad(); loss.backward(); opt_t.step()
            tot += loss.item() * x.size(0); n += x.size(0)
        if ep % 10 == 0 or ep == 1:
            print(f'[trend] ep{ep:03d} mse={tot / n:.6f}')
    if hasattr(model, 'fit_scale_gate'):
        model.fit_scale_gate(loaders['train'].dataset.tensors[0].to(device))
        print(f'[trend] scale gate: log_ref={float(model.scale_log_ref):.3f} '
              f'tau={float(model.scale_tau):.3f}')

    with torch.no_grad():
        y_full = torch.from_numpy(y_all).unsqueeze(0).to(device)
        t_full = torch.arange(len(y_all), device=device, dtype=torch.float32)
        r1_f, _ = model.decomp(y_full)
        r2_f, _ = model.seasonal(r1_f, t=t_full)
        r2_np = r2_f.squeeze().cpu().numpy()
        n_all = len(y_all)
        n_test = int(n_all * 0.2)
        n_val = n_all - n_train - n_test
        C_full = np.zeros(n_all, dtype=np.float32)
        C_tr, bps, events = detect_jumps(r2_np[:n_train], period=12, w_min=3)
        C_full[:n_train] = C_tr.astype(np.float32)
        if n_val > SEQ_LEN + PRED_LEN:
            C_va, _, _ = detect_jumps(r2_np[n_train:n_train + n_val], period=12, w_min=3)
            C_full[n_train:n_train + n_val] = C_va.astype(np.float32)
        if n_test > SEQ_LEN + PRED_LEN:
            C_te, _, _ = detect_jumps(r2_np[n_train + n_val:], period=12, w_min=3)
            C_full[n_train + n_val:] = C_te.astype(np.float32)
        model.set_jump_series(torch.from_numpy(C_full).unsqueeze(-1).to(device))
        print(f'[jump] events={len(events)} nnz={int((np.abs(C_full) > 1e-8).sum())}/{n_all}')

    opt_j = torch.optim.Adam(model.jump.parameters(), lr=LR)
    for ep in range(1, EPOCHS_J + 1):
        model.train(); tot = n = 0
        for x, yb, t, _ in loaders['train']:
            x, t = x.to(device), t.to(device)
            keep = (t[:, -1] + PRED_LEN) < n_train
            if keep.sum() < 1:
                continue
            x, t = x[keep], t[keep]
            with torch.no_grad():
                _, _, _, r2, _, C_hist = model.decompose(x, t=t)
                C_fut = model.gather_C_future(t)
                y_evt = (C_fut.abs() > 1e-8).float()
            p, amp_log = model.jump.forward_probs_amps(r2, C_hist)
            loss = model.jump.loss_cls(p, y_evt) + model.jump.loss_amp(amp_log, C_fut, y_evt)
            opt_j.zero_grad(); loss.backward(); opt_j.step()
            tot += loss.item() * x.size(0); n += x.size(0)
        if ep % 10 == 0 or ep == 1:
            print(f'[jump] ep{ep:03d} loss={tot / max(n, 1):.6f}')

    # residual
    model.eval()
    R_list = []
    with torch.no_grad():
        for x, yb, t, _ in loaders['train']:
            x, t = x.to(device), t.to(device)
            _, _, _, _, R, _ = model.decompose(x, t=t)
            R_list.append(R.cpu())
    R_train = torch.cat(R_list, 0)
    model.mamba.fit_norm(R_train.to(device))
    wn = model.mamba.maybe_deactivate_white_noise(R_train)
    print(f'[resid] white_noise={wn} active={int(model.mamba.active)}')
    if int(model.mamba.active.item()) == 1:
        opt_r = torch.optim.Adam(model.mamba.parameters(), lr=LR)
        best_val, best_state = float('inf'), None
        for ep in range(1, EPOCHS_R + 1):
            model.train(); tot = n = 0
            a = model.decomp.alpha.detach()
            for x, yb, t, _ in loaders['train']:
                x, yb, t = x.to(device), yb.to(device), t.to(device)
                with torch.no_grad():
                    _, r1, T = model.forecast_trend(x)
                    T_true = continue_ema(T[:, -1], yb, a)
                    steps = torch.arange(1, PRED_LEN + 1, device=t.device, dtype=t.dtype)
                    S_fut = model.seasonal.forecast(t[:, -1:] + steps.unsqueeze(0))
                    C_fut = model.gather_C_future(t)
                    R_true = yb - T_true - S_fut - C_fut
                    _, _, _, _, R_hist, _ = model.decompose(x, t=t)
                loss = loss_fn(model.forecast_residual(R_hist), R_true)
                opt_r.zero_grad(); loss.backward(); opt_r.step()
                tot += loss.item() * x.size(0); n += x.size(0)
            mse, _, _ = eval_mse(model, *pack_xy(loaders['val']), device)
            if mse < best_val:
                best_val = mse
                best_state = {k: v.detach().cpu().clone()
                              for k, v in model.mamba.state_dict().items()}
            if ep % 10 == 0 or ep == 1:
                print(f'[mamba] ep{ep:03d} train={tot / n:.6f} val={mse:.6f}')
        if best_state is not None:
            model.mamba.load_state_dict(best_state)


def pack_xy(loader):
    """Recover tensors from a loader built as TensorDataset(x,y,t,idx)."""
    xs, ys, ts = [], [], []
    for x, y, t, _ in loader:
        xs.append(x); ys.append(y); ts.append(t)
    return torch.cat(xs), torch.cat(ys), torch.cat(ts)


def predict_batch(model, x, t, H_T=None, H_S=None, H_C=None, H_R=None,
                  gS=None, gC=None, gR=None):
    T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
    T_hat, _, _ = model.forecast_trend(x, H_T=H_T)
    S_hat = model.forecast_seasonal(r1, t, S_hist=S, H_S=H_S, gate_S=gS)
    C_hat, _ = model.forecast_jump(r2, C_hist, H_C=H_C, gate_C=gC)
    R_hat = model.forecast_residual(R, H_R=H_R, gate_R=gR)
    return T_hat + S_hat + C_hat + R_hat, (T, S, r2, R)


def main(dataset: str, pred_len: int = 6, calendar_mode: str = "short",
         encoder=None):
    global PRED_LEN
    PRED_LEN = int(pred_len)
    torch.manual_seed(SEED)
    np.random.seed(SEED)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f'=== DS-SAA trial  {dataset}  seq={SEQ_LEN} pred={PRED_LEN}  '
          f'calendar={calendar_mode}  device={device} ===')

    y_all, facts_all, dates_all, borders, n_train = load_pack(
        ROOT / 'data' / f'{dataset}.csv')

    packs = {}
    for split, (b1, b2) in borders.items():
        x, fut, t, fi, di = make_windows(y_all, facts_all, dates_all, b1, b2)
        idx = torch.arange(x.size(0))
        packs[split] = dict(x=x, y=fut, t=t, facts=fi, dates=di)
        print(f'  {split}: N={x.size(0)}')

    loaders = {
        split: DataLoader(
            TensorDataset(p['x'], p['y'], p['t'], torch.arange(p['x'].size(0))),
            batch_size=BATCH, shuffle=(split == 'train'))
        for split, p in packs.items()
    }

    cfg = SimpleNamespace(
        task_name='long_term_forecast',
        seq_len=SEQ_LEN, pred_len=PRED_LEN, enc_in=1,
        d_ff=64, ema_alpha=0.05, ema_adapt='series', ema_learnable=True,
        seasonal_periods=12, fourier_K=3, seasonal_adaptive=False,
        mamba_d_model=64, mamba_layers=2, mamba_d_state=16,
        jump_hidden=32, jump_theta=0.5, jump_pos_weight=5.0,
        use_ds_saa=True, ds_saa_dim=D_SAA,
    )
    model = Model(cfg).to(device)
    a0 = model.decomp.fit_alpha(torch.from_numpy(y_all[:n_train]))
    print(f'[ema] alpha={float(model.decomp.alpha):.4f} (fit={a0})')

    # ---- stage 1: pure TS ----
    print('---- stage 1: pure-TS backbone ----')
    train_ts_backbone(model, loaders, n_train, y_all, borders, device)
    mse0, mae0, p0 = eval_mse(model, packs['test']['x'], packs['test']['y'],
                              packs['test']['t'], device, use_text=False)
    print(f'[stage1 test] persist MSE={p0:.6f}  TSR MSE={mse0:.6f} MAE={mae0:.6f}')

    # ---- attach DS-SAA + cache text ----
    print('---- load GPT2 + cache text embeds ----')
    enc = encoder if encoder is not None else load_gpt2_encoder(device=device)
    semantic = DualSourceSemanticSpace(
        enc, proj_dim=D_SAA, pred_len=PRED_LEN,
        calendar_mode=calendar_mode).to(device)
    dssaa = DSSAAModule(
        d_model=D_SAA, seq_len=SEQ_LEN, n_vars=1, semantic=semantic,
        max_events=MAX_EVENTS,
    ).to(device)
    model.attach_dssaa(dssaa)

    caches = {}
    for split in ('train', 'val', 'test'):
        caches[split] = precompute_text(
            semantic, dssaa, packs[split]['x'], packs[split]['facts'],
            packs[split]['dates'], device, tag=split)

    loss_fn = nn.MSELoss()

    # freeze backbone for stage 2
    for p in model.parameters():
        p.requires_grad = False
    for p in dssaa.parameters():
        p.requires_grad = True
    # also train text-fused trend head
    for p in model.delta_mlp_txt.parameters():
        p.requires_grad = True

    opt2 = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=LR_S2)
    print('---- stage 2: DS-SAA on TS residual ----')
    best_val, best_state = float('inf'), None
    for ep in range(1, EPOCHS_S2 + 1):
        model.train(); dssaa.train(); tot = n = 0
        for x, yb, t, idx in loaders['train']:
            x, yb, t = x.to(device), yb.to(device), t.to(device)
            idx = idx.tolist()
            with torch.no_grad():
                y_ts, (T, S, r2, R) = predict_batch(model, x, t, H_T=None)
                residual = yb - y_ts
            H_endo, exo_by, mask_exo, _, _ = gather_cache(caches['train'], idx, device, dssaa)
            # need grads through enhance; recompute T,S,r2,R with grad for query
            T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
            out = dssaa.enhance(T, S, r2, R, H_endo, exo_by, mask_exo)
            yhat, _ = predict_batch(
                model, x, t,
                H_T=out.H_fusion['T'], H_S=out.H_fusion['S'],
                H_C=out.H_fusion['C'], H_R=out.H_fusion['R'],
                gS=out.gates['S'], gC=out.gates['C'], gR=out.gates['R'])
            # fit residual of frozen TS + small orth + SRSA route CE
            loss = loss_fn(yhat, yb) + ORTH_W * out.L_orth
            if out.L_route is not None:
                loss = loss + ROUTE_W * out.L_route
            # encourage correcting residual
            loss = loss + 0.5 * loss_fn(yhat - y_ts.detach(), residual.detach())
            opt2.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            opt2.step()
            tot += loss.item() * x.size(0); n += x.size(0)
        vm, _, _ = eval_mse(
            model, packs['val']['x'], packs['val']['y'], packs['val']['t'],
            device, cache=caches['val'], dssaa=dssaa, use_text=True)
        if vm < best_val:
            best_val = vm
            best_state = {
                'dssaa': {k: v.detach().cpu().clone() for k, v in dssaa.state_dict().items()},
                'txt': {k: v.detach().cpu().clone()
                        for k, v in model.delta_mlp_txt.state_dict().items()},
            }
        if ep % 5 == 0 or ep == 1:
            print(f'[s2] ep{ep:03d} loss={tot / n:.6f} val={vm:.6f} best={best_val:.6f}')
    if best_state is not None:
        dssaa.load_state_dict(best_state['dssaa'])
        model.delta_mlp_txt.load_state_dict(best_state['txt'])

    mse2, mae2, _ = eval_mse(
        model, packs['test']['x'], packs['test']['y'], packs['test']['t'],
        device, cache=caches['test'], dssaa=dssaa, use_text=True)
    print(f'[stage2 test] TSR+text MSE={mse2:.6f} MAE={mae2:.6f}  (vs s1 {mse0:.6f})')

    # ---- stage 3: light e2e ----
    print('---- stage 3: e2e fine-tune ----')
    for p in model.parameters():
        p.requires_grad = True
    model.jump.freeze_cls_head(True)
    # keep LLM frozen
    for p in semantic.encoder.parameters():
        p.requires_grad = False
    opt3 = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=LR_S3)
    best_val, best_state = float('inf'), None
    for ep in range(1, EPOCHS_S3 + 1):
        model.train(); tot = n = 0
        model.jump.freeze_cls_head(True)
        for x, yb, t, idx in loaders['train']:
            x, yb, t = x.to(device), yb.to(device), t.to(device)
            idx = idx.tolist()
            T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
            H_endo, exo_by, mask_exo, _, _ = gather_cache(caches['train'], idx, device, dssaa)
            out = dssaa.enhance(T, S, r2, R, H_endo, exo_by, mask_exo)
            yhat, _ = predict_batch(
                model, x, t,
                H_T=out.H_fusion['T'], H_S=out.H_fusion['S'],
                H_C=out.H_fusion['C'], H_R=out.H_fusion['R'],
                gS=out.gates['S'], gC=out.gates['C'], gR=out.gates['R'])
            loss = loss_fn(yhat, yb) + ORTH_W * out.L_orth
            if out.L_route is not None:
                loss = loss + 0.1 * ROUTE_W * out.L_route
            opt3.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            opt3.step()
            tot += loss.item() * x.size(0); n += x.size(0)
        vm, _, _ = eval_mse(
            model, packs['val']['x'], packs['val']['y'], packs['val']['t'],
            device, cache=caches['val'], dssaa=dssaa, use_text=True)
        if vm < best_val:
            best_val = vm
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        if ep % 5 == 0 or ep == 1:
            print(f'[s3] ep{ep:03d} loss={tot / n:.6f} val={vm:.6f} best={best_val:.6f}')
    if best_state is not None:
        model.load_state_dict(best_state, strict=False)

    mse3, mae3, p3 = eval_mse(
        model, packs['test']['x'], packs['test']['y'], packs['test']['t'],
        device, cache=caches['test'], dssaa=dssaa, use_text=True)
    mse3b, _, _ = eval_mse(
        model, packs['test']['x'], packs['test']['y'], packs['test']['t'],
        device, use_text=False)
    print('==== summary (test) ====')
    print(f'  persist          MSE={p3:.6f}')
    print(f'  stage1 TS        MSE={mse0:.6f}  MAE={mae0:.6f}')
    print(f'  stage2 +text     MSE={mse2:.6f}  MAE={mae2:.6f}')
    print(f'  stage3 +text     MSE={mse3:.6f}  MAE={mae3:.6f}')
    print(f'  stage3 text-off  MSE={mse3b:.6f}')
    print('done.')
    return {
        'persist': p3, 'ts': mse0, 's2': mse2, 's3': mse3, 'text_off': mse3b,
        'mae_ts': mae0, 'mae_s3': mae3,
    }


ALL_DOMAINS = (
    'Agriculture', 'Climate', 'Economy', 'Economy_sort', 'Energy',
    'Environment', 'Health', 'Security', 'SocialGood', 'Traffic',
    'Weather', 'new_metr',
)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('datasets', nargs='*', default=['Climate'])
    ap.add_argument('--all', action='store_true', help='run every CSV domain')
    ap.add_argument('--pred_len', type=int, default=6)
    ap.add_argument('--calendar_mode', default='short',
                    choices=('off', 'short', 'full'),
                    help='off=repro pre-calendar; short=S-only one-line; full=verbose')
    args = ap.parse_args()
    names = list(ALL_DOMAINS) if args.all else list(args.datasets)
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    shared_enc = load_gpt2_encoder(device=device) if len(names) > 1 else None
    rows = []
    for name in names:
        try:
            r = main(name, args.pred_len, calendar_mode=args.calendar_mode,
                     encoder=shared_enc)
            rows.append((name, r))
        except Exception as exc:
            print(f'[FAIL] {name}: {type(exc).__name__}: {exc}')
            rows.append((name, None))
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    if len(names) > 1:
        print('\n========== ALL DOMAINS (test MSE) ==========')
        print(f'{"domain":16s} {"persist":>10s} {"TS":>10s} {"+text":>10s} {"text-off":>10s}')
        for name, r in rows:
            if r is None:
                print(f'{name:16s} FAIL')
            else:
                print(f'{name:16s} {r["persist"]:10.4f} {r["ts"]:10.4f} '
                      f'{r["s3"]:10.4f} {r["text_off"]:10.4f}')
