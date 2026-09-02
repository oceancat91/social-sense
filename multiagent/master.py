"""
主控 Agent：汇总多平台报告 → 对齐 → 融合 → 最终跨平台归纳 CT。

职责：
  - 汇总各平台 OT₁ 与融合指标，产出「跨平台共识 + 分歧 + 茧房证据」的结构化终裁；
  - 用 LLM 生成叙事层总结（无 API 时回退确定性模板，量化结论不受影响）；
  - 执行跨平台校准门禁（CX1–CX5），不达标不得释放跨平台强结论。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .align import align
from .contract import normalize_report
from .fuse import fuse
from .llm import chat, extract_json

SYSTEM_PROMPT = (
    "你是多平台舆情主控 Agent。你只基于下方给出的「平台报告 + 融合指标」做跨平台归纳，"
    "不得编造任何平台未提供的事实。请输出 JSON，字段：\n"
    "{\n"
    '  "summary": "200 字以内中文归纳：共识、分歧、茧房风险",\n'
    '  "claims": [{"text": "一条可验证断言", "platforms": ["bilibili", ...], "evidence": "引用指标或平台结论"}],\n'
    '  "risk_flags": ["争议/偏见/茧房风险提示"]\n'
    "}\n"
    "约束：claims 引用的 platforms 必须来自报告集合；茧房相关表述必须与 echo_chamber_score 一致。"
)


def _platform_list(reports: list[dict[str, Any]]) -> list[str]:
    return [str(r.get("platform")) for r in reports]


def _digest_deterministic(
    reports: list[dict[str, Any]],
    aligned: dict[str, Any],
    fused: dict[str, Any],
) -> dict[str, Any]:
    """确定性归纳：直接由融合指标拼装结构化断言（不依赖 LLM，保证与数据一致）。"""
    platforms = _platform_list(reports)
    claims: list[dict[str, Any]] = []
    risk: list[str] = []

    # 共识：跨平台立场分布
    dominant = fused.get("dominant_stance") or {}
    if dominant and len(set(dominant.values())) == 1:
        claims.append(
            {
                "text": f"各平台主导立场一致（{dominant.get(platforms[0])}）",
                "platforms": platforms,
                "evidence": "fuse.dominant_stance",
            }
        )
    elif dominant:
        claims.append(
            {
                "text": "各平台主导立场存在分歧：" + "；".join(f"{k}={v}" for k, v in dominant.items()),
                "platforms": platforms,
                "evidence": "fuse.dominant_stance",
            }
        )

    # 分歧
    sd = fused.get("stance_divergence") or 0.0
    se = fused.get("sentiment_divergence") or 0.0
    corr = fused.get("mean_volume_corr")
    claims.append(
        {
            "text": f"立场分布 JS 分歧 {sd}，情绪均值极差 {se}",
            "platforms": platforms,
            "evidence": "fuse.stance_divergence/sentiment_divergence",
        }
    )
    if corr is not None:
        level = "同频共振" if corr > 0.5 else ("弱共振" if corr > 0 else "反向/无共振")
        claims.append(
            {
                "text": f"平台声量时间相关性 {corr}（{level}）",
                "platforms": platforms,
                "evidence": "fuse.mean_volume_corr",
            }
        )

    echo = fused.get("echo_chamber_score") or 0.0
    if echo >= 0.5:
        risk.append(f"信息茧房风险较高（指数 {echo}）：平台间立场/情绪/声量显著分裂")
        claims.append(
            {
                "text": f"检测到显著信息茧房风险，指数 {echo}",
                "platforms": platforms,
                "evidence": "fuse.echo_chamber_score",
            }
        )
    elif echo >= 0.25:
        risk.append(f"存在一定平台分裂（指数 {echo}），建议跨平台对照解读")
    else:
        risk.append(f"平台间一致性较好（指数 {echo}），茧房风险低")

    # 情绪
    sent = fused.get("sentiment_means") or {}
    if sent:
        avg = sum(v for v in sent.values() if v is not None) / max(
            1, sum(1 for v in sent.values() if v is not None)
        )
        tone = "偏正面" if avg > 0.15 else ("偏负面" if avg < -0.15 else "中性")
        claims.append(
            {
                "text": f"跨平台情绪均值 {round(avg, 3)}（{tone}）",
                "platforms": platforms,
                "evidence": "fuse.sentiment_means",
            }
        )

    summary = "；".join(c["text"] for c in claims[:4])
    return {
        "claims": claims,
        "risk_flags": risk,
        "summary": summary,
        "dominant_stance": dominant,
    }


def _build_llm_user(
    reports: list[dict[str, Any]],
    aligned: dict[str, Any],
    fused: dict[str, Any],
) -> str:
    compact = {
        "platforms": fused.get("platforms"),
        "stance_divergence": fused.get("stance_divergence"),
        "sentiment_divergence": fused.get("sentiment_divergence"),
        "sentiment_means": fused.get("sentiment_means"),
        "bias_scores": fused.get("bias_scores"),
        "mean_volume_corr": fused.get("mean_volume_corr"),
        "echo_chamber_score": fused.get("echo_chamber_score"),
        "echo_chamber_components": fused.get("echo_chamber_components"),
        "stance_pair_divergences": fused.get("stance_pair_divergences"),
        "per_bucket_divergence": fused.get("per_bucket_divergence")[:20],
    }
    per_platform = [
        {
            "platform": r.get("platform"),
            "keyword": r.get("keyword"),
            "time_range": r.get("time_range"),
            "meta": r.get("meta"),
            "stance_dist": r.get("stance_dist"),
            "top_tags": r.get("top_tags"),
            "OT1": r.get("OT1"),
            "skill3_anomalies": (r.get("skill3") or {}).get("anomalies"),
        }
        for r in reports
    ]
    return json.dumps(
        {"fusion": compact, "platform_reports": per_platform},
        ensure_ascii=False,
        indent=2,
    )


def _run_cx_gates(
    ct: dict[str, Any],
    reports: list[dict[str, Any]],
    fused: dict[str, Any],
) -> dict[str, Any]:
    """跨平台校准门禁 CX1–CX5。"""
    platforms = _platform_list(reports)
    n = len(platforms)
    gates: list[dict[str, Any]] = []
    ok = True

    # CX1 平台覆盖
    if n == 1:
        gates.append({"gate": "CX1", "pass": True, "note": "单平台，已降级为 single_platform"})
    else:
        gates.append({"gate": "CX1", "pass": n >= 2, "note": f"{n} 个平台参与"})

    # CX2 分歧诚实：不得夸大/漏报茧房（仅拦截「强断言」与指标明显不符）
    echo = fused.get("echo_chamber_score") or 0.0
    summary = str(ct.get("summary") or "")
    strong_terms = ("严重", "显著", "强烈", "高度", "极端")
    mentions_divergence = any(k in summary for k in ("分裂", "茧房", "分歧", "不一致"))
    overstate = any(k in summary for k in strong_terms) and echo < 0.4
    understate = echo >= 0.4 and not mentions_divergence
    cx2_pass = not overstate and not understate
    gates.append(
        {
            "gate": "CX2",
            "pass": cx2_pass,
            "note": f"echo={echo}, 夸大={overstate}, 漏报={understate}",
        }
    )

    # CX3 禁跨平台幻觉：claims 引用的平台必须在报告集合内
    unknown_platforms: set[str] = set()
    for c in ct.get("claims") or []:
        for p in c.get("platforms") or []:
            if p not in platforms:
                unknown_platforms.add(p)
    cx3_pass = not unknown_platforms
    gates.append(
        {
            "gate": "CX3",
            "pass": cx3_pass,
            "note": f"未知平台={sorted(unknown_platforms)}" if unknown_platforms else "无越界平台",
        }
    )

    # CX4 证据可溯源：每个断言须绑定 ≥1 平台
    cx4_pass = all((c.get("platforms") or []) for c in ct.get("claims") or [])
    gates.append({"gate": "CX4", "pass": cx4_pass, "note": "claims 均有平台绑定"})

    # CX5 空窗诚实：全平台空 → 不得强结论
    all_empty = all((r.get("meta") or {}).get("is_empty") for r in reports)
    cx5_pass = not all_empty
    gates.append(
        {
            "gate": "CX5",
            "pass": cx5_pass,
            "note": "全平台空数据" if all_empty else "存在有效观测",
        }
    )

    ok = all(g["pass"] for g in gates)
    return {"gates": gates, "all_pass": ok}


def run_master(
    reports_raw: list[dict[str, Any]],
    *,
    use_llm: bool = True,
) -> dict[str, Any]:
    """主控入口：规范化 → 对齐 → 融合 → 归纳 → 校准。"""
    reports = [normalize_report(r) for r in reports_raw]
    if not reports:
        return {"CT_status": "failed", "error": "无平台报告"}

    aligned = align(reports)
    fused = fuse(aligned, reports)
    n = len(reports)

    digest = _digest_deterministic(reports, aligned, fused)

    # LLM 叙事层（可选，失败回退确定性归纳）
    llm_summary: dict[str, Any] | None = None
    llm_error: str | None = None
    if use_llm and n >= 1:
        try:
            user = _build_llm_user(reports, aligned, fused)
            llm_summary = extract_json(chat(SYSTEM_PROMPT, user))
        except Exception as e:  # noqa: BLE001
            llm_error = str(e)

    claims = (llm_summary or {}).get("claims") or digest["claims"]
    summary = (llm_summary or {}).get("summary") or digest["summary"]
    risk_flags = list((llm_summary or {}).get("risk_flags") or digest["risk_flags"])

    ct: dict[str, Any] = {
        "CT_status": "provisional",
        "scope": "cross_platform" if n >= 2 else "single_platform",
        "n_platforms": n,
        "platforms": [str(r.get("platform")) for r in reports],
        "keyword": reports[0].get("keyword"),
        "time_range": reports[0].get("time_range"),
        "granularity": reports[0].get("granularity"),
        "summary": summary,
        "claims": claims,
        "risk_flags": risk_flags,
        "echo_chamber": {
            "score": fused.get("echo_chamber_score"),
            "components": fused.get("echo_chamber_components"),
        },
        "fusion": fused,
        # 对齐结果（暴露给前端做「跨平台对齐」可视化：统一 time_axis + 平台内 z-score）
        "aligned": {
            "time_axis": aligned.get("time_axis") or [],
            "z_series": aligned.get("z_series") or {},
            "granularity": aligned.get("granularity"),
            "n_buckets": aligned.get("n_buckets"),
        },
        "llm_used": bool(llm_summary),
        "llm_error": llm_error,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }

    cx = _run_cx_gates(ct, reports, fused)
    ct["calibration"] = cx
    if not cx["all_pass"]:
        ct["CT_status"] = "failed_calibration"
    elif n == 1:
        ct["CT_status"] = "single_platform"
    else:
        ct["CT_status"] = "accepted"
    return ct
