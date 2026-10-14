"""端到端：异常检测 → checkpoint 推理 → 结构化中间产物 → LLM 归因报告。

阶段
----
1. 数据/事件输入（已有 CSV / anomalies）
2. 异常检测（scripts/anomaly_detect.py，可跳过）
3. 数值模型推理（checkpoint）
4. 结构化中间产物（events.jsonl / forecast_summary.json）
5. LLM 归因（DeepSeek / 模板回退）

失败回退：
- 无 checkpoint → 明确报错 + 训练命令
- LLM 挂掉 → 模板报告（复用 llm_reporter）
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SOCIAL_SENSE = Path(__file__).resolve().parents[2]
FORECAST = SOCIAL_SENSE / "social_forecast"
PY = sys.executable


@dataclass
class WorkflowResult:
    ok: bool
    stages: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    report_preview: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "stages": self.stages,
            "artifacts": self.artifacts,
            "errors": self.errors,
            "report_preview": self.report_preview[:800],
        }


class ForecastAIWorkflow:
    def __init__(
        self,
        *,
        checkpoint: Optional[Path] = None,
        out_dir: Optional[Path] = None,
        threshold: float = 3.0,
        top_events: int = 15,
        template_llm: bool = False,
        skip_anomaly: bool = False,
        skip_forecast: bool = False,
        skip_llm: bool = False,
        pred_windows: int = 5,
    ):
        self.checkpoint = Path(checkpoint) if checkpoint else None
        self.out_dir = Path(out_dir) if out_dir else (
            FORECAST / "results" / "workflow"
        )
        self.threshold = threshold
        self.top_events = top_events
        self.template_llm = template_llm
        self.skip_anomaly = skip_anomaly
        self.skip_forecast = skip_forecast
        self.skip_llm = skip_llm
        self.pred_windows = pred_windows
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _run_py(self, script_rel: str, args: List[str], cwd: Path) -> None:
        cmd = [PY, "-u", script_rel, *args]
        logger.info("run: %s (cwd=%s)", " ".join(cmd), cwd)
        print("\n>>>", " ".join(cmd), flush=True)
        r = subprocess.run(cmd, cwd=str(cwd), env=os.environ.copy())
        if r.returncode != 0:
            raise RuntimeError(f"command failed ({r.returncode}): {' '.join(cmd)}")

    def stage_anomaly(self) -> Dict[str, Any]:
        daily = FORECAST / "data" / "social" / "SocialMedia_daily_2023plus.csv"
        if not daily.exists():
            return {"skipped": True, "reason": f"missing {daily}"}
        self._run_py(
            "scripts/anomaly_detect.py",
            ["--csv", str(daily.relative_to(FORECAST)),
             "--threshold", str(self.threshold), "--top", "30"],
            FORECAST,
        )
        export = FORECAST / "scripts" / "export_events.py"
        if export.exists():
            self._run_py("scripts/export_events.py", [], FORECAST)
        anom = FORECAST / "data" / "social" / "anomalies.csv"
        events = FORECAST / "results" / "events.jsonl"
        return {
            "skipped": False,
            "anomalies": str(anom) if anom.exists() else "",
            "events": str(events) if events.exists() else "",
        }

    def stage_forecast(self) -> Dict[str, Any]:
        if str(SOCIAL_SENSE) not in sys.path:
            sys.path.insert(0, str(SOCIAL_SENSE))
        from workflow.forecast_ai.adapter import ForecastAdapter, find_latest_checkpoint

        ckpt = self.checkpoint or find_latest_checkpoint()
        if ckpt is None:
            raise FileNotFoundError("no checkpoint")
        svc = ForecastAdapter.load(ckpt)
        summary = svc.summary()

        # last windows from SocialMedia_log
        csv_path = FORECAST / "data" / f"{summary.get('domain') or 'SocialMedia_log'}.csv"
        if not csv_path.exists():
            csv_path = FORECAST / "data" / "SocialMedia_log.csv"
        import pandas as pd
        import numpy as np

        ot = pd.read_csv(csv_path)["OT"].values.astype(np.float64)
        seq_len = int(summary["seq_len"])
        preds: List[Dict[str, Any]] = []
        n = int(self.pred_windows)
        for k in range(n):
            end = len(ot) - k * max(seq_len // 4, 1)
            start = end - seq_len
            if start < 0:
                break
            window = ot[start:end]
            pr = svc.predict(window, t0=int(start))
            pr["window_end_idx"] = int(end - 1)
            preds.append(pr)

        # 每个预测窗口的精简摘要（供 LLM 归因与仪表盘）
        window_briefs = [
            {
                "t0": p.get("meta", {}).get("t0"),
                "direction": p.get("direction"),
                "direction_delta": round(float(p.get("direction_delta", 0.0)), 3),
                "spike_warning": bool(p.get("spike_warning")),
                "spike_gain": round(float(p.get("spike_gain", 0.0)), 3),
                "spike_thr": round(float(p.get("meta", {}).get("spike_thr", 0.0)), 3),
                "spike_thr_src": p.get("meta", {}).get("spike_thr_src", ""),
            }
            for p in preds
        ]

        out_json = self.out_dir / "forecast_summary.json"
        payload = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "checkpoint": summary,
            "predictions": preds,
            "window_briefs": window_briefs,
            "narrative": {
                "focus": "direction + spike_warning (not MSE)",
                "n_up": sum(1 for p in preds if p.get("direction") == "up"),
                "n_down": sum(1 for p in preds if p.get("direction") == "down"),
                "n_spike": sum(1 for p in preds if p.get("spike_warning")),
            },
        }
        out_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "checkpoint": summary.get("path", ""),
            "forecast_summary": str(out_json),
            "n_predictions": len(preds),
            "narrative": payload["narrative"],
            "window_briefs": window_briefs,
        }

    def stage_llm(self, forecast_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # enrich anomalies path with forecast brief if present
        brief_path = self.out_dir / "llm_forecast_brief.json"
        if forecast_info:
            brief_path.write_text(
                json.dumps({
                    "forecast": forecast_info.get("narrative"),
                    "checkpoint": forecast_info.get("checkpoint"),
                    "window_briefs": forecast_info.get("window_briefs", []),
                    "note": "数值模型已给出方向/尖峰预警（排名口径）；请结合异常事件做归因，勿编造 MSE。",
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        args = ["--top", str(self.top_events)]
        if self.template_llm:
            args.append("--template")
        try:
            self._run_py("scripts/llm_reporter.py", args, FORECAST)
            used_template = self.template_llm
            llm_error = ""
        except Exception as e:  # noqa: BLE001
            logger.warning("LLM failed, forcing template: %s", e)
            self._run_py("scripts/llm_reporter.py",
                         ["--top", str(self.top_events), "--template"], FORECAST)
            used_template = True
            llm_error = str(e)

        report = FORECAST / "data" / "social" / "report.md"
        # append forecast section if available
        if report.exists() and forecast_info:
            extra = [
                "",
                "---",
                "",
                "## 数值模型预测摘要（checkpoint）",
                "",
                f"- checkpoint: `{forecast_info.get('checkpoint', '')}`",
                f"- 预测窗口数: {forecast_info.get('n_predictions', 0)}",
            ]
            narr = forecast_info.get("narrative") or {}
            extra.append(
                f"- 方向: up={narr.get('n_up', 0)} / down={narr.get('n_down', 0)} "
                f"/ 尖峰预警={narr.get('n_spike', 0)}"
            )
            extra.append("")
            extra.append(
                f"> 结构化结果见 `{forecast_info.get('forecast_summary', '')}`"
            )
            with report.open("a", encoding="utf-8") as f:
                f.write("\n".join(extra) + "\n")

        text = report.read_text(encoding="utf-8") if report.exists() else ""
        # copy into workflow out
        out_report = self.out_dir / "report.md"
        if text:
            out_report.write_text(text, encoding="utf-8")
        return {
            "report": str(report),
            "workflow_report": str(out_report),
            "template": used_template,
            "llm_error": llm_error,
            "brief": str(brief_path) if brief_path.exists() else "",
        }

    def run(self) -> WorkflowResult:
        result = WorkflowResult(ok=True)
        forecast_info = None

        # 1–2 anomaly
        if not self.skip_anomaly:
            try:
                result.stages["anomaly"] = self.stage_anomaly()
                if result.stages["anomaly"].get("anomalies"):
                    result.artifacts["anomalies"] = result.stages["anomaly"]["anomalies"]
                if result.stages["anomaly"].get("events"):
                    result.artifacts["events"] = result.stages["anomaly"]["events"]
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"anomaly: {e}")
                result.stages["anomaly"] = {"error": str(e)}
                # non-fatal if anomalies.csv already exists
                anom = FORECAST / "data" / "social" / "anomalies.csv"
                if not anom.exists():
                    result.ok = False

        # 3–4 forecast
        if not self.skip_forecast:
            try:
                forecast_info = self.stage_forecast()
                result.stages["forecast"] = forecast_info
                result.artifacts["forecast_summary"] = forecast_info["forecast_summary"]
                result.artifacts["checkpoint"] = forecast_info.get("checkpoint", "")
            except FileNotFoundError as e:
                msg = (
                    f"{e}\n"
                    "请先导出 checkpoint：\n"
                    "  cd social_forecast\n"
                    "  python -u test\\test_event_response_e2e.py "
                    "SocialMedia_log --capacity lite --seq_len 28 "
                    "--seasonal_period 7 --no_ctx --direction\n"
                    "或冒烟权重：\n"
                    "  python -u scripts\\export_smoke_checkpoint.py"
                )
                result.errors.append(msg)
                result.stages["forecast"] = {"error": msg}
                result.ok = False
                print(msg, flush=True)
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"forecast: {e}")
                result.stages["forecast"] = {"error": str(e)}
                result.ok = False

        # 5 LLM
        if not self.skip_llm:
            try:
                llm_info = self.stage_llm(forecast_info)
                result.stages["llm"] = llm_info
                result.artifacts["report"] = llm_info.get("workflow_report") or llm_info.get("report", "")
                if result.artifacts["report"] and Path(result.artifacts["report"]).exists():
                    result.report_preview = Path(result.artifacts["report"]).read_text(
                        encoding="utf-8"
                    )[:1200]
            except Exception as e:  # noqa: BLE001
                result.errors.append(f"llm: {e}")
                result.stages["llm"] = {"error": str(e)}
                # LLM failure alone shouldn't fail whole pipeline if template works;
                # stage_llm already tries template. Mark ok False only if no report.
                if not (FORECAST / "data" / "social" / "report.md").exists():
                    result.ok = False

        summary_path = self.out_dir / "workflow_result.json"
        summary_path.write_text(
            json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        result.artifacts["workflow_result"] = str(summary_path)
        return result


def run_workflow(**kwargs) -> WorkflowResult:
    return ForecastAIWorkflow(**kwargs).run()
