"""
多 Agent 分析引擎：把 agent/（B 站单平台 Skill1–6）与 multiagent/（跨平台主控）
封装成 Flask 可调用的纯函数服务层。

设计要点：
  - 数据源解耦：云端不依赖真实 B 站爬虫，而是把后端 SentimentData（已做情感分析）
    转成标准契约 D_platform，再喂给 Skill2→6 与跨平台融合。未来接入真实爬虫只需
    替换「数据源转换」这一层。
  - LLM 降级：Skill5/6 依赖 DeepSeek；未配置 API Key 时自动降级为确定性结论，
    保证 Skill2→4 与跨平台融合（master use_llm=False）仍能产出结果。
  - 路径隔离：通过 AGENT_ROOT / MULTIAGENT_ROOT 环境变量定位 agent 与 multiagent
    代码目录（容器内挂载到 /app/agent、/app/multiagent），并把它们加入 sys.path。
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

BACKEND_ROOT = Path(__file__).resolve().parents[2]   # backend/
REPO_ROOT = BACKEND_ROOT.parent                       # 仓库根（本地开发）
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "agent_outputs"

# 平台 -> 后端 SentimentData 用的平台标识（对齐 agent 契约，全小写）
PLATFORM_ALIASES = {
    "bilibili": "bilibili",
    "weibo": "weibo",
    "douyin": "douyin",
    "xiaohongshu": "xiaohongshu",
    "zhihu": "zhihu",
    "kuaishou": "kuaishou",
}


class AgentEngineError(RuntimeError):
    """引擎不可用 / 执行失败。"""


def agent_root() -> str:
    return os.getenv("AGENT_ROOT", str(REPO_ROOT / "agent"))


def multiagent_root() -> str:
    return os.getenv("MULTIAGENT_ROOT", str(REPO_ROOT / "multiagent"))


def output_dir() -> Path:
    p = Path(os.getenv("AGENT_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR)))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ensure_paths() -> None:
    """把 agent 相关代码目录加入 sys.path（幂等）。

    agent/ 下是多个顶层包（PlatformCrawler、StanceProfiler ...），需加入 agent 目录本身；
    multiagent 是一个独立包，需加入其父目录才能 `import multiagent`。
    """
    for root in (agent_root(), str(Path(multiagent_root()).parent)):
        if root and root not in sys.path:
            sys.path.insert(0, root)


def is_available() -> bool:
    """agent 与 multiagent 代码目录是否齐备（缺一视为不可用）。"""
    return (Path(agent_root()) / "StanceProfiler").exists() and (
        Path(multiagent_root()) / "master.py"
    ).exists()


def load_modules() -> tuple[Any, Any, Any, Any, Any, Any]:
    """惰性加载各 Skill 纯函数入口。失败抛 AgentEngineError。"""
    _ensure_paths()
    try:
        # pylint: disable=import-error
        from PlatformCrawler.dataloader.builder import build_d_platform
        from StanceProfiler.profiler import profile_d_platform
        from MultimodalAnalyzer.analyzer import AnalyzerConfig, run_analysis
        from KnowledgeAugmentor.store import KnowledgeStore
        from Conclusion.pipeline import run_conclusion
        from multiagent.master import run_master
        # pylint: enable=import-error
    except Exception as e:  # noqa: BLE001
        raise AgentEngineError(f"加载 agent 引擎失败：{e}") from e
    return (
        build_d_platform,
        profile_d_platform,
        (AnalyzerConfig, run_analysis),
        KnowledgeStore,
        run_conclusion,
        run_master,
    )


# --------------------------------------------------------------------------- #
# 数据源转换：SentimentData rows -> D_platform
# --------------------------------------------------------------------------- #

def _to_tz_cn(dt: datetime) -> datetime:
    """把后端 naive/UTC 时间统一转成 UTC+8 aware。"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone(timedelta(hours=8)))


def rows_to_records(rows: list[Any]) -> list[dict[str, Any]]:
    """把 SentimentData ORM 对象/字典 转成 build_d_platform 需要的 records。"""
    records: list[dict[str, Any]] = []
    for d in rows:
        if isinstance(d, dict):
            get = d.get
        else:
            get = lambda k, default=None: getattr(d, k, default)  # noqa: E731

        published = get("published_at")
        if published is None:
            continue
        dt = _to_tz_cn(published)
        content_id = str(get("content_hash") or get("id") or "").strip()
        if not content_id:
            continue

        likes = int(get("like_count") or 0)
        comments = int(get("comment_count") or 0)
        shares = int(get("share_count") or 0)
        interact = likes + comments * 2 + shares * 3

        # 关键词：SentimentData.keywords 是 JSON 字符串，转 list
        keywords = get("keywords")
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except (ValueError, TypeError):
                keywords = []
        keywords = [str(w) for w in (keywords or [])][:8]

        records.append(
            {
                "content_id": content_id,
                "parent_id": None,
                "author_id": str(get("author") or ""),
                "ts": dt.isoformat(timespec="seconds"),
                "ts_unix": int(dt.timestamp()),
                "text": str(get("content") or "").strip(),
                "like": float(likes),
                "reply_count": float(comments),
                "share_or_coin": float(shares),
                "interact": float(interact),
                "source_url": get("url"),
                "stance_label": None,        # 交给 Skill2 重新标注
                "sentiment_score": float(get("score") or 0.0),
                "topic_tags": keywords,
                "lang": "zh",
                "ext": {"backend_source": "sentiment_data"},
            }
        )
    return records


def build_d_platform_from_rows(
    rows: list[Any],
    *,
    keyword: str,
    platform: str = "bilibili",
    granularity: str = "day",
    time_range: tuple[str, str] | None = None,
) -> dict[str, Any]:
    """SentimentData rows -> 标准 D_platform（复用 Skill1 的 build_d_platform）。"""
    if not is_available():
        raise AgentEngineError("agent 代码目录缺失，无法构建 D_platform")

    build_d_platform = load_modules()[0]
    records = rows_to_records(rows)

    if time_range is None:
        if records:
            start = min(r["ts"] for r in records)[:10]
            end_dt = max(
                datetime.fromisoformat(r["ts"]) for r in records
            ) + timedelta(days=1)
            end = end_dt.strftime("%Y-%m-%d")
        else:
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        time_range = (start, end)

    bundle = {"records": records, "n_raw_in": len(records)}
    return build_d_platform(
        bundle,
        keyword=keyword,
        time_range=time_range,
        granularity=granularity,
        platform=platform,
    )


# --------------------------------------------------------------------------- #
# 单平台分析：D_platform -> Skill2→6 -> PlatformReport
# --------------------------------------------------------------------------- #

def _should_augment(d_platform: dict[str, Any], skill3: dict[str, Any]) -> bool:
    meta = d_platform.get("D_meta") or {}
    if int(meta.get("n_text") or 0) > 200:
        return True
    return any(
        a.get("type") in ("cross_modal_inconsistency", "cross_scale_inconsistency")
        or a.get("severity") in ("important", "critical")
        for a in skill3.get("anomalies") or []
    )


def _deterministic_conclusion(
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any],
    reason: str,
    skill3: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """无 LLM 时的确定性降级结论（仅基于硬数据，不做叙事）。"""
    ts = d_platform.get("D_ts") or []
    sent_mean = stance_profile.get("sentiment_global_mean")

    # 趋势：首尾有效桶声量比较
    nonempty = [b for b in ts if not b.get("is_empty")]
    if len(nonempty) >= 2:
        head = float(nonempty[0].get("volume") or 0)
        tail = float(nonempty[-1].get("volume") or 0)
        claim_trend = "up" if tail > head else ("down" if tail < head else "flat")
    else:
        claim_trend = "unknown"

    if sent_mean is None:
        claim_sentiment = "unknown"
    elif sent_mean > 0.15:
        claim_sentiment = "up"
    elif sent_mean < -0.15:
        claim_sentiment = "down"
    else:
        claim_sentiment = "flat"

    claim_stance = stance_profile.get("stance_global") or "unclear"
    anomalies = (skill3 or {}).get("anomalies") or []
    risk_level = str(
        ((skill3 or {}).get("risk_summary") or {}).get("max_severity") or "none"
    )
    anomaly_evidence = [str(a.get("ts")) for a in anomalies if a.get("ts")][:8]
    local_evidence = [
        f"{a.get('ts')} · {a.get('type')} · {a.get('reason') or a.get('score')}"
        for a in anomalies[:5]
    ]

    ot1 = {
        "OT1_status": "degraded",
        "claim_trend": claim_trend,
        "claim_sentiment": claim_sentiment,
        "claim_stance": claim_stance,
        "uncertainty": "high",
        "summary_analysis": f"[降级结论] 未配置 LLM，仅输出硬数据摘要：主导立场 {claim_stance}，"
        f"情绪均值 {sent_mean if sent_mean is not None else 'N/A'}，声量趋势 {claim_trend}。",
        "risk_flags": [],
        "risk_level": risk_level,
        "anomaly_reasoning": {
            "global_observation": f"评论声量趋势为 {claim_trend}，主导立场为 {claim_stance}",
            "local_evidence": local_evidence,
            "cross_check": "未调用 LLM，仅保留 Skill3 硬证据，未执行历史案例语义类比",
            "reassessment": "结果为确定性降级输出；需结合空窗率与采集完整性人工复核",
        },
        "evidence_ids": anomaly_evidence,
        "calibration_rounds": 0,
    }
    return {
        "OT1": ot1,
        "OT1_status": "degraded",
        "deviation_report": [],
        "calibration_constraints": [],
        "degraded": True,
        "degraded_reason": reason,
    }


def run_platform_analysis(
    d_platform: dict[str, Any],
    *,
    with_conclusion: bool = True,
) -> dict[str, Any]:
    """D_platform -> Skill2→6 -> PlatformReport（dict，可直接交给 run_master）。"""
    if not is_available():
        raise AgentEngineError("agent 代码目录缺失")
    _ensure_paths()

    _, profile_d_platform, (AnalyzerConfig, run_analysis), KnowledgeStore, run_conclusion, _ = load_modules()

    # Skill2 立场画像
    d_platform, stance_profile = profile_d_platform(d_platform)

    # Skill3 多模态分析
    skill3 = run_analysis(
        d_platform, AnalyzerConfig(enable_text_tower=True), out_dir=output_dir()
    )

    # Skill4 知识增强（写入 + 按需检索）
    # 知识库存到可写的输出目录（agent/ 挂载为只读，不能往源码目录写）
    keyword = (d_platform.get("D_meta") or {}).get("keyword") or ""
    store = KnowledgeStore(index_path=str(output_dir() / "knowledge_store" / "index.jsonl"))
    store.write_d_platform(d_platform)
    case_examples = store.retrieve_analysis_examples(d_platform)
    if _should_augment(d_platform, skill3):
        rag = store.retrieve(keyword, top_k=8, keyword=keyword)
        rag.update(case_examples)
        rag["augment_used"] = bool(
            rag.get("rag_chunks") or rag.get("example_retrieval_used")
        )
    elif case_examples.get("example_retrieval_used"):
        rag = {
            **case_examples,
            "augment_used": True,
            "rag_chunks": [],
            "history_cases": [],
        }
    else:
        rag = None
    store.write_analysis_case(d_platform, skill3)

    # Skill5+6 结论生成 + 校准（LLM 缺失则降级）
    conclusion: dict[str, Any]
    if with_conclusion:
        try:
            conclusion = run_conclusion(
                d_platform, stance_profile, skill3, rag, max_rounds=2
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("结论生成降级（LLM 不可用）：%s", e)
            conclusion = _deterministic_conclusion(
                d_platform, stance_profile, str(e), skill3
            )
    else:
        conclusion = _deterministic_conclusion(
            d_platform, stance_profile, "skip_conclusion", skill3
        )

    return _assemble_report(d_platform, stance_profile, skill3, rag, conclusion)


def _assemble_report(
    d_platform: dict[str, Any],
    stance_profile: dict[str, Any],
    skill3: dict[str, Any],
    rag: dict[str, Any] | None,
    conclusion: dict[str, Any],
) -> dict[str, Any]:
    """组装 PlatformReport（与 multiagent.contract.normalize_report 兼容）。"""
    meta = d_platform.get("D_meta") or {}
    ot1 = conclusion.get("OT1") or {}
    return {
        "schema_version": "platform_report_v1",
        "platform": meta.get("platform"),
        "keyword": meta.get("keyword"),
        "time_range": meta.get("time_range"),
        "granularity": meta.get("granularity"),
        "meta": {
            "n_text": meta.get("n_text"),
            "n_buckets": meta.get("n_buckets"),
            "empty_ratio": meta.get("empty_ratio"),
            "is_empty": bool(meta.get("is_empty")),
            "stance_global": meta.get("stance_global"),
            "bias_score": meta.get("bias_score"),
            "confidence": meta.get("confidence"),
            "sentiment_global_mean": meta.get("sentiment_global_mean"),
        },
        "D_ts": d_platform.get("D_ts") or [],
        "stance_dist": stance_profile.get("stance_ratios") or {},
        "top_tags": [c.get("label") for c in stance_profile.get("keyword_clusters") or []],
        "skill3": {
            "anomalies": skill3.get("anomalies") or [],
            "risk_summary": skill3.get("risk_summary") or {},
            "multiscale_windows": (skill3.get("multiscale") or {}).get("windows") or [],
            "need_recrawl": bool(skill3.get("need_recrawl")),
        },
        "augment_used": bool((rag or {}).get("augment_used")),
        "OT1": {
            "OT1_status": ot1.get("OT1_status") or conclusion.get("OT1_status"),
            "claim_trend": ot1.get("claim_trend"),
            "claim_sentiment": ot1.get("claim_sentiment"),
            "claim_stance": ot1.get("claim_stance"),
            "uncertainty": ot1.get("uncertainty"),
            "summary_analysis": ot1.get("summary_analysis") or "",
            "risk_flags": ot1.get("risk_flags") or [],
            "risk_level": ot1.get("risk_level") or "unknown",
            "anomaly_reasoning": ot1.get("anomaly_reasoning") or {},
            "evidence_ids": ot1.get("evidence_ids") or [],
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


# --------------------------------------------------------------------------- #
# 跨平台融合：多平台 report -> run_master -> CT
# --------------------------------------------------------------------------- #

def run_cross_platform_analysis(
    reports: list[dict[str, Any]],
    *,
    use_llm: bool = True,
) -> dict[str, Any]:
    """多平台报告 -> 主控融合（对齐 + 融合 + 归纳 + CX 门禁）。"""
    if not is_available():
        raise AgentEngineError("multiagent 代码目录缺失")
    _ensure_paths()
    run_master = load_modules()[5]
    return run_master(reports, use_llm=use_llm)


def run_full_analysis(
    *,
    keyword: str,
    platforms: list[str],
    rows_by_platform: dict[str, list[Any]],
    granularity: str = "day",
    use_llm: bool = True,
    progress_cb=None,
) -> dict[str, Any]:
    """一站式：多平台 rows -> 各平台 report -> 跨平台 CT。

    rows_by_platform: {platform: [SentimentData...]}。
    progress_cb: 可选进度回调 progress_cb(platform, done_index, total)。
    """
    reports: list[dict[str, Any]] = []
    total = len(platforms)
    for idx, platform in enumerate(platforms, start=1):
        rows = rows_by_platform.get(platform, [])
        d_platform = build_d_platform_from_rows(
            rows, keyword=keyword, platform=platform, granularity=granularity
        )
        reports.append(run_platform_analysis(d_platform, with_conclusion=use_llm))
        if progress_cb:
            progress_cb(platform, idx, total)

    if len(reports) >= 2:
        ct = run_cross_platform_analysis(reports, use_llm=use_llm)
    else:
        # 单平台：仍产出 report，但无跨平台融合
        ct = {
            "CT_status": "single_platform",
            "scope": "single_platform",
            "n_platforms": 1,
            "platforms": [r.get("platform") for r in reports],
            "summary": (reports[0].get("OT1") or {}).get("summary_analysis") if reports else "",
        }

    return {
        "platform_reports": reports,
        "cross_platform": ct,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
