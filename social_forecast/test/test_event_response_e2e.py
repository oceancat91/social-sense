"""Full e2e for 方案二 EventResponse C + DS-SAA (routed T/C).

Usage:
  python test/test_event_response_e2e.py Security Climate --pred_len 6
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import importlib.util as _ilu


def _load_base():
    path = ROOT / "test" / "test_dssaa_forecast.py"
    spec = _ilu.spec_from_file_location("dssaa_base", path)
    mod = _ilu.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


base = _load_base()

from models.a import Model  # noqa: E402
from layers.event_response import (  # noqa: E402
    fit_response_library,
    fit_response_library_from_breakpoints,
)
from layers.ds_saa import DSSAAModule, COMPONENTS  # noqa: E402
from layers.ds_saa_semantic import (  # noqa: E402
    DualSourceSemanticSpace,
    ExoEventBatch,
    encode_exo_events,
    load_gpt2_encoder,
    parse_fact_documents,
)
from utils.text_route import route_document  # noqa: E402

OUT = ROOT / "test" / "results" / "event_response_e2e.csv"
CKPT_DIR = ROOT / "checkpoints"
EPOCHS_RESP = 30
TR_W = 0.2       # trust-region weight on text trend modulation
PP_W = 0.1       # point-process (fire / amplitude) supervision weight
T_ENDO = True    # endo window text → T (the Security-61 trend path)
SUPPORT_GATE = False  # train-support gate on the T residual (ablation)
T_HEAD = "residual"   # replace | residual (text residual on top of the numeric trend heads)
T_TIME_ONLY = False   # H_T without any text (numeric-level diagnostic)
TREND_MODE = "mix"    # mix | plain | eq  (scale-OOD trend ablation)
TEXT_SCALE_GATE = True  # multiply T text residual by (1-w)
FORCE_SILENT_C = False  # train/eval with C always off (C ablation)
USE_ENC_T = False      # augment plain trend head with Mamba-encoded branch
USE_ENC_EQ = False     # run Mamba encoder inside the equivariant head (ΔT/s)
EVAL_DIRECTION = False  # 方向命中率 + 尖峰预警评测（换口径，不拼 MSE）
C_NUMERIC = True       # 无外生事件时用数值 jump 头预测 C（让 C 参与纯数值预测）
SPIKE_W = 2.0          # 尖峰窗口的额外 loss 权重（对冲 MSE 保守压扁）
SPIKE_W_Q = 0.75       # 尖峰定义分位数（未来 P 天 max 涨幅 ≥ 训练集该分位 → 尖峰窗口）
SAVE_CKPT = True       # train 结束导出 checkpoint（架构零改动，只序列化权重）
CKPT_DIR_OVERRIDE = None  # Path | None


def c_point_process_loss(model, t, yb, exo_C, n_train):
    """Supervise the C trigger as a text-marked point process.

    Labels come from PELT jumps on the *training* r2 only (future window must
    lie inside the train split).  For windows with ≥1 routed event doc:
      BCE(p_fire, 1[∃ jump in horizon])  +  MSE(Ĉ, C_fut) on positives.
    """
    info = getattr(model, "_last_C_info", None)
    if not isinstance(info, dict) or "p_fire" not in info or exo_C is None:
        return yb.new_zeros(())
    keep = ((t[:, -1] + model.pred_len) < n_train)
    has_exo = exo_C.mask.sum(dim=-1) > 0
    sel = keep & has_exo
    if sel.sum() < 1:
        return yb.new_zeros(())
    with torch.no_grad():
        C_fut = model.gather_C_future(t)                      # [B,P,1]
        y_evt = (C_fut.abs().amax(dim=(1, 2)) > 1e-8).float()
    p = info["p_fire"].clamp(1e-4, 1 - 1e-4)
    bce = nn.functional.binary_cross_entropy(p[sel], y_evt[sel])
    curve = info["curve"] * info["fire"].view(-1, 1)           # [B,P]
    pos = sel & (y_evt > 0)
    amp = yb.new_zeros(())
    if pos.sum() > 0:
        amp = nn.functional.mse_loss(curve[pos], C_fut[pos, :, 0])
    return PP_W * (bce + amp)


def spike_sample_weight(yb, origin, thr):
    """尖峰窗口加权：未来 P 天 max 涨幅 ≥ 训练集分位阈值 → 权重 (1+SPIKE_W)。

    yb [B,P,1], origin [B,1,1]（预测原点的标准化值）, thr 为训练集 gain 分位。
    返回 [B] 权重，仅对尖峰窗口放大，非尖峰权重为 1。
    """
    gain = yb.amax(dim=1)[:, 0] - origin[:, 0, 0]        # [B]
    is_spike = (gain >= thr).to(yb.dtype)
    return 1.0 + SPIKE_W * is_spike


CAPACITY = {
    # 低负载：小 batch / 少 epoch，适合笔记本防黑屏
    "lite": dict(
        d_ff=64, ds_saa_dim=64, jump_hidden=32, response_K=3, fourier_K=3,
        resid_n_bands=4, max_events=4, epochs_resp=10,
        epochs_t=15, epochs_r=15, epochs_s2=8, epochs_s3=5, batch=4,
    ),
    "base": dict(
        d_ff=64, ds_saa_dim=64, jump_hidden=32, response_K=3, fourier_K=3,
        resid_n_bands=4, max_events=6, epochs_resp=30,
        epochs_t=30, epochs_r=30, epochs_s2=15, epochs_s3=10, batch=16,
    ),
    # ~2× base: wider trend MLP / DS-SAA / residual bands + larger random
    # shape reservoir (d_saa drives enc_T_eq width).
    "large": dict(
        d_ff=128, ds_saa_dim=128, jump_hidden=64, response_K=4, fourier_K=4,
        resid_n_bands=6, max_events=8, epochs_resp=30,
        epochs_t=30, epochs_r=30, epochs_s2=15, epochs_s3=10, batch=16,
    ),
    # ~4× base + extra text training: wider DS-SAA / text heads, more S2/S3
    # epochs so text pathways can actually use the capacity.
    "xlarge": dict(
        d_ff=256, ds_saa_dim=256, jump_hidden=128, response_K=5, fourier_K=5,
        resid_n_bands=8, max_events=10, epochs_resp=40,
        epochs_t=30, epochs_r=30, epochs_s2=25, epochs_s3=15, batch=16,
    ),
}


def predict_batch(model, x, t, H_T=None, H_S=None, H_C=None, H_R=None,
                  gS=None, gC=None, gR=None, exo_C=None, silent_C=False,
                  gT=None):
    T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
    T_hat, _, _ = model.forecast_trend(x, H_T=H_T, gate_T=gT)
    S_hat = model.forecast_seasonal(r1, t, S_hist=S, H_S=H_S, gate_S=gS)
    if silent_C:
        C_hat = x.new_zeros(x.size(0), model.pred_len, x.size(-1))
    else:
        model._exo_C = exo_C
        if exo_C is None:
            # 数值触发：无外生事件 → c_numeric fallback（jump 头）
            C_hat, _ = model.forecast_jump(
                r2, C_hist, H_C=None, gate_C=None,
                exo_V=None, exo_mask=None)
        else:
            C_hat, _ = model.forecast_jump(
                r2, C_hist, H_C=None, gate_C=None,
                exo_V=exo_C.V, exo_mask=exo_C.mask, exo_quality=exo_C.quality)
    R_hat = model.forecast_residual(R, H_R=H_R, gate_R=gR)
    return T_hat + S_hat + C_hat + R_hat, (T, S, r2, R)


@torch.no_grad()
def eval_mse(model, xs, ys, ts, device, cache=None, dssaa=None,
             use_text=False, silent_C=False, drop=None,
             zero_endo=False, zero_exo=False, diag=False):
    drop = set(drop or [])
    model.eval()
    loader = DataLoader(
        TensorDataset(xs, ys, ts, torch.arange(xs.size(0))),
        batch_size=base.BATCH, shuffle=False)
    se = ae = n = persist_se = 0.0
    fire_sum = fire_n = 0.0
    occ = {c: 0.0 for c in ("T", "S", "C", "R")}
    occ_n = 0.0
    gsum = {c: 0.0 for c in ("T", "S", "C", "R")}
    anorm = {c: 0.0 for c in ("T", "S", "C", "R")}
    gT_sum = gT_n = 0.0
    for x, y, t, idx in loader:
        x, y, t = x.to(device), y.to(device), t.to(device)
        idx = idx.tolist()
        H_T = H_S = H_C = H_R = None
        gS = gC = gR = gT = None
        exo_C = None
        if use_text and cache is not None and dssaa is not None:
            H_endo, exo_by, mask_exo, _, _ = base.gather_cache(cache, idx, device, dssaa)
            T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
            out = dssaa.enhance(
                T, S, r2, R, H_endo, exo_by, mask_exo,
                zero_endo=zero_endo, zero_exo=zero_exo)
            H_T, H_S = out.H_fusion["T"], out.H_fusion["S"]
            H_C, H_R = out.H_fusion["C"], out.H_fusion["R"]
            gS, gC, gR = out.gates["S"], out.gates["C"], out.gates["R"]
            gT = model.text_support_gate(H_endo["T"])
            gT_sum += float(gT.sum()); gT_n += gT.numel()
            if out.exo_routed and "C" in out.exo_routed:
                exo_C = out.exo_routed["C"]
            else:
                exo_C = exo_by["C"]
            if "T" in drop:
                H_T = None
            if "S" in drop:
                H_S, gS = None, None
            if "R" in drop:
                H_R, gR = None, None
            if diag and out.exo_routed:
                bsz = x.size(0)
                occ_n += bsz
                for c in occ:
                    if c not in out.exo_routed:
                        continue
                    m = out.exo_routed[c].mask
                    occ[c] += float((m.sum(dim=-1) > 0).float().sum())
                    if c in out.gates:
                        gsum[c] += float(out.gates[c].sum())
                    if c in getattr(out, "A", {}):
                        anorm[c] += float(out.A[c].detach().norm(dim=-1).mean() * bsz)
        yhat, _ = predict_batch(
            model, x, t, H_T=H_T, H_S=H_S, H_C=H_C, H_R=H_R,
            gS=gS, gC=gC, gR=gR, exo_C=exo_C, silent_C=silent_C, gT=gT)
        if (not silent_C) and use_text and getattr(model, "_last_C_info", None):
            info = model._last_C_info
            if isinstance(info, dict) and "fire" in info:
                fire_sum += float(info["fire"].sum().item())
                fire_n += info["fire"].numel()
        persist = x[:, -1:].expand_as(y)
        se += ((yhat - y) ** 2).sum().item()
        ae += (yhat - y).abs().sum().item()
        persist_se += ((persist - y) ** 2).sum().item()
        n += y.numel()
    fire_rate = fire_sum / max(fire_n, 1.0)
    if diag and gT_n > 0:
        print(f"[diag] support gate_T mean={gT_sum / gT_n:.3f}")
    if diag and occ_n > 0:
        print("[diag] routed occupancy (frac samples with ≥1 doc) "
              + " ".join(f"{c}={occ[c]/occ_n:.3f}" for c in occ))
        print("[diag] mean gate "
              + " ".join(f"{c}={gsum[c]/occ_n:.3f}" for c in gsum))
        print("[diag] mean |A| "
              + " ".join(f"{c}={anorm[c]/occ_n:.4f}" for c in anorm))
        if dssaa is not None and hasattr(dssaa, "blocks"):
            lams = []
            for c in ("T", "S", "C", "R"):
                le = float(torch.sigmoid(dssaa.blocks[c].fuse.lambda_endo_logit))
                lams.append(f"{c}:endo={le:.2f}/exo={1-le:.2f}")
            print("[diag] λ  " + "  ".join(lams))
    return se / n, ae / n, persist_se / n, fire_rate


@torch.no_grad()
def eval_direction_metrics(model, packs, cache, dssaa, device,
                           force_silent_C, drop_test):
    """方向命中率 + 尖峰预警（换口径，不拼 MSE）。

    全程用标准化的 y（单调线性变换不改变方向 / 分位数），因此与 scaler
    无关。persist 恒输出平线 → 方向命中率 0%、尖峰 recall 0%（下界）。
    """
    xs, ys, ts = packs["test"]["x"], packs["test"]["y"], packs["test"]["t"]
    loader = DataLoader(
        TensorDataset(xs, ys, ts, torch.arange(xs.size(0))),
        batch_size=base.BATCH, shuffle=False)
    yhats, persists, ys_list = [], [], []
    for x, y, t, idx in loader:
        x, y, t = x.to(device), y.to(device), t.to(device)
        idx = idx.tolist()
        H_T = H_S = H_C = H_R = None
        gS = gC = gR = gT = None
        exo_C = None
        if cache is not None and dssaa is not None:
            H_endo, exo_by, mask_exo, _, _ = base.gather_cache(cache, idx, device, dssaa)
            T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
            out = dssaa.enhance(T, S, r2, R, H_endo, exo_by, mask_exo)
            H_T, H_S = out.H_fusion["T"], out.H_fusion["S"]
            H_C, H_R = out.H_fusion["C"], out.H_fusion["R"]
            gS, gC, gR = out.gates["S"], out.gates["C"], out.gates["R"]
            gT = model.text_support_gate(H_endo["T"])
            exo_C = (out.exo_routed["C"] if out.exo_routed and "C" in out.exo_routed
                     else exo_by["C"])
            if "T" in drop_test:
                H_T = None
            if "S" in drop_test:
                H_S, gS = None, None
            if "R" in drop_test:
                H_R, gR = None, None
        yhat, _ = predict_batch(
            model, x, t, H_T=H_T, H_S=H_S, H_C=H_C, H_R=H_R,
            gS=gS, gC=gC, gR=gR, exo_C=exo_C, silent_C=force_silent_C, gT=gT)
        persist = x[:, -1:].expand_as(y)
        yhats.append(yhat.cpu())
        persists.append(persist.cpu())
        ys_list.append(y.cpu())
    yhat = torch.cat(yhats, 0)       # [N,P,1]
    persist = torch.cat(persists, 0)
    y = torch.cat(ys_list, 0)
    origin_val = xs[:, -1, 0]        # [N]

    # ---- 方向命中率（涨/跌二分类，排除 |Δ| 最小的 10% 作"平"）----
    d_true = y.mean(dim=1)[:, 0] - origin_val
    d_pred = yhat.mean(dim=1)[:, 0] - origin_val
    d_per = persist.mean(dim=1)[:, 0] - origin_val   # ≡ 0
    thr_flat = float(torch.quantile(d_true.abs(), 0.10))
    act = d_true.abs() > thr_flat
    dir_model = float((torch.sign(d_pred[act]) == torch.sign(d_true[act])).float().mean())
    dir_persist = float((torch.sign(d_per[act]) == torch.sign(d_true[act])).float().mean())

    # ---- 尖峰预警（未来 H 步最大涨幅）----
    gain_true = y.amax(dim=1)[:, 0] - origin_val
    gain_pred = yhat.amax(dim=1)[:, 0] - origin_val
    gain_per = persist.amax(dim=1)[:, 0] - origin_val   # ≡ 0
    thr_spike = float(torch.quantile(gain_true, 0.75))
    spike = gain_true > thr_spike

    import numpy as _np
    gt = gain_true.numpy()
    gp = gain_pred.numpy()
    gper = gain_per.numpy()
    lbl = spike.numpy().astype(int)

    def prf(warn):
        tp = float((warn & spike).sum())
        fp = float((warn & ~spike).sum())
        fn = float((~warn & spike).sum())
        rec = tp / (tp + fn + 1e-9)
        prec = tp / (tp + fp + 1e-9)
        f1 = 2 * rec * prec / (rec + prec + 1e-9)
        return rec, prec, f1

    # 幅度校准诊断：模型预测涨幅是否被 MSE 压扁
    print("  gain 分位数 true/pred (50/75/90%):")
    for q in (50, 75, 90):
        print(f"    {q}% = {_np.percentile(gt, q):.3f} / {_np.percentile(gp, q):.3f}")

    # AUC（阈值无关）：模型预测涨幅能否区分尖峰/非尖峰
    from sklearn.metrics import roc_auc_score
    auc = roc_auc_score(lbl, gp) if _np.ptp(gp) > 1e-8 else 0.5
    auc_per = roc_auc_score(lbl, gper) if _np.ptp(gper) > 1e-8 else 0.5
    print(f"  尖峰 AUC（预测涨幅→尖峰标签） 模型={auc:.3f}   persist={auc_per:.3f}")

    print("==== 方向 + 尖峰预警（换口径，不拼 MSE）====")
    print(f"  有效方向样本={int(act.sum())}/{d_true.numel()} (排除 |Δ|<{thr_flat:.3f})")
    print(f"  方向命中率    模型={dir_model:.3f}   persist={dir_persist:.3f}")
    print(f"  尖峰阈值={thr_spike:.3f}  尖峰窗口={int(spike.sum())}")
    for name, th in (("75分位", thr_spike),
                     ("中位数", float(torch.quantile(gain_true, 0.50))),
                     ("任意涨", 0.0)):
        rm, pm, fm = prf(gain_pred > th)
        rp, pp, fp_ = prf(gain_per > th)
        print(f"  预警@{name:6s}(th={th:.2f})  model recall={rm:.3f} "
              f"prec={pm:.3f} F1={fm:.3f}  |  persist recall={rp:.3f} "
              f"prec={pp:.3f} F1={fp_:.3f}")
    r_m, p_m, f1_m = prf(gain_pred > thr_spike)
    r_p, p_p, f1_p = prf(gain_per > thr_spike)

    # 排名口径：对「模型预测涨幅」取 75 分位做阈值（生产同口径）
    thr_rank = float(_np.percentile(gp, 75))
    r_rk, p_rk, f1_rk = prf(gain_pred > thr_rank)
    print(f"  排名口径(th=pred_gain_q75={thr_rank:.3f})  model recall={r_rk:.3f} "
          f"prec={p_rk:.3f} F1={f1_rk:.3f}")
    return dict(
        dir_model=dir_model, dir_persist=dir_persist,
        spike_n=int(spike.sum()), spike_thr=thr_spike,
        warn_recall_model=r_m, warn_recall_persist=r_p,
        warn_prec_model=p_m, warn_prec_persist=p_p,
        warn_f1_model=f1_m, warn_f1_persist=f1_p,
        spike_auc_model=auc, spike_auc_persist=auc_per,
        gain90_true=float(_np.percentile(gt, 90)),
        gain90_pred=float(_np.percentile(gp, 90)),
        pred_gain_q50=float(_np.percentile(gp, 50)),
        pred_gain_q75=float(thr_rank),
        warn_recall_rank=r_rk, warn_prec_rank=p_rk, warn_f1_rank=f1_rk,
    )


@torch.no_grad()
def eval_direction_score(model, packs, cache, dssaa, device, split,
                         silent_C=False, drop=None):
    """在 ``split`` 集上算方向命中率 + 尖峰 AUC，返回 dict（score 越大越好）。

    用作验证门控的选择指标（替代 MSE）：score = 方向命中率 + 尖峰 AUC。
    """
    drop = set(drop or [])
    xs, ys, ts = packs[split]["x"], packs[split]["y"], packs[split]["t"]
    loader = DataLoader(
        TensorDataset(xs, ys, ts, torch.arange(xs.size(0))),
        batch_size=base.BATCH, shuffle=False)
    yhats, ys_list = [], []
    for x, y, t, idx in loader:
        x, y, t = x.to(device), y.to(device), t.to(device)
        idx = idx.tolist()
        H_T = H_S = H_C = H_R = None
        gS = gC = gR = gT = None
        exo_C = None
        if cache is not None and dssaa is not None:
            H_endo, exo_by, mask_exo, _, _ = base.gather_cache(cache, idx, device, dssaa)
            T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
            out = dssaa.enhance(T, S, r2, R, H_endo, exo_by, mask_exo)
            H_T, H_S = out.H_fusion["T"], out.H_fusion["S"]
            H_C, H_R = out.H_fusion["C"], out.H_fusion["R"]
            gS, gC, gR = out.gates["S"], out.gates["C"], out.gates["R"]
            gT = model.text_support_gate(H_endo["T"])
            exo_C = (out.exo_routed["C"] if out.exo_routed and "C" in out.exo_routed
                     else exo_by["C"])
            if "T" in drop:
                H_T = None
            if "S" in drop:
                H_S, gS = None, None
            if "R" in drop:
                H_R, gR = None, None
        yhat, _ = predict_batch(
            model, x, t, H_T=H_T, H_S=H_S, H_C=H_C, H_R=H_R,
            gS=gS, gC=gC, gR=gR, exo_C=exo_C, silent_C=silent_C, gT=gT)
        yhats.append(yhat.cpu())
        ys_list.append(y.cpu())
    yhat = torch.cat(yhats, 0)          # [N,P,1]
    y = torch.cat(ys_list, 0)
    origin = xs[:, -1, 0]               # [N]

    d_true = y.mean(dim=1)[:, 0] - origin
    d_pred = yhat.mean(dim=1)[:, 0] - origin
    thr_flat = float(torch.quantile(d_true.abs(), 0.10))
    act = d_true.abs() > thr_flat
    dir_model = float((torch.sign(d_pred[act]) == torch.sign(d_true[act])).float().mean())

    gain_true = y.amax(dim=1)[:, 0] - origin
    gain_pred = yhat.amax(dim=1)[:, 0] - origin
    thr_spike = float(torch.quantile(gain_true, 0.75))
    spike = gain_true > thr_spike
    import numpy as _np
    from sklearn.metrics import roc_auc_score
    gt = gain_true.numpy(); gp = gain_pred.numpy(); lbl = spike.numpy().astype(int)
    auc = roc_auc_score(lbl, gp) if _np.ptp(gp) > 1e-8 else 0.5
    return dict(dir_model=dir_model, spike_auc_model=auc,
                score=dir_model + auc,
                pred_gain_q50=float(_np.percentile(gp, 50)),
                pred_gain_q75=float(_np.percentile(gp, 75)))


def build_snippet_supervision(model, lib, facts_all, dates_all, encoder, device, dssaa,
                              r2_np=None):
    """Pair each train breakpoint with origin-fact event embedding."""
    snippets = lib["snippets"]
    if not snippets:
        return None
    texts = []
    targets = []
    strengths = []
    r2_wins = []
    L = base.SEQ_LEN
    for s in snippets:
        t_b = int(s.t_break)
        if r2_np is not None:
            seg = np.asarray(r2_np[max(0, t_b - L):t_b], dtype=np.float32)
            if seg.size < L:
                seg = np.concatenate([np.full(L - seg.size, seg[0] if seg.size else 0.0,
                                              dtype=np.float32), seg])
            r2_wins.append(seg)
        fact = facts_all[min(t_b, len(facts_all) - 1)]
        bodies = []
        conf_acc = 0.0
        for date, body in parse_fact_documents(fact):
            lab, conf = route_document(body, date)
            if lab == "event":
                bodies.append(body)
                conf_acc = max(conf_acc, conf)
        if not bodies:
            bodies = ["event shock"]
            conf_acc = 0.3
        texts.append(" ".join(bodies)[:400])
        targets.append(s.post[: base.PRED_LEN])
        strengths.append(max(conf_acc, 0.1) * (abs(s.amp) + 0.1))
    targets = torch.tensor(np.stack(targets, 0), dtype=torch.float32, device=device)
    strengths = torch.tensor(strengths, dtype=torch.float32, device=device)
    emb = encoder.encode(texts, device=device)  # [N, d_llm]
    r2_hist = None
    if r2_wins:
        r2_hist = torch.tensor(np.stack(r2_wins, 0), dtype=torch.float32,
                               device=device).unsqueeze(-1)
    # use the same exo_proj['C'] as inference
    return {"emb_raw": emb.detach(), "targets": targets,
            "strengths": strengths.clamp_min(1e-3), "dssaa": dssaa,
            "r2_hist": r2_hist}


def train_response_head(model, pack, epochs: int):
    if pack is None:
        print("[resp] no snippets — skip")
        return
    dssaa = pack["dssaa"]
    opt = torch.optim.Adam(
        list(model.event_resp.parameters()) + list(dssaa.exo_proj["C"].parameters()),
        lr=1e-3)
    for ep in range(1, epochs + 1):
        model.train()
        emb = dssaa.exo_proj["C"](pack["emb_raw"])
        # force soft fire during snippet fit
        loss = model.event_resp.loss_on_snippets(
            emb, pack["targets"], strengths=pack["strengths"],
            r2_hist=pack.get("r2_hist"), seq_len=base.SEQ_LEN)
        opt.zero_grad(); loss.backward(); opt.step()
        if ep % 10 == 0 or ep == 1:
            print(f"[resp] ep{ep:03d} loss={float(loss.detach()):.6f}")


@torch.no_grad()
def scale_gate_stats(model, packs, device):
    """Mean scale-OOD gate w per split (w?1: window scale above train range)."""
    out = {}
    for split, p in packs.items():
        _, T = model.decomp(p["x"].to(device))
        w = model.scale_gate(T[:, 1:] - T[:, :-1])
        out[split] = float(w.mean())
    return out


def gated_val(model, packs, caches, dssaa, device):
    """Val 方向分数（方向命中率 + 尖峰 AUC）under the four gate configs.

    模型选择用 max(·)（score 越大越好）：过拟合的路径在选模型时被关掉，
    而不是强制早停。最终 gate 在 val 上重新决定。
    """
    out = {}
    for name, kw in (("val", {}), ("noC", dict(silent_C=True)),
                     ("noT", dict(drop=("T",))),
                     ("noCT", dict(silent_C=True, drop=("T",)))):
        d = eval_direction_score(
            model, packs, caches["val"], dssaa, device, "val", **kw)
        out[name] = d["score"]
    return out


def tune_theta_on_val(model, packs, cache, dssaa, device):
    """Pick trigger theta maximizing val 方向分数 (text on)."""
    best_th, best_score = 0.5, -float("inf")
    for th in (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5):
        model.event_resp.theta = th
        d = eval_direction_score(
            model, packs, cache["val"], dssaa, device, "val", silent_C=False)
        print(f"  [theta] {th:.2f} val_score={d['score']:.4f} "
              f"dir={d['dir_model']:.3f} auc={d['spike_auc_model']:.3f}")
        if d["score"] > best_score:
            best_score, best_th = d["score"], th
    model.event_resp.theta = best_th
    print(f"[theta] selected {best_th:.1f} (val_score={best_score:.4f})")
    return best_th


def run_domain(dataset: str, pred_len: int, calendar_mode: str, encoder,
               capacity: str = "base", seq_len: int = 8,
               seasonal_period: int = 12):
    cap = CAPACITY[capacity]
    base.PRED_LEN = int(pred_len)
    base.SEQ_LEN = int(seq_len)
    base.BATCH = int(cap["batch"])
    base.MAX_EVENTS = int(cap["max_events"])
    base.D_SAA = int(cap["ds_saa_dim"])
    base.EPOCHS_T = int(cap["epochs_t"])
    base.EPOCHS_R = int(cap["epochs_r"])
    base.EPOCHS_S2 = int(cap["epochs_s2"])
    base.EPOCHS_S3 = int(cap["epochs_s3"])
    epochs_resp = int(cap["epochs_resp"])
    torch.manual_seed(base.SEED)
    np.random.seed(base.SEED)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n======== {dataset}  pred={pred_len} calendar={calendar_mode} "
          f"capacity={capacity} d_saa={cap['ds_saa_dim']} ========")

    csv_path = ROOT / "data" / f"{dataset}.csv"
    y_all, facts_all, dates_all, borders, n_train = base.load_pack(csv_path)
    # scaler stats for checkpoint (same fit as load_pack: train OT only)
    import pandas as _pd
    from sklearn.preprocessing import StandardScaler as _SS
    _raw_ot = _pd.read_csv(csv_path)["OT"].values.astype(np.float64).reshape(-1, 1)
    _scaler = _SS().fit(_raw_ot[:n_train])
    scaler_mean = _scaler.mean_.tolist()
    scaler_scale = _scaler.scale_.tolist()
    packs = {}
    for split, (b1, b2) in borders.items():
        x, fut, t, fi, di = base.make_windows(y_all, facts_all, dates_all, b1, b2)
        packs[split] = dict(x=x, y=fut, t=t, facts=fi, dates=di)
        print(f"  {split}: N={x.size(0)}")

    loaders = {
        split: DataLoader(
            TensorDataset(p["x"], p["y"], p["t"], torch.arange(p["x"].size(0))),
            batch_size=base.BATCH, shuffle=(split == "train"))
        for split, p in packs.items()
    }

    cfg = SimpleNamespace(
        task_name="long_term_forecast",
        seq_len=base.SEQ_LEN, pred_len=base.PRED_LEN, enc_in=1,
        d_ff=int(cap["d_ff"]), ema_alpha=0.05, ema_adapt="series", ema_learnable=True,
        seasonal_periods=seasonal_period, fourier_K=int(cap["fourier_K"]), seasonal_adaptive=False,
        jump_hidden=int(cap["jump_hidden"]), jump_theta=0.5, jump_pos_weight=5.0,
        use_ds_saa=True, ds_saa_dim=int(cap["ds_saa_dim"]),
        c_mode="response", response_K=int(cap["response_K"]),
        resid_n_bands=int(cap["resid_n_bands"]),
        t_head=T_HEAD,
        trend_mode=TREND_MODE,
        text_scale_gate=TEXT_SCALE_GATE,
        use_enc_T=USE_ENC_T,
        use_enc_eq=USE_ENC_EQ,
        c_numeric=C_NUMERIC,
    )
    model = Model(cfg).to(device)
    print(f"[cfg-model] trend_mode={TREND_MODE} text_scale_gate={TEXT_SCALE_GATE} "
          f"t_endo={T_ENDO} force_silent_C={FORCE_SILENT_C} "
          f"use_enc_T={USE_ENC_T} use_enc_eq={USE_ENC_EQ}")
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[capacity] params≈{n_params/1e6:.2f}M  d_ff={cap['d_ff']} "
          f"K_resp={cap['response_K']} bands={cap['resid_n_bands']}")
    model.decomp.fit_alpha(torch.from_numpy(y_all[:n_train]))

    # ---- 尖峰加权阈值：训练集 future max 涨幅的分位数 ----
    with torch.no_grad():
        tr_x = packs["train"]["x"]                 # [N,L,1]
        tr_y = packs["train"]["y"]                 # [N,P,1]
        tr_gain = tr_y.amax(dim=1)[:, 0] - tr_x[:, -1, 0]   # [N]
        spike_thr = float(torch.quantile(tr_gain, SPIKE_W_Q))
    print(f"[spike-w] train gain q{SPIKE_W_Q:.0%}={spike_thr:.4f}  "
          f"spike_w={SPIKE_W}")

    # ---- stage1: pure TS (trend/season/resid); C silent ----
    print("---- stage1 pure-TS ----")
    old_j = base.EPOCHS_J
    if not C_NUMERIC:
        base.EPOCHS_J = 0  # skip legacy jump head train (C 无数值触发)
    base.train_ts_backbone(model, loaders, n_train, y_all, borders, device)
    base.EPOCHS_J = old_j

    mse_ts, mae_ts, p_ts, _ = eval_mse(
        model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
        device, use_text=False)
    # ablation of the scale-equivariant trend head: plain ΔMLP only
    model.scale_ready.fill_(False)
    mse_plain, _, _, _ = eval_mse(
        model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
        device, use_text=False)
    model.scale_ready.fill_(True)
    w_stats = scale_gate_stats(model, packs, device)
    print(f"[stage1 test] persist={p_ts:.6f} TS={mse_ts:.6f} "
          f"(plain-ΔMLP only={mse_plain:.6f})  mean w train/val/test="
          f"{w_stats['train']:.3f}/{w_stats['val']:.3f}/{w_stats['test']:.3f}")

    # ---- response library on train r2 ----
    with torch.no_grad():
        y_tr = torch.from_numpy(y_all[:n_train]).view(1, n_train, 1).to(device)
        t_tr = torch.arange(n_train, device=device, dtype=torch.float32).view(1, -1)
        r1, _ = model.decomp(y_tr)
        r2, _ = model.seasonal(r1, t=t_tr)
        r2_np = r2.squeeze().cpu().numpy()
    lib = fit_response_library(
        r2_np, horizon=base.PRED_LEN, pre_len=3, K=int(cap["response_K"]))
    # Social / log-smoothed series: PELT often finds 0 BPs.  Fall back to
    # anomaly-detection days (MAD z) that fall inside the train split, so the
    # C pathway + text-routed events can actually fire.
    if len(lib.get("snippets") or []) == 0:
        anom_csv = ROOT / "data" / "social" / "anomalies.csv"
        date_csv = ROOT / "data" / f"{dataset}.csv"
        if anom_csv.exists() and date_csv.exists():
            import pandas as _pd
            dates_df = _pd.read_csv(date_csv)
            date_col = "date" if "date" in dates_df.columns else "Date"
            date2i = {str(d)[:10]: i for i, d in enumerate(dates_df[date_col].tolist())}
            adf = _pd.read_csv(anom_csv)
            adf = adf[adf["is_anomaly"] == True]  # noqa: E712
            bps = []
            for d in adf["date"].astype(str).str[:10].tolist():
                i = date2i.get(d)
                if i is not None and i < n_train:
                    bps.append(int(i))
            if bps:
                lib = fit_response_library_from_breakpoints(
                    r2_np, bps, horizon=base.PRED_LEN, pre_len=3,
                    K=int(cap["response_K"]))
                print(f"[library] PELT empty → anomaly BPs={len(bps)} "
                      f"(train-only) snippets={len(lib['snippets'])}")
            else:
                print("[library] PELT empty and no train-side anomaly BPs")
        else:
            print("[library] PELT empty; anomalies.csv missing — C stays silent")
    model.load_response_library(lib)
    if lib.get("C") is not None:
        C_t = torch.tensor(np.asarray(lib["C"]), dtype=torch.float32).view(-1, 1)
        # pad / trim to full series length
        if C_t.size(0) < len(y_all):
            pad = torch.zeros(len(y_all) - C_t.size(0), 1)
            C_t = torch.cat([C_t, pad], 0)
        model.set_jump_series(C_t[: len(y_all)].to(device))
    print(f"[library] bps={len(lib['bps'])} snippets={len(lib['snippets'])}")

    # ---- text + DS-SAA ----
    print("---- text cache + DS-SAA ----")
    d_saa = int(cap["ds_saa_dim"])
    semantic = DualSourceSemanticSpace(
        encoder, proj_dim=d_saa, pred_len=base.PRED_LEN,
        calendar_mode=calendar_mode).to(device)
    dssaa = DSSAAModule(
        d_model=d_saa, seq_len=base.SEQ_LEN, n_vars=1,
        semantic=semantic, max_events=base.MAX_EVENTS,
        t_endo=T_ENDO, t_time_only=T_TIME_ONLY).to(device)
    model.attach_dssaa(dssaa)

    caches = {
        split: base.precompute_text(
            semantic, dssaa, packs[split]["x"], packs[split]["facts"],
            packs[split]["dates"], device, tag=split)
        for split in ("train", "val", "test")
    }
    # ---- support model of endo-T embeddings (train only; diagnostic unless
    # --support_gate) ----
    d_tr = model.fit_text_support(caches["train"]["H_endo"]["T"].to(device))
    for split in ("val", "test"):
        E = caches[split]["H_endo"]["T"].to(device)
        g = model.text_support_gate(E)
        d = model.text_support_dist(E)
        print(f"[support] {split}: dist mean={float(d.mean()):.3f} "
              f"(train mean={float(d_tr.mean()):.3f} thr={float(model.sup_thr):.3f}) "
              f"gate mean={float(g.mean()):.3f} frac<0.5={float((g < 0.5).float().mean()):.3f}")
    if not SUPPORT_GATE:
        model.sup_ready.fill_(False)   # gate ≡ 1
    print(f"[support] gate {'ON' if SUPPORT_GATE else 'off (gate=1)'}")

    # report C exo occupancy
    c_rate = float(caches["train"]["exo"]["C"]["mask"].sum() /
                   max(caches["train"]["exo"]["C"]["mask"].numel(), 1))
    t_rate = float(caches["train"]["exo"]["T"]["mask"].sum() /
                   max(caches["train"]["exo"]["T"]["mask"].numel(), 1))
    print(f"[route] train exo occupancy  C={c_rate:.4f}  T={t_rate:.4f}")

    # ---- train response head on snippets ----
    snip = build_snippet_supervision(
        model, lib, facts_all, dates_all, encoder, device, dssaa, r2_np=r2_np)
    train_response_head(model, snip, epochs_resp)

    loss_fn = nn.MSELoss()

    # ---- stage2: DS-SAA + text heads (incl event_resp) ----
    print("---- stage2 ----")
    for p in model.parameters():
        p.requires_grad = False
    for p in dssaa.parameters():
        p.requires_grad = True
    for p in model.txt_film.parameters():
        p.requires_grad = True
    for p in model.event_resp.parameters():
        p.requires_grad = True
    for p in model.season_mod.parameters():
        p.requires_grad = True
    # conditional mamba text path
    for p in model.resid.parameters():
        p.requires_grad = True
    for p in model.phase_enc.parameters():
        p.requires_grad = True

    opt2 = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=base.LR_S2)
    best_val, best_state = -float("inf"), None
    for ep in range(1, base.EPOCHS_S2 + 1):
        model.train(); dssaa.train(); tot = n = 0
        for x, yb, t, idx in loaders["train"]:
            x, yb, t = x.to(device), yb.to(device), t.to(device)
            idx = idx.tolist()
            with torch.no_grad():
                y_ts, _ = predict_batch(model, x, t, silent_C=True)
                residual = yb - y_ts
            H_endo, exo_by, mask_exo, _, _ = base.gather_cache(
                caches["train"], idx, device, dssaa)
            T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
            out = dssaa.enhance(T, S, r2, R, H_endo, exo_by, mask_exo)
            exo_C = (out.exo_routed["C"] if out.exo_routed and "C" in out.exo_routed
                     else exo_by["C"])
            yhat, _ = predict_batch(
                model, x, t,
                H_T=out.H_fusion["T"], H_S=out.H_fusion["S"],
                H_C=out.H_fusion["C"], H_R=out.H_fusion["R"],
                gS=out.gates["S"], gC=out.gates["C"], gR=out.gates["R"],
                exo_C=exo_C, silent_C=FORCE_SILENT_C,
                gT=model.text_support_gate(H_endo["T"]))
            sw = spike_sample_weight(yb, x[:, -1:], spike_thr)   # [B] 尖峰加权
            loss = (loss_fn(yhat, yb) * sw.view(-1, 1, 1)).mean() + base.ORTH_W * out.L_orth
            if out.L_route is not None:
                loss = loss + getattr(base, "ROUTE_W", 0.1) * out.L_route
            loss = loss + 0.5 * loss_fn(yhat - y_ts.detach(), residual.detach())
            # trust region on text-driven trend modulation (no-harm)
            loss = loss + TR_W * model.trend_trust_region()
            # text-marked point-process supervision for C:
            #   fire ← PELT future-jump label; Ĉ ← PELT future C (signed)
            if not FORCE_SILENT_C:
                loss = loss + c_point_process_loss(model, t, yb, exo_C, n_train)
            opt2.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            opt2.step()
            tot += loss.item() * x.size(0); n += x.size(0)
        vms = gated_val(model, packs, caches, dssaa, device)
        vm = max(vms.values())   # best achievable under the final gate search
        if vm > best_val:
            best_val = vm
            best_state = {
                k: v.detach().cpu().clone() for k, v in model.state_dict().items()
            }
            best_dssaa = {
                k: v.detach().cpu().clone() for k, v in dssaa.state_dict().items()
            }
        if ep % 5 == 0 or ep == 1:
            print(f"[s2] ep{ep:03d} loss={tot/n:.6f} "
                  + " ".join(f"{k}={v:.6f}" for k, v in vms.items()))
    if best_state is not None:
        model.load_state_dict(best_state, strict=False)
        dssaa.load_state_dict(best_dssaa)

    mse_s2, _, _, fr2 = eval_mse(
        model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
        device, cache=caches["test"], dssaa=dssaa, use_text=True)
    print(f"[stage2 test] MSE={mse_s2:.6f} fire={fr2:.3f}")

    # ---- stage3 e2e ----
    print("---- stage3 ----")
    for p in model.parameters():
        p.requires_grad = True
    model.jump.freeze_cls_head(True)
    for p in semantic.encoder.parameters():
        p.requires_grad = False
    opt3 = torch.optim.Adam(
        [p for p in model.parameters() if p.requires_grad], lr=base.LR_S3)
    best_val, best_state = -float("inf"), None
    for ep in range(1, base.EPOCHS_S3 + 1):
        model.train(); tot = n = 0
        model.jump.freeze_cls_head(True)
        for x, yb, t, idx in loaders["train"]:
            x, yb, t = x.to(device), yb.to(device), t.to(device)
            idx = idx.tolist()
            H_endo, exo_by, mask_exo, _, _ = base.gather_cache(
                caches["train"], idx, device, dssaa)
            T, S, r1, r2, R, C_hist = model.decompose(x, t=t)
            out = dssaa.enhance(T, S, r2, R, H_endo, exo_by, mask_exo)
            exo_C = (out.exo_routed["C"] if out.exo_routed and "C" in out.exo_routed
                     else exo_by["C"])
            yhat, _ = predict_batch(
                model, x, t,
                H_T=out.H_fusion["T"], H_S=out.H_fusion["S"],
                H_C=out.H_fusion["C"], H_R=out.H_fusion["R"],
                gS=out.gates["S"], gC=out.gates["C"], gR=out.gates["R"],
                exo_C=exo_C, silent_C=FORCE_SILENT_C,
                gT=model.text_support_gate(H_endo["T"]))
            sw = spike_sample_weight(yb, x[:, -1:], spike_thr)   # [B] 尖峰加权
            loss = (loss_fn(yhat, yb) * sw.view(-1, 1, 1)).mean() + base.ORTH_W * out.L_orth
            if out.L_route is not None:
                loss = loss + 0.1 * getattr(base, "ROUTE_W", 0.1) * out.L_route
            loss = loss + TR_W * model.trend_trust_region()
            if not FORCE_SILENT_C:
                loss = loss + 0.5 * c_point_process_loss(model, t, yb, exo_C, n_train)
            opt3.zero_grad(); loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            opt3.step()
            tot += loss.item() * x.size(0); n += x.size(0)
        vms = gated_val(model, packs, caches, dssaa, device)
        vm = max(vms.values())   # best achievable under the final gate search
        if vm > best_val:
            best_val = vm
            best_state = {k: v.detach().cpu().clone()
                          for k, v in model.state_dict().items()}
        if ep % 5 == 0 or ep == 1:
            print(f"[s3] ep{ep:03d} loss={tot/n:.6f} "
                  + " ".join(f"{k}={v:.6f}" for k, v in vms.items()))
    if best_state is not None:
        model.load_state_dict(best_state, strict=False)

    th = tune_theta_on_val(model, packs, caches, dssaa, device)

    # C × drop ⊆ {T,S,R}, selected on val.  (The Security-61 trend gain is
    # now carried by the numeric scale-equivariant head, so the T text
    # residual is selected like any other text path.)
    import itertools
    d_val_full = eval_direction_score(
        model, packs, caches["val"], dssaa, device, "val", silent_C=False)
    d_val_noC = eval_direction_score(
        model, packs, caches["val"], dssaa, device, "val", silent_C=True)
    cands = []
    for silent in (False, True):
        for r in range(0, 4):
            for drop in itertools.combinations(("T", "S", "R"), r):
                d = eval_direction_score(
                    model, packs, caches["val"], dssaa, device, "val",
                    silent_C=silent, drop=drop)
                n_on = (0 if silent else 1) + (3 - len(drop))
                cands.append((d["score"], n_on, silent, drop))
    v_max = max(c[0] for c in cands)
    # 容差 0.02 内 → 优先 C on（silent=False），其次更少文本路径
    near = [c for c in cands if c[0] >= v_max - 0.02]
    best_v, _, force_silent_C, drop_test = min(near, key=lambda c: (c[2], c[1]))
    if FORCE_SILENT_C:
        force_silent_C = True
    force_drop_T = "T" in drop_test
    print(f"[gate] val full={d_val_full['score']:.4f} "
          f"(dir={d_val_full['dir_model']:.3f}, auc={d_val_full['spike_auc_model']:.3f}) "
          f"C-silent={d_val_noC['score']:.4f} "
          f"best={best_v:.4f} → C={'off' if force_silent_C else 'on'} "
          f"drop={list(drop_test) or '-'}")

    mse_full, mae_full, p_full, fr = eval_mse(
        model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
        device, cache=caches["test"], dssaa=dssaa, use_text=True,
        silent_C=force_silent_C, drop=drop_test)
    mse_off, _, _, _ = eval_mse(
        model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
        device, use_text=False)
    mse_noC, _, _, _ = eval_mse(
        model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
        device, cache=caches["test"], dssaa=dssaa, use_text=True, silent_C=True,
        drop=drop_test)

    c_contrib = mse_noC - mse_full  # >0 means C helped (when not force-silent)
    print("==== summary (test) ====")
    print(f"  persist           {p_full:.6f}")
    print(f"  stage1 TS         {mse_ts:.6f}")
    print(f"  stage3 +text      {mse_full:.6f}  fire={fr:.3f} theta={th} "
          f"C={'off' if force_silent_C else 'on'} drop={list(drop_test) or '-'}")
    print(f"  stage3 text-off   {mse_off:.6f}")
    print(f"  stage3 C-silent   {mse_noC:.6f}  (C contrib Δ={c_contrib:+.6f})")

    print("==== diag (test, C silent) ====")
    eval_mse(
        model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
        device, cache=caches["test"], dssaa=dssaa, use_text=True,
        silent_C=True, diag=True)
    for name, kw in (
        ("drop T", dict(drop=("T",))),
        ("drop S", dict(drop=("S",))),
        ("drop R", dict(drop=("R",))),
        ("endo only", dict(zero_exo=True)),
        ("exo only", dict(zero_endo=True)),
    ):
        mse_d, _, _, _ = eval_mse(
            model, packs["test"]["x"], packs["test"]["y"], packs["test"]["t"],
            device, cache=caches["test"], dssaa=dssaa, use_text=True,
            silent_C=True, **kw)
        print(f"  {name:10s} {mse_d:.6f}  Δvs+text={mse_d-mse_noC:+.6f}")

    dirres = {}
    if EVAL_DIRECTION:
        dirres = eval_direction_metrics(model, packs, caches["test"], dssaa, device,
                                        force_silent_C, drop_test)

    # 生产预警阈值：数字口径（无文本）下 val 集预测涨幅 75 分位，与最终 gate 对齐
    pred_gain_q75 = None
    try:
        d_val_num = eval_direction_score(model, packs, None, None, device, "val",
                                         silent_C=force_silent_C, drop=drop_test)
        pred_gain_q75 = d_val_num.get("pred_gain_q75")
        print(f"[rank] 生产预警阈值 pred_gain_q75(val, numeric) = {pred_gain_q75}")
    except Exception as e:  # noqa: BLE001
        print(f"[rank] pred_gain_q75 计算失败（非致命）: {e}")

    row = {
        "domain": dataset,
        "seed": base.SEED,
        "capacity": capacity,
        "trend_mode": TREND_MODE,
        "text_scale_gate": int(TEXT_SCALE_GATE),
        "t_endo": int(T_ENDO),
        "force_silent_C": int(FORCE_SILENT_C),
        "persist": p_full,
        "ts": mse_ts,
        "ts_plain": mse_plain,
        "w_test": w_stats["test"],
        "s3_text": mse_full,
        "s3_off": mse_off,
        "s3_Csilent": mse_noC,
        "C_contrib": c_contrib,
        "C_enabled": (not force_silent_C),
        "T_enabled": (not force_drop_T),
        "drop": "".join(drop_test) or "-",
        "fire_rate": fr,
        "theta": th,
        "n_snippets": len(lib["snippets"]),
        "vs_ts_pct": 100.0 * (mse_full - mse_ts) / max(mse_ts, 1e-12),
        **dirres,
        # Production calibration must come from the numeric validation path.
        # dirres contains a same-named diagnostic computed on text/test data.
        "test_text_pred_gain_q75": dirres.get("pred_gain_q75"),
        "pred_gain_q75": pred_gain_q75,
    }

    # ---- export checkpoint (weights + config; architecture unchanged) ----
    ckpt_path = ""
    if SAVE_CKPT:
        try:
            from checkpoint import save_checkpoint, DEFAULT_CKPT_DIR
            out_dir = Path(CKPT_DIR_OVERRIDE) if CKPT_DIR_OVERRIDE else DEFAULT_CKPT_DIR
            fname = f"{dataset}_{capacity}_pl{pred_len}_L{seq_len}.pt"
            ckpt_file = out_dir / fname
            save_checkpoint(
                ckpt_file,
                model=model,
                dssaa=dssaa,
                configs=cfg,
                scaler_mean=scaler_mean,
                scaler_scale=scaler_scale,
                gate={
                    "silent_C": bool(force_silent_C),
                    "drop": list(drop_test),
                    "theta": float(th),
                    "support_gate": bool(SUPPORT_GATE),
                    "force_drop_T": bool(force_drop_T),
                    "calendar_mode": calendar_mode,
                    "seasonal_period": seasonal_period,
                },
                response_lib=lib,
                domain=dataset,
                capacity=capacity,
                metrics=row,
                extra={
                    "max_events": int(base.MAX_EVENTS),
                    "t_endo": bool(T_ENDO),
                    "t_time_only": bool(T_TIME_ONLY),
                    "n_train": int(n_train),
                    "seed": int(base.SEED),
                },
            )
            ckpt_path = str(ckpt_file)
            print(f"[ckpt] saved {ckpt_file}")
        except Exception as e:  # noqa: BLE001
            print(f"[ckpt] save failed (non-fatal): {e}")
    row["checkpoint"] = ckpt_path
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("domains", nargs="*", default=["Security", "Climate"])
    ap.add_argument("--pred_len", type=int, default=6)
    ap.add_argument("--calendar", default="short")
    ap.add_argument("--seq_len", type=int, default=8,
                    help="input window length (8 → 28 for longer trend context)")
    ap.add_argument("--seasonal_period", type=int, default=12,
                    help="Fourier seasonal period (12=monthly, 7=weekly)")
    ap.add_argument("--capacity", choices=list(CAPACITY), default="base")
    ap.add_argument("--out", type=str, default="")
    ap.add_argument("--no_ctx", action="store_true",
                    help="use token-embedding pooling instead of contextual")
    ap.add_argument("--endo", choices=("values", "regime"), default="values",
                    help="endogenous text: raw-values template or regime words")
    ap.add_argument("--no_t_endo", action="store_true",
                    help="do not feed endogenous text into the trend path")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--t_head", choices=("replace", "residual"), default="residual")
    ap.add_argument("--t_time_only", action="store_true",
                    help="H_T = time projection only (no endo/exo text) — tests "
                         "whether the T gain is numeric")
    ap.add_argument("--support_gate", action="store_true",
                    help="scale the T text residual by the train-support gate "
                         "(off by default: input-space distance closes the gate "
                         "on Security test where the T head still helps)")
    ap.add_argument("--trend_mode", choices=("mix", "plain", "eq"), default="mix",
                    help="numeric trend head: mix=scale-OOD, plain=ΔMLP, eq=s·MLP(ΔT/s)")
    ap.add_argument("--no_text_scale_gate", action="store_true",
                    help="do not multiply T text residual by (1-w)")
    ap.add_argument("--use_enc_T", action="store_true",
                    help="augment the plain trend head with a Mamba-encoded "
                         "trend branch (RepMoE encoder fusion)")
    ap.add_argument("--use_enc_eq", action="store_true",
                    help="run the Mamba encoder INSIDE the equivariant head "
                         "on ΔT/s (scale-invariant fusion)")
    ap.add_argument("--force_silent_C", action="store_true",
                    help="keep C silent in train/eval (EventResponse ablation)")
    ap.add_argument("--direction", action="store_true",
                    help="also evaluate direction hit-rate + spike warning "
                         "(alternative to MSE for the forecast branch)")
    ap.add_argument("--no_c_numeric", action="store_true",
                    help="disable numeric C fallback (C silent without exo event)")
    ap.add_argument("--spike_w", type=float, default=2.0,
                    help="extra loss weight on spike windows (0 disables spike weighting)")
    ap.add_argument("--ckpt_dir", type=str, default="",
                    help="checkpoint output dir (default: social_forecast/checkpoints)")
    ap.add_argument("--no_ckpt", action="store_true",
                    help="do not export checkpoint after training")
    args = ap.parse_args()
    global SUPPORT_GATE, T_HEAD, T_TIME_ONLY, TREND_MODE, TEXT_SCALE_GATE, FORCE_SILENT_C, USE_ENC_T, USE_ENC_EQ, EVAL_DIRECTION, C_NUMERIC, SPIKE_W, SAVE_CKPT, CKPT_DIR_OVERRIDE
    SUPPORT_GATE = bool(args.support_gate)
    T_HEAD = args.t_head
    T_TIME_ONLY = bool(args.t_time_only)
    TREND_MODE = args.trend_mode
    TEXT_SCALE_GATE = not bool(args.no_text_scale_gate)
    FORCE_SILENT_C = bool(args.force_silent_C)
    USE_ENC_T = bool(args.use_enc_T)
    USE_ENC_EQ = bool(args.use_enc_eq)
    EVAL_DIRECTION = bool(args.direction)
    C_NUMERIC = not bool(args.no_c_numeric)
    SPIKE_W = float(args.spike_w)
    SAVE_CKPT = not bool(args.no_ckpt)
    CKPT_DIR_OVERRIDE = Path(args.ckpt_dir) if args.ckpt_dir else None
    print(f"[cfg] t_head={T_HEAD} t_time_only={T_TIME_ONLY} "
          f"support_gate={SUPPORT_GATE} trend_mode={TREND_MODE} "
          f"text_scale_gate={TEXT_SCALE_GATE} force_silent_C={FORCE_SILENT_C} "
          f"c_numeric={C_NUMERIC} spike_w={SPIKE_W}")
    import layers.ds_saa_semantic as _sem
    _sem.ENDO_MODE = args.endo
    global T_ENDO
    T_ENDO = True
    if args.no_t_endo:
        T_ENDO = False
    if args.seed is not None:
        base.SEED = int(args.seed)
    print(f"[cfg] endo={args.endo} t_endo={T_ENDO} seed={base.SEED}")

    out_path = Path(args.out) if args.out else OUT

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    import os as _os
    _frac = _os.environ.get("ABLATION_GPU_FRAC")
    if device.type == "cuda" and _frac:
        try:
            torch.cuda.set_per_process_memory_fraction(float(_frac))
            print(f"[run] gpu memory fraction={_frac}")
        except Exception as e:
            print(f"[run] gpu memory fraction skipped: {e}")
    print(f"[run] device={device} capacity={args.capacity} → {CAPACITY[args.capacity]}")
    enc = load_gpt2_encoder(device=device, use_hidden=not args.no_ctx)
    print(f"[encoder] contextual={not args.no_ctx} layers={enc.layers}")
    rows = []
    for d in args.domains:
        rows.append(run_domain(
            d, args.pred_len, args.calendar, enc, capacity=args.capacity,
            seq_len=args.seq_len, seasonal_period=args.seasonal_period))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {out_path}")
    print("\ndomain | TS(plain) | TS(eq-mix, w_test) | +text | C-silent | off | C_Δ | vsTS%")
    for r in rows:
        print(
            f"{r['domain']:12s} {r['ts_plain']:.4f} {r['ts']:.4f}({r['w_test']:.2f}) "
            f"{r['s3_text']:.4f} {r['s3_Csilent']:.4f} {r['s3_off']:.4f} "
            f"{r['C_contrib']:+.4f} {r['vs_ts_pct']:+.1f}%"
        )


if __name__ == "__main__":
    main()
