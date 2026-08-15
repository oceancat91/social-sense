"""
单平台 Agent 全链路编排：LLM规划 → Skill1 → Skill2 → Skill3 → (Skill4 备用) → Skill5 → Skill6。

编排方式：
  - 优先 LangGraph 状态图（若已安装 langgraph，否则线性执行）
  - 线性执行与 LangGraph 节点复用同一批 step_* 函数，保证行为一致
  - 每个 Skill 单独记账（skill_log），异常即中止并抛出，便于定位

用法：
  python -m Agent.orchestrator --topic 科比去世
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypedDict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .agent import (
    AGENT_OUTPUT,
    SKILL_LOG,
    apply_plan_to_args,
    collect_topic,
    plan_with_llm,
    run_skill1_crawler,
    run_skill2_stance,
)
from Conclusion.pipeline import run_conclusion
from KnowledgeAugmentor.store import KnowledgeStore
from MultimodalAnalyzer.analyzer import AnalyzerConfig, run_analysis

# Skill4 启用条件阈值：D_text 总量超过此值即触发 RAG 补充
CONTEXT_TEXT_THRESHOLD = 200

State = dict[str, Any]
StepFn = Callable[[State], State]


class PipelineState(TypedDict, total=False):
    """LangGraph 状态 Schema（键与线性执行 State 保持一致）。"""

    topic: str
    args: Any
    plan: dict[str, Any]
    d_path: str | None
    d_platform: dict[str, Any] | None
    stance_profile: dict[str, Any] | None
    skill3: dict[str, Any] | None
    rag: dict[str, Any] | None
    conclusion: dict[str, Any] | None
    event_dir: str | None
    force_history: bool
    skill_log: list[dict[str, Any]]


def _safe(topic: str) -> str:
    return re.sub(r'[\\/:*?"<>|\s]+', "_", topic)[:40]


def _load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return json.load(f)


def _load_stance_profile(topic: str) -> dict[str, Any]:
    p = AGENT_OUTPUT / f"stance_profile_{_safe(topic)}.json"
    if p.exists():
        return _load_json(p)
    return {}


def _should_augment(
    d_platform: dict[str, Any],
    skill3: dict[str, Any],
    force_history: bool = False,
) -> bool:
    if force_history:
        return True
    meta = d_platform.get("D_meta") or {}
    if int(meta.get("n_text") or 0) > CONTEXT_TEXT_THRESHOLD:
        return True
    if any(a.get("type") == "cross_modal_inconsistency" for a in skill3.get("anomalies") or []):
        return True
    return False


# ---------------- Skill 步骤（LangGraph 节点与线性执行共用） ---------------- #

def step_crawl(state: State) -> State:
    """Skill1：采集 + 清洗 → D_platform.json。

    按 args.platform 分发：B站走专用爬虫；其余平台走通用 PlatformAdapter 流水线。
    """
    args = state["args"]
    platform = getattr(args, "platform", "bilibili") or "bilibili"

    if platform != "bilibili":
        from PlatformCrawler.pipeline import run_platform_pipeline

        d_platform = run_platform_pipeline(
            args.topic,
            platform,
            since=args.since,
            until=args.until,
            granularity=args.granularity,
            search_pages=getattr(args, "search_pages", 1),
            max_entities=getattr(args, "max_videos", 3),
            comment_pages=getattr(args, "comment_pages", 2),
            mode=getattr(args, "comment_mode", "latest"),
        )
        state["d_platform"] = d_platform
        state["d_path"] = str((d_platform.get("D_meta") or {}).get("text_uri") or "")
        return state

    d_path = run_skill1_crawler(args)
    state["d_path"] = str(d_path)
    state["d_platform"] = _load_json(d_path)
    return state


def step_stance(state: State) -> State:
    """Skill2：立场画像 → 刷新 D_platform + stance_profile。"""
    args = state["args"]
    stamped, event_dir = run_skill2_stance(Path(state["d_path"]), args)
    state["event_dir"] = str(event_dir) if event_dir else None
    state["d_platform"] = _load_json(stamped)
    state["stance_profile"] = _load_stance_profile(args.topic)
    return state


def step_analyze(state: State) -> State:
    """Skill3：多模态时序–文本分析。"""
    cfg = AnalyzerConfig(enable_text_tower=True)
    skill3 = run_analysis(
        state["d_platform"], cfg, out_dir=Path(__file__).resolve().parent / "outputs"
    )
    state["skill3"] = skill3
    return state


def step_augment(state: State) -> State:
    """Skill4（备用）：写入 + 按需检索。"""
    d_platform = state["d_platform"]
    store = KnowledgeStore()
    store.write_d_platform(d_platform)
    if _should_augment(d_platform, state.get("skill3") or {}, force_history=state.get("force_history", False)):
        keyword = (d_platform.get("D_meta") or {}).get("keyword") or state["args"].topic
        state["rag"] = store.retrieve(keyword, top_k=8, keyword=keyword)
    else:
        state["rag"] = None
    return state


def step_conclude(state: State) -> State:
    """Skill5+6：结论生成 + 严格校准。"""
    state["conclusion"] = run_conclusion(
        state["d_platform"],
        state.get("stance_profile") or None,
        state.get("skill3") or None,
        state.get("rag") or None,
        max_rounds=2,
    )
    return state


def build_state(topic: str, args: argparse.Namespace) -> State:
    return {
        "topic": topic,
        "args": args,
        "plan": getattr(args, "plan", {}),
        "d_path": None,
        "d_platform": None,
        "stance_profile": None,
        "skill3": None,
        "rag": None,
        "conclusion": None,
        "event_dir": None,
        "force_history": False,
        "skill_log": [],
    }


# ---------------- 执行编排 ---------------- #

def _run_step(name: str, fn: StepFn, state: State) -> State:
    """执行单个 Skill，记账状态；异常抛出并留痕。"""
    try:
        state = fn(state)
        state["skill_log"].append(
            {"skill": name, "status": "ok", "ts": datetime.now().isoformat(timespec="seconds")}
        )
        return state
    except Exception as e:
        state["skill_log"].append(
            {
                "skill": name,
                "status": "error",
                "error": str(e),
                "ts": datetime.now().isoformat(timespec="seconds"),
            }
        )
        raise


def run_linear(state: State) -> State:
    """线性执行（无 LangGraph 时的兜底）。"""
    state = _run_step("PlatformCrawler", step_crawl, state)
    state = _run_step("StanceProfiler", step_stance, state)
    state = _run_step("MultimodalAnalyzer", step_analyze, state)
    state = _run_step("KnowledgeAugmentor", step_augment, state)
    state = _run_step("Conclusion+Calibrator", step_conclude, state)
    return state


def build_langgraph():
    """构建 LangGraph 状态图；未安装 langgraph 时返回 None。"""
    try:
        from langgraph.graph import END, StateGraph  # type: ignore
    except ImportError:
        return None

    g = StateGraph(PipelineState)
    g.add_node("crawl", step_crawl)
    g.add_node("stance", step_stance)
    g.add_node("analyze", step_analyze)
    g.add_node("augment", step_augment)
    g.add_node("conclude", step_conclude)
    g.set_entry_point("crawl")
    g.add_edge("crawl", "stance")
    g.add_edge("stance", "analyze")
    g.add_edge("analyze", "augment")
    g.add_edge("augment", "conclude")
    g.add_edge("conclude", END)
    return g.compile()


def run_pipeline(topic: str, args: argparse.Namespace, *, use_langgraph: bool = True) -> State:
    state = build_state(topic, args)
    if use_langgraph:
        graph = build_langgraph()
        if graph is not None:
            # LangGraph 的节点返回值会作为状态更新写回
            return dict(graph.invoke(state))
    return run_linear(state)


def export_report(state: State) -> dict[str, Any]:
    """产出符合 multiagent.contract 的 PlatformReport（跨平台对齐层消费）。"""
    d_platform = state.get("d_platform") or {}
    meta = d_platform.get("D_meta") or {}
    stance = state.get("stance_profile") or {}
    skill3 = state.get("skill3") or {}
    conclusion = state.get("conclusion") or {}
    ot1 = conclusion.get("OT1") or {}
    rag = state.get("rag") or {}
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
        "stance_dist": stance.get("stance_ratios") or {},
        "top_tags": [c.get("label") for c in stance.get("keyword_clusters") or []],
        "skill3": {
            "anomalies": skill3.get("anomalies") or [],
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
            "evidence_ids": ot1.get("evidence_ids") or [],
        },
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def summarize(state: State) -> dict[str, Any]:
    """压缩成可提交的扁平摘要（调试/展示用；跨平台消费请用 export_report）。"""
    d_platform = state.get("d_platform") or {}
    meta = d_platform.get("D_meta") or {}
    conclusion = state.get("conclusion") or {}
    ot1 = conclusion.get("OT1") or {}
    skill3 = state.get("skill3") or {}
    return {
        "platform": meta.get("platform"),
        "keyword": meta.get("keyword"),
        "time_range": meta.get("time_range"),
        "granularity": meta.get("granularity"),
        "n_text": meta.get("n_text"),
        "empty_ratio": meta.get("empty_ratio"),
        "stance_global": meta.get("stance_global"),
        "bias_score": meta.get("bias_score"),
        "skill3_anomalies": skill3.get("anomalies") or [],
        "skill3_need_recrawl": skill3.get("need_recrawl"),
        "augment_used": bool((state.get("rag") or {}).get("augment_used")),
        "OT1_status": ot1.get("OT1_status"),
        "claim_trend": ot1.get("claim_trend"),
        "claim_topic_trend": ot1.get("claim_topic_trend"),
        "claim_stance": ot1.get("claim_stance"),
        "uncertainty": ot1.get("uncertainty"),
        "summary_analysis": ot1.get("summary_analysis"),
        "risk_flags": ot1.get("risk_flags") or [],
        "evidence_ids": ot1.get("evidence_ids") or [],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


def run_agent_full(args: argparse.Namespace, *, use_langgraph: bool = True) -> dict[str, Any]:
    """全链路入口：话题 → LLM 规划 → Skill1..6 → 报告。"""
    SKILL_LOG.clear()
    topic = collect_topic(args)
    plan = plan_with_llm(topic, args)
    args = apply_plan_to_args(args, plan)

    state = run_pipeline(topic, args, use_langgraph=use_langgraph)
    report = summarize(state)
    report["llm_plan"] = plan
    report["skill_log"] = state.get("skill_log") or []
    report["dataset_dir"] = state.get("event_dir")

    AGENT_OUTPUT.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = AGENT_OUTPUT / f"full_pipeline_{_safe(topic)}_{ts}.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 契约版平台报告（供多平台主控层消费）
    platform_report = export_report(state)
    pr_out = AGENT_OUTPUT / f"platform_report_{_safe(topic)}_{ts}.json"
    with pr_out.open("w", encoding="utf-8") as f:
        json.dump(platform_report, f, ensure_ascii=False, indent=2)
    report["platform_report"] = str(pr_out)

    print(f"\n[Orchestrator] 全链路报告 → {out}")
    print(f"[Orchestrator] 平台报告(契约) → {pr_out}")
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="单平台 Agent 全链路编排（Skill1→6）")
    p.add_argument("--topic", default=None, help="话题关键词（唯一必填的人工输入）")
    p.add_argument(
        "--platform",
        default="bilibili",
        choices=["bilibili", "weibo", "douyin", "xiaohongshu", "zhihu", "kuaishou"],
        help="目标平台；非 bilibili 时走通用 PlatformAdapter 流水线",
    )
    p.add_argument("--since", default=None, help="调试：强制覆盖评论窗开始日")
    p.add_argument("--until", default=None, help="调试：强制覆盖评论窗结束日")
    p.add_argument("--granularity", choices=["hour", "day"], default="day")
    p.add_argument("--search-pages", type=int, default=1)
    p.add_argument("--max-videos", type=int, default=None)
    p.add_argument("--no-second", action="store_true")
    p.add_argument("--to-dataset", action="store_true", default=True)
    p.add_argument("--no-dataset", action="store_true")
    p.add_argument("--event-title", default=None)
    p.add_argument("--description", default="")
    p.add_argument("--no-langgraph", action="store_true", help="禁用 LangGraph，走线性执行")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.no_dataset:
        args.to_dataset = False
    args._max_videos_cli = args.max_videos is not None
    if args.max_videos is None:
        args.max_videos = 2
    run_agent_full(args, use_langgraph=not args.no_langgraph)


if __name__ == "__main__":
    main()
