"""
Skill6：ResidualCalibrator —— 强制校准，G1–G7 全过才释放 OT₁。
"""

from __future__ import annotations

from typing import Any

from .gates import run_gates
from .rewrite import rewrite_ot0

CALIBRATOR_VERSION = "residual_calibrator_v1"


def calibrate(
    ot0: dict[str, Any],
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any] | None = None,
    skill3: dict[str, Any] | None = None,
    rag: dict[str, Any] | None = None,
    *,
    max_rounds: int = 2,
    empty_threshold: float = 0.5,
) -> dict[str, Any]:
    report = run_gates(ot0, d_platform, stance_profile, skill3, rag, empty_threshold=empty_threshold)
    rounds = 0
    while report["status"] != "pass" and rounds < max_rounds:
        try:
            pkg = ot0.get("_evidence_package") or {}
            ot0 = rewrite_ot0(ot0, report["deviations"], pkg)
        except Exception:
            break
        report = run_gates(ot0, d_platform, stance_profile, skill3, rag, empty_threshold=empty_threshold)
        rounds += 1

    if report["status"] == "pass":
        status = "accepted"
    elif any(d["gate"] in ("G4", "G5") for d in report["deviations"]):
        status = "reject"
    else:
        status = "failed_calibration"

    ot1 = {k: v for k, v in ot0.items() if not k.startswith("_")}
    ot1["OT1_status"] = status
    ot1["calibration_rounds"] = rounds
    return {
        "deviation_report": report["deviations"],
        "calibration_constraints": [d["msg"] for d in report["deviations"]],
        "OT1": ot1,
        "OT1_status": status,
        "calibrator_version": CALIBRATOR_VERSION,
    }
