"""Verify full/numeric checkpoint equivalence and numeric deployment metrics.

Only trusted local checkpoints should be supplied: the project loader uses
torch.load(weights_only=False). Inputs are never modified. The JSON output
must be a new file; no training or text encoding is performed.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "SocialMedia_log.csv"
EQUIVALENCE_ATOL = 1e-6
EQUIVALENCE_RTOL = 1e-6
THRESHOLD_ATOL = 1e-5


def artifact_info(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"path": str(path), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest()}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _finite_prediction(result: Any, pred_len: int, label: str) -> None:
    import numpy as np

    _require(np.asarray(result.yhat_scaled).shape == (pred_len,),
             f"{label}: unexpected prediction shape")
    for key, values in {"scaled": result.yhat_scaled, "raw": result.yhat_raw,
                        **result.components}.items():
        _require(bool(np.isfinite(values).all()), f"{label}: nonfinite {key}")
    for key in ("origin_raw", "direction_delta", "spike_gain"):
        _require(math.isfinite(float(getattr(result, key))),
                 f"{label}: nonfinite {key}")
    if result.fire_prob is not None:
        _require(math.isfinite(float(result.fire_prob)),
                 f"{label}: nonfinite fire_prob")


def verify(args: argparse.Namespace) -> dict[str, Any]:
    import numpy as np
    import torch
    from sklearn.metrics import roc_auc_score

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from checkpoint import load_forecast_bundle
    from inference import predict_window

    torch.set_num_threads(args.threads)
    torch.set_num_interop_threads(1)
    print("[verify] load full checkpoint (CPU, numeric path)", flush=True)
    full = load_forecast_bundle(args.checkpoint, device="cpu", with_text=False)
    print("[verify] load numeric checkpoint", flush=True)
    numeric = load_forecast_bundle(
        args.numeric_checkpoint, device="cpu", with_text=False)
    _require(full.dssaa is None and numeric.dssaa is None,
             "Text modules must not be loaded during numeric verification")
    _require((full.seq_len, full.pred_len) == (28, 6),
             "Expected the L28/P6 model for this verification protocol")
    _require((numeric.seq_len, numeric.pred_len) == (full.seq_len, full.pred_len),
             "Full/numeric window lengths differ")
    _require(full.domain == numeric.domain == "SocialMedia_log",
             "Both checkpoints must use the SocialMedia_log domain")
    _require(full.gate == numeric.gate, "Full/numeric gates differ")
    np.testing.assert_array_equal(full.scaler_mean, numeric.scaler_mean)
    np.testing.assert_array_equal(full.scaler_scale, numeric.scaler_scale)
    _require(bool(np.isfinite(numeric.scaler_mean).all()) and
             bool(np.isfinite(numeric.scaler_scale).all()) and
             bool((numeric.scaler_scale > 0).all()), "Invalid checkpoint scaler")

    thresholds = []
    for name, bundle in (("full", full), ("numeric", numeric)):
        value = bundle.metrics.get("pred_gain_q75")
        _require(value is not None and math.isfinite(float(value)),
                 f"{name}: missing finite saved pred_gain_q75")
        thresholds.append(float(value))
    _require(abs(thresholds[0] - thresholds[1]) <= THRESHOLD_ATOL,
             "Full/numeric saved validation thresholds differ")
    saved_threshold = thresholds[1]

    with CSV_PATH.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        values, dates = [], []
        for row in rows:
            values.append(float(row["OT"]))
            dates.append(row.get("date") or row.get("Date") or "")
    raw = np.asarray(values, dtype=np.float64)
    _require(bool(np.isfinite(raw).all()), "CSV OT contains nonfinite values")
    _require(dates == sorted(dates) and all(dates),
             "CSV dates must be present and chronologically ordered")
    n = len(raw)
    n_train, n_test = int(n * 0.7), int(n * 0.2)
    n_val = n - n_train - n_test
    seq_len, pred_len = numeric.seq_len, numeric.pred_len
    starts = {
        "validation": range(n_train - seq_len,
                            n_train + n_val - seq_len - pred_len + 1),
        "test": range(n - n_test - seq_len, n - seq_len - pred_len + 1),
    }
    _require(n_train >= seq_len + pred_len and n_val >= pred_len and
             n_test >= pred_len, "CSV is too short for chronological splits")
    _require(len(starts["test"]) == 262,
             "Expected all 262 test windows; dataset changed, review the protocol")
    # Training uses StandardScaler on the first 70% only (population std).
    np.testing.assert_allclose(numeric.scaler_mean, [raw[:n_train].mean()],
                               rtol=1e-8, atol=1e-8)
    np.testing.assert_allclose(numeric.scaler_scale, [raw[:n_train].std()],
                               rtol=1e-8, atol=1e-8)
    scaled = numeric.transform(raw).reshape(-1)

    val_gains = []
    for start in starts["validation"]:
        result = predict_window(numeric, raw[start:start + seq_len], t0=start)
        _finite_prediction(result, pred_len, f"validation window {start}")
        val_gains.append(result.spike_gain)
    measured_threshold = float(np.percentile(val_gains, 75))
    threshold_error = abs(measured_threshold - saved_threshold)
    _require(threshold_error <= THRESHOLD_ATOL,
             f"Saved pred_gain_q75={saved_threshold} differs from numeric "
             f"validation q75={measured_threshold} by {threshold_error}")
    print(f"[verify] validation threshold matches across {len(val_gains)} windows",
          flush=True)

    predictions, targets, origins, predicted_gains, warnings = [], [], [], [], []
    max_error = 0.0
    for index, start in enumerate(starts["test"], 1):
        window = raw[start:start + seq_len]
        full_result = predict_window(full, window, t0=start)
        result = predict_window(numeric, window, t0=start)
        _finite_prediction(full_result, pred_len, f"full test window {start}")
        _finite_prediction(result, pred_len, f"numeric test window {start}")
        _require(full_result.components.keys() == result.components.keys(),
                 "Full/numeric component names differ")
        pairs = [(full_result.yhat_scaled, result.yhat_scaled),
                 (full_result.yhat_raw, result.yhat_raw)]
        pairs += [(full_result.components[k], result.components[k])
                  for k in result.components]
        for left, right in pairs:
            np.testing.assert_allclose(left, right, atol=EQUIVALENCE_ATOL,
                                       rtol=EQUIVALENCE_RTOL,
                                       err_msg=f"test window {start}")
        error = float(np.max(np.abs(full_result.yhat_scaled - result.yhat_scaled)))
        max_error = max(max_error, error)
        _require(full_result.direction == result.direction and
                 full_result.spike_warning == result.spike_warning,
                 f"test window {start}: deployment signals differ")
        _require(abs(float(result.meta["spike_thr"]) - saved_threshold) <= 1e-12,
                 "Numeric inference did not use its saved validation threshold")
        _require(bool(result.spike_warning) == (result.spike_gain > saved_threshold),
                 "Warning differs from saved-threshold protocol")
        predictions.append(result.yhat_scaled.copy())
        targets.append(scaled[start + seq_len:start + seq_len + pred_len])
        origins.append(scaled[start + seq_len - 1])
        predicted_gains.append(result.spike_gain)
        warnings.append(result.spike_warning)
        if index % 50 == 0:
            print(f"[verify] equivalent test windows {index}/{len(starts['test'])}",
                  flush=True)

    yhat = np.stack(predictions)
    truth = np.stack(targets)
    origin = np.asarray(origins, dtype=np.float32)
    true_delta = truth.mean(axis=1) - origin
    pred_delta = yhat.mean(axis=1) - origin
    flat_threshold = float(np.quantile(np.abs(true_delta), 0.10))
    active = np.abs(true_delta) > flat_threshold
    _require(bool(active.any()), "No active direction evaluation windows")
    true_gain = truth.max(axis=1) - origin
    pred_gain = np.asarray(predicted_gains)
    true_spike_threshold = float(np.quantile(true_gain, 0.75))
    spike = true_gain > true_spike_threshold
    _require(0 < int(spike.sum()) < len(spike), "Spike AUC needs both classes")
    warning = np.asarray(warnings, dtype=bool)
    tp, fp = int((warning & spike).sum()), int((warning & ~spike).sum())
    fn, tn = int((~warning & spike).sum()), int((~warning & ~spike).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0

    return {
        "status": "passed",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "path": "CPU numeric inference, with_text=False, batch=1",
            "torch_version": str(torch.__version__), "threads": args.threads,
            "seq_len": seq_len, "pred_len": pred_len,
            "target_space": "StandardScaler(train-only) applied to log1p(OT)",
            "split": "chronological 70% train, remaining 10% val, 20% test",
            "rows": {"all": n, "train": n_train, "validation": n_val,
                     "test": n_test},
            "windows": {"train": n_train - seq_len - pred_len + 1,
                        "validation": len(val_gains), "test": len(predictions)},
            "dates": {"first": dates[0], "last": dates[-1]},
            "direction_rule": "sign(mean future - origin), true abs delta > q10",
            "spike_label_rule": "true max future - origin > test true gain q75",
            "warning_rule": "predicted max future - origin > saved validation q75",
        },
        "artifacts": {"full_checkpoint": artifact_info(args.checkpoint),
                      "numeric_checkpoint": artifact_info(args.numeric_checkpoint),
                      "evaluation_csv": artifact_info(CSV_PATH)},
        "equivalence": {"all_test_windows_passed": True,
                        "max_abs_scaled_prediction_error": max_error,
                        "absolute_tolerance": EQUIVALENCE_ATOL,
                        "relative_tolerance": EQUIVALENCE_RTOL,
                        "components_and_raw_predictions_checked": True},
        "validation_threshold": {
            "saved_pred_gain_q75": saved_threshold,
            "measured_numeric_validation_pred_gain_q75": measured_threshold,
            "absolute_error": threshold_error, "tolerance": THRESHOLD_ATOL},
        "numeric_holdout_metrics": {
            "standardized_mse": float(np.mean((yhat - truth) ** 2)),
            "persist_standardized_mse": float(np.mean((origin[:, None] - truth) ** 2)),
            "direction_accuracy": float(np.mean(
                np.sign(pred_delta[active]) == np.sign(true_delta[active]))),
            "direction_active_windows": int(active.sum()),
            "direction_flat_abs_delta_q10": flat_threshold,
            "spike_auc": float(roc_auc_score(spike.astype(int), pred_gain)),
            "spike_true_gain_q75": true_spike_threshold,
            "spike_windows": int(spike.sum()), "warning_windows": int(warning.sum()),
            "saved_validation_threshold_recall": recall,
            "saved_validation_threshold_precision": precision,
            "saved_validation_threshold_f1": (
                2 * precision * recall / (precision + recall)
                if precision + recall else 0.0),
            "confusion": {"tp": tp, "fp": fp, "fn": fn, "tn": tn}},
        "numeric_model_parameters": sum(p.numel() for p in numeric.model.parameters()),
        "limitations": [
            "These are numeric deployment metrics, not text-assisted training metrics.",
            "Overlapping chronological windows are not independent samples.",
            "Test-set quantiles define evaluation labels only; warning calibration "
            "uses the saved validation-set threshold.",
            "Peak server RAM and latency were not measured by this verifier."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--numeric-checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="new JSON file; existing files are never overwritten")
    parser.add_argument("--threads", type=int, default=2)
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    for key in ("checkpoint", "numeric_checkpoint"):
        path = getattr(args, key).resolve()
        if not path.is_file():
            parser.error(f"missing checkpoint: {path}")
        setattr(args, key, path)
    args.output = args.output.resolve()
    if args.output.exists():
        parser.error(f"refusing to overwrite existing output: {args.output}")
    report = verify(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(f"[verify] PASSED: {args.output}", flush=True)


if __name__ == "__main__":
    main()
