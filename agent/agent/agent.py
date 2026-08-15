"""
单平台舆情感知 Agent（当前仅启用 Skill1 + Skill2）

职责：
  - 人工只输入「话题」
  - LLM（DeepSeek）自行规划 since/until 与采集参数
  - 调度 PlatformCrawler → StanceProfiler
  - 归档到 dataset/

用法：
  python -m Agent --topic 科比去世
  python -m Agent
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .llm_plan import fallback_plan, plan_analysis_window
from PlatformCrawler.pipeline import (
    OUTPUT_DIR,
    run_crawl_comments,
    run_dataloader,
    run_search,
    run_search_heat_pool,
)
from StanceProfiler.archive import archive_event
from StanceProfiler.profiler import profile_d_platform

AGENT_OUTPUT = Path(__file__).resolve().parent / "outputs"
SKILL_LOG: list[dict[str, Any]] = []


def _log_skill(name: str, status: str, detail: dict[str, Any] | None = None) -> None:
    SKILL_LOG.append(
        {
            "skill": name,
            "status": status,
            "detail": detail or {},
            "ts": datetime.now().isoformat(timespec="seconds"),
        }
    )


def _ask(prompt: str, default: str | None = None) -> str:
    tip = f"{prompt}" + (f" [{default}]" if default else "") + ": "
    val = input(tip).strip()
    if not val and default is not None:
        return default
    return val


def collect_topic(args: argparse.Namespace) -> str:
    topic = (args.topic or "").strip()
    if not topic:
        print("\n=== 单平台舆情 Agent（Skill1+Skill2）===")
        print("请输入要分析的话题（必填）。长轴热度由 LLM 规划；评论固定 2 页近期抽样。")
        topic = _ask("话题关键词")
    if not topic:
        raise SystemExit("未提供话题，Agent 不会自行编造话题。")
    return topic


def plan_with_llm(topic: str, args: argparse.Namespace) -> dict[str, Any]:
    """LLM 规划时间窗；可用 --since/--until 强制覆盖（调试用）。"""
    print("\n[Agent] 调用 LLM 规划分析时间窗与采集参数 …")
    try:
        plan = plan_analysis_window(topic)
        _log_skill("LLMPlanner", "ok", {"plan": plan})
    except Exception as e:
        print(f"[Agent] LLM 规划失败，启用本地兜底：{e}")
        plan = fallback_plan(topic)
        _log_skill("LLMPlanner", "fallback", {"error": str(e), "plan": plan})

    # 调试覆盖
    if args.since:
        plan["since"] = args.since
    if args.until:
        plan["until"] = args.until
    if args.max_videos is not None and getattr(args, "_max_videos_cli", False):
        plan["max_videos"] = args.max_videos

    print("[Agent] LLM 规划结果：")
    print(
        json.dumps(
            {
                "topic": topic,
                "analysis_mode": plan.get("analysis_mode"),
                "event_start": plan.get("event_start"),
                "heat_axis": [plan["since"], plan["until"]],
                "comment_window": [
                    plan.get("comment_since"),
                    plan.get("comment_until"),
                ],
                "comment_pages": plan.get("comment_pages"),
                "video_search_window": [
                    plan.get("search_since"),
                    plan.get("search_until"),
                ],
                "max_videos": plan.get("max_videos"),
                "heat_search_pages": plan.get("heat_search_pages"),
                "heat_max_videos": plan.get("heat_max_videos"),
                "rationale": plan.get("rationale"),
                "planned_by": plan.get("planned_by"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return plan


def apply_plan_to_args(args: argparse.Namespace, plan: dict[str, Any]) -> argparse.Namespace:
    args.topic = plan["topic"]
    # D_ts / topic_heat 长轴
    args.since = plan["since"]
    args.until = plan["until"]
    # 评论抓取窗（近期）+ 固定 2 页
    args.comment_since = plan.get("comment_since") or plan["since"]
    args.comment_until = plan.get("comment_until") or plan["until"]
    args.search_since = plan.get("search_since") or plan["since"]
    args.search_until = plan.get("search_until") or plan["until"]
    args.max_videos = int(plan.get("max_videos") or 2)
    args.comment_pages = 2  # 硬限制：评论只爬两页
    args.heat_search_pages = int(plan.get("heat_search_pages") or 3)
    args.heat_max_videos = int(plan.get("heat_max_videos") or 100)
    args.search_pages = int(plan.get("search_pages") or args.heat_search_pages)
    args.order = plan.get("order") or "click"
    args.rank_by = plan.get("rank_by") or "play"
    args.comment_mode = plan.get("comment_mode") or "latest"
    args.plan = plan
    return args


def run_skill1_crawler(args: argparse.Namespace) -> Path:
    print("\n[Agent] 调度 Skill1 PlatformCrawler …")
    try:
        # 1) 话题热度池：爆发→至今的发布分布
        heat_videos = run_search_heat_pool(
            args.topic,
            pages=getattr(args, "heat_search_pages", 3),
            max_videos=getattr(args, "heat_max_videos", 100),
            order="pubdate",
            since=args.search_since,
            until=args.search_until,
        )
        # 2) 评论目标：Top-N
        videos = run_search(
            args.topic,
            pages=args.search_pages,
            max_videos=args.max_videos,
            order=args.order,
            rank_by=args.rank_by,
            since=args.search_since,
            until=args.search_until,
        )
        if not videos and heat_videos:
            videos = heat_videos[: args.max_videos]

        if not videos:
            print("[Agent] 搜索无视频，仍生成空时间轴 D_platform（可含 topic_heat）。")
            d = run_dataloader(
                [],
                keyword=args.topic,
                since=args.since,
                until=args.until,
                granularity=args.granularity,
                heat_videos=heat_videos,
            )
        else:
            csv_paths = run_crawl_comments(
                videos,
                comment_pages=args.comment_pages,
                no_second=args.no_second,
                mode=args.comment_mode,
                since=args.comment_since,
                until=args.comment_until,
            )
            d = run_dataloader(
                csv_paths,
                keyword=args.topic,
                since=args.since,
                until=args.until,
                granularity=args.granularity,
                heat_videos=heat_videos or videos,
            )

        out = Path(d["D_meta"].get("text_uri") or "")
        if not out.exists():
            safe = re.sub(r'[\\/:*?"<>|\s]+', "_", args.topic)[:40]
            cand = list(OUTPUT_DIR.glob(f"D_platform_{safe}_*.json"))
            if not cand:
                raise FileNotFoundError("Skill1 未产出 D_platform.json")
            out = max(cand, key=lambda p: p.stat().st_mtime)

        _log_skill(
            "PlatformCrawler",
            "ok",
            {
                "D_platform": str(out),
                "n_text": d["D_meta"].get("n_text"),
                "n_text_raw_in": d["D_meta"].get("n_text_raw_in"),
                "is_empty": d["D_meta"].get("is_empty"),
                "n_videos": len(videos) if videos else 0,
            },
        )
        print(f"[Agent] Skill1 完成 → {out}")
        return out
    except Exception as e:
        _log_skill("PlatformCrawler", "error", {"error": str(e)})
        raise


def run_skill2_stance(d_path: Path, args: argparse.Namespace) -> tuple[Path, Path | None]:
    print("\n[Agent] 调度 Skill2 StanceProfiler …")
    try:
        with d_path.open("r", encoding="utf-8") as f:
            d_in = json.load(f)

        d_out, profile = profile_d_platform(d_in)
        AGENT_OUTPUT.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[\\/:*?"<>|\s]+', "_", args.topic)[:40]
        stamped = AGENT_OUTPUT / f"D_platform_{safe}_stanced.json"
        profile_path = AGENT_OUTPUT / f"stance_profile_{safe}.json"

        with stamped.open("w", encoding="utf-8") as f:
            json.dump(d_out, f, ensure_ascii=False, indent=2)
        with profile_path.open("w", encoding="utf-8") as f:
            json.dump(profile, f, ensure_ascii=False, indent=2)

        event_dir = None
        if args.to_dataset:
            plan = getattr(args, "plan", {}) or {}
            event_dir = archive_event(
                d_out,
                profile,
                event_title=args.event_title or args.topic,
                description=args.description
                or f"Agent 自动链路：话题「{args.topic}」。LLM 规划：{plan.get('rationale','')}",
                source_notes=(
                    f"mode={plan.get('analysis_mode')}, "
                    f"heat_axis=[{args.since},{args.until}], "
                    f"comment=[{args.comment_since},{args.comment_until}]×{args.comment_pages}p, "
                    f"search=[{args.search_since},{args.search_until}], "
                    f"max_videos={args.max_videos}"
                ),
            )

        _log_skill(
            "StanceProfiler",
            "ok",
            {
                "D_platform": str(stamped),
                "stance_profile": str(profile_path),
                "stance_global": d_out["D_meta"].get("stance_global"),
                "stance_provisional": (d_out["D_meta"].get("ext") or {}).get(
                    "stance_provisional"
                ),
                "n_text": d_out["D_meta"].get("n_text"),
                "dataset_dir": str(event_dir) if event_dir else None,
            },
        )
        print(f"[Agent] Skill2 完成 → {stamped}")
        if event_dir:
            print(f"[Agent] 已归档 dataset → {event_dir}")
        return stamped, Path(event_dir) if event_dir else None
    except Exception as e:
        _log_skill("StanceProfiler", "error", {"error": str(e)})
        raise


def verify_skills_used() -> bool:
    ok_skills = {x["skill"] for x in SKILL_LOG if x["status"] in ("ok", "fallback")}
    # LLM 可为 fallback；两个主 Skill 必须 ok
    main_ok = any(
        x["skill"] == "PlatformCrawler" and x["status"] == "ok" for x in SKILL_LOG
    ) and any(x["skill"] == "StanceProfiler" and x["status"] == "ok" for x in SKILL_LOG)
    print("\n=== Skill 调用核验 ===")
    for item in SKILL_LOG:
        print(f"  - {item['skill']}: {item['status']}")
    print(
        "结论:",
        "✓ Agent 已用 LLM 规划时间窗，并正确调用 Skill1 + Skill2"
        if main_ok
        else "✗ 主 Skill 调用不完整",
    )
    return main_ok


def run_agent(args: argparse.Namespace) -> dict[str, Any]:
    SKILL_LOG.clear()
    topic = collect_topic(args)
    plan = plan_with_llm(topic, args)
    args = apply_plan_to_args(args, plan)

    d1 = run_skill1_crawler(args)
    d2, event_dir = run_skill2_stance(d1, args)
    ok = verify_skills_used()

    report = {
        "ok": ok,
        "topic": args.topic,
        "llm_plan": plan,
        "skill1_output": str(d1),
        "skill2_output": str(d2),
        "dataset_dir": str(event_dir) if event_dir else None,
        "skill_log": SKILL_LOG,
    }
    AGENT_OUTPUT.mkdir(parents=True, exist_ok=True)
    report_path = AGENT_OUTPUT / "last_run_report.json"
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n[Agent] 运行报告 → {report_path}")
    return report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="单平台舆情 Agent（话题人工输入，时间窗 LLM 规划）")
    p.add_argument("--topic", default=None, help="话题关键词（唯一必填的人工输入）")
    p.add_argument("--since", default=None, help="调试：强制覆盖评论窗开始日")
    p.add_argument("--until", default=None, help="调试：强制覆盖评论窗结束日")
    p.add_argument("--granularity", choices=["hour", "day"], default="day")
    p.add_argument("--search-pages", type=int, default=1)
    p.add_argument("--max-videos", type=int, default=None, help="调试：覆盖 LLM 的视频数")
    p.add_argument("--no-second", action="store_true")
    p.add_argument("--to-dataset", action="store_true", default=True)
    p.add_argument("--no-dataset", action="store_true")
    p.add_argument("--event-title", default=None)
    p.add_argument("--description", default="")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.no_dataset:
        args.to_dataset = False
    args._max_videos_cli = args.max_videos is not None
    if args.max_videos is None:
        args.max_videos = 2
    run_agent(args)


if __name__ == "__main__":
    main()
