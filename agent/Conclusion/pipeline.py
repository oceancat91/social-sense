"""
Skill5+6 命令行入口：生成 OT₀ → 严格校准 → 输出 OT₁。

  python -m Conclusion --d-platform path/D_platform.json \
      --stance-profile path/stance_profile.json \
      --analysis path/skill3.json [--rag path/rag.json] [--out out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Conclusion.calib.calibrator import calibrate
from Conclusion.gen.generator import generate_ot0

OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"


def _load_json(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"找不到输入文件：{p}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def run_conclusion(
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any] | None = None,
    skill3: dict[str, Any] | None = None,
    rag: dict[str, Any] | None = None,
    *,
    topk_text: int = 15,
    max_rounds: int = 2,
    empty_threshold: float = 0.5,
) -> dict[str, Any]:
    ot0 = generate_ot0(d_platform, stance_profile, skill3, rag, topk_text=topk_text)
    result = calibrate(
        ot0,
        d_platform,
        stance_profile,
        skill3,
        rag,
        max_rounds=max_rounds,
        empty_threshold=empty_threshold,
    )
    result["OT0"] = {k: v for k, v in ot0.items() if not k.startswith("_")}
    return result


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Conclusion：结论生成 + 残差校准")
    p.add_argument("--d-platform", required=True, help="D_platform.json")
    p.add_argument("--stance-profile", default=None, help="stance_profile.json")
    p.add_argument("--analysis", default=None, help="Skill3 结果 JSON")
    p.add_argument("--rag", default=None, help="Skill4 检索结果 JSON（可选）")
    p.add_argument("--out", default=None, help="输出结论 JSON")
    p.add_argument("--topk-text", type=int, default=15)
    p.add_argument("--max-rounds", type=int, default=2)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    d_platform = _load_json(args.d_platform)
    assert d_platform is not None
    stance = _load_json(args.stance_profile)
    skill3 = _load_json(args.analysis)
    rag = _load_json(args.rag)

    result = run_conclusion(
        d_platform,
        stance,
        skill3,
        rag,
        topk_text=args.topk_text,
        max_rounds=args.max_rounds,
    )

    print(
        json.dumps(
            {
                "OT1_status": result["OT1_status"],
                "calibration_rounds": result["OT1"].get("calibration_rounds"),
                "claim_trend": result["OT1"].get("claim_trend"),
                "claim_stance": result["OT1"].get("claim_stance"),
                "uncertainty": result["OT1"].get("uncertainty"),
                "deviation_report": result["deviation_report"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.dry_run:
        return
    out = Path(args.out) if args.out else OUTPUT_DIR / "conclusion.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"conclusion saved: {out}")


if __name__ == "__main__":
    main()
