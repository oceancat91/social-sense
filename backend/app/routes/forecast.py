"""热度预测 + AI 归因 API（公开只读，便于仪表盘演示）。"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from flask import Blueprint, current_app, jsonify, request, send_from_directory

logger = logging.getLogger(__name__)

forecast_bp = Blueprint("forecast", __name__)

_SOCIAL_SENSE = Path(__file__).resolve().parents[3]
_FORECAST = _SOCIAL_SENSE / "social_forecast"
_LOCK = threading.Lock()
_SERVICE = None
_SERVICE_ERROR = ""


def _roots():
    return _SOCIAL_SENSE, _FORECAST


def _get_service(force: bool = False):
    """Lazy singleton：首次请求时加载正式 checkpoint。"""
    global _SERVICE, _SERVICE_ERROR
    with _LOCK:
        if _SERVICE is not None and not force:
            return _SERVICE
        if _SERVICE_ERROR and not force:
            raise RuntimeError(_SERVICE_ERROR)
        try:
            from app.services.forecast_service import ForecastService

            _SERVICE = ForecastService.load(device="cpu")
            _SERVICE_ERROR = ""
            logger.info("forecast model loaded")
            return _SERVICE
        except Exception as e:  # noqa: BLE001
            _SERVICE_ERROR = str(e)
            logger.exception("forecast load failed")
            raise


def _load_ot_frame():
    csv_path = _FORECAST / "data" / "SocialMedia_log.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"missing {csv_path}")
    df = pd.read_csv(csv_path)
    date_col = "date" if "date" in df.columns else "Date"
    df[date_col] = pd.to_datetime(df[date_col]).dt.strftime("%Y-%m-%d")
    return df, date_col


@forecast_bp.route("/status", methods=["GET"])
def forecast_status():
    """模型 / checkpoint / 产物状态。"""
    from app.services.forecast_service import find_latest_checkpoint, default_checkpoint_dir

    ckpt = find_latest_checkpoint(default_checkpoint_dir())
    report = _FORECAST / "data" / "social" / "report.md"
    wf_report = _FORECAST / "results" / "workflow" / "report.md"
    summary = _FORECAST / "results" / "workflow" / "forecast_summary.json"
    anom = _FORECAST / "data" / "social" / "anomalies.csv"

    model_info = None
    err = None
    try:
        svc = _get_service()
        model_info = svc.summary()
    except Exception as e:  # noqa: BLE001
        err = str(e)

    return jsonify(
        code=200,
        message="ok",
        data={
            "checkpoint": str(ckpt) if ckpt else None,
            "checkpoint_name": ckpt.name if ckpt else None,
            "model_loaded": model_info is not None,
            "model": model_info,
            "load_error": err,
            "artifacts": {
                "report": str(wf_report if wf_report.exists() else report),
                "report_exists": wf_report.exists() or report.exists(),
                "forecast_summary": str(summary) if summary.exists() else None,
                "anomalies": str(anom) if anom.exists() else None,
            },
            "served_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
    )


@forecast_bp.route("/dashboard-data", methods=["GET"])
def dashboard_data():
    """仪表盘一次拉取：历史序列 + 最新预测 + 异常 + 报告。"""
    hist_n = request.args.get("hist", default=90, type=int)
    hist_n = max(30, min(hist_n, 365))

    df, date_col = _load_ot_frame()
    tail = df.tail(hist_n)
    history = {
        "dates": tail[date_col].tolist(),
        "ot": [float(x) for x in tail["OT"].tolist()],
    }

    prediction = None
    components = None
    model = None
    try:
        svc = _get_service()
        model = svc.summary()
        seq_len = int(model["seq_len"])
        pred_len = int(model["pred_len"])
        window = df["OT"].values.astype(np.float64)[-seq_len:]
        t0 = len(df) - seq_len
        pr = svc.predict(window, t0=int(t0))
        last_date = pd.to_datetime(df[date_col].iloc[-1])
        fut_dates = [
            (last_date + pd.Timedelta(days=i + 1)).strftime("%Y-%m-%d")
            for i in range(pred_len)
        ]
        prediction = {
            "dates": fut_dates,
            "yhat_raw": pr["yhat_raw"],
            "direction": pr["direction"],
            "direction_delta": pr["direction_delta"],
            "spike_warning": pr["spike_warning"],
            "spike_gain": pr["spike_gain"],
            "origin_raw": pr["origin_raw"],
        }
        components = pr.get("components")
    except Exception as e:  # noqa: BLE001
        return jsonify(code=503, message=f"模型未就绪: {e}", data={"history": history}), 503

    anomalies = []
    anom_path = _FORECAST / "data" / "social" / "anomalies.csv"
    if anom_path.exists():
        adf = pd.read_csv(anom_path)
        adf = adf[adf["is_anomaly"] == True].sort_values("z_max", ascending=False).head(12)  # noqa: E712
        for _, row in adf.iterrows():
            anomalies.append({
                "date": str(row.get("date", ""))[:10],
                "z_max": float(row["z_max"]),
                "trigger": str(row.get("trigger_metric", "")),
                "OT": float(row.get("OT", 0)),
                "fact": str(row.get("fact", ""))[:160],
            })

    report_md = ""
    for p in (
        _FORECAST / "results" / "workflow" / "report.md",
        _FORECAST / "data" / "social" / "report.md",
    ):
        if p.exists():
            report_md = p.read_text(encoding="utf-8")
            break

    narrative = None
    summary_path = _FORECAST / "results" / "workflow" / "forecast_summary.json"
    if summary_path.exists():
        try:
            narrative = json.loads(summary_path.read_text(encoding="utf-8")).get("narrative")
        except Exception:  # noqa: BLE001
            narrative = None

    return jsonify(
        code=200,
        message="ok",
        data={
            "model": model,
            "history": history,
            "prediction": prediction,
            "components": components,
            "anomalies": anomalies,
            "report_md": report_md,
            "narrative": narrative,
        },
    )


@forecast_bp.route("/predict", methods=["POST"])
def forecast_predict():
    """对自定义窗口做一次预测。body: {window: number[]}"""
    body = request.get_json(silent=True) or {}
    window = body.get("window")
    if not isinstance(window, list) or len(window) < 4:
        return jsonify(code=400, message="需要 window: number[]"), 400
    try:
        svc = _get_service()
        need = int(svc.summary()["seq_len"])
        if len(window) != need:
            return jsonify(
                code=400,
                message=f"窗口长度应为 {need}，当前 {len(window)}",
            ), 400
        pr = svc.predict([float(x) for x in window])
        return jsonify(code=200, message="ok", data=pr)
    except Exception as e:  # noqa: BLE001
        return jsonify(code=503, message=str(e)), 503


@forecast_bp.route("/report", methods=["GET"])
def forecast_report():
    for p in (
        _FORECAST / "results" / "workflow" / "report.md",
        _FORECAST / "data" / "social" / "report.md",
    ):
        if p.exists():
            return jsonify(code=200, message="ok", data={"markdown": p.read_text(encoding="utf-8"), "path": str(p)})
    return jsonify(code=404, message="尚无报告，请先跑 workflow"), 404


@forecast_bp.route("/ui/", methods=["GET"])
@forecast_bp.route("/ui", methods=["GET"])
def forecast_ui():
    """预测仪表盘静态页。"""
    static_dir = Path(current_app.root_path) / "static" / "forecast"
    return send_from_directory(static_dir, "index.html")
