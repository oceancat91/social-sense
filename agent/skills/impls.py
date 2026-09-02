"""六项 Skill 的具体实现：把各模块能力封装为可独立调用、可验证的单元。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# —— 路径注入：agent 目录（顶层包）+ 仓库根（multiagent 包）—— #
AGENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_DIR.parent
for _path in (str(AGENT_DIR), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position,import-error
from MultimodalAnalyzer.analyzer import AnalyzerConfig, run_analysis  # noqa: E402
from PlatformCrawler.dataloader.builder import build_d_platform  # noqa: E402
from PlatformCrawler.dataloader.cleaner import clean_records  # noqa: E402
from StanceProfiler.profiler import profile_d_platform  # noqa: E402

from .base import Skill, SkillContext  # noqa: E402
from .registry import register  # noqa: E402


@register
class PlatformCrawlerSkill(Skill):
    """Skill1：采集 + 清洗 → D_platform。

    输入优先级：
      1. ``ctx.d_platform`` 已存在 → 幂等跳过；
      2. ``ctx.raw_records`` 提供原始字段 → 清洗 + 建包；
      3. ``ctx.args`` 提供爬虫参数 → 委托 PlatformCrawler 流水线。
    """

    name = "PlatformCrawler"
    version = "platform_crawler_v1"

    def run(self, ctx: SkillContext) -> SkillContext:
        if ctx.d_platform is not None:
            ctx.record(self.name, "skip", reason="d_platform 已存在")
            return ctx

        if ctx.raw_records is not None:
            since, until = ctx.time_range or (None, None)  # type: ignore[misc]
            if not since or not until:
                # 从原始字段推导时间窗
                from datetime import datetime, timedelta

                days = sorted(
                    {str(r.get("ts_raw") or "")[:10] for r in ctx.raw_records}
                )
                since, _ = days[0], days[-1]
                until = (
                    datetime.strptime(days[-1], "%Y-%m-%d") + timedelta(days=1)
                ).strftime("%Y-%m-%d")
            from datetime import datetime as _dt
            from zoneinfo import ZoneInfo

            tz = ZoneInfo("Asia/Shanghai")
            start = _dt.strptime(since, "%Y-%m-%d").replace(tzinfo=tz)
            end = _dt.strptime(until, "%Y-%m-%d").replace(tzinfo=tz)
            bundle = clean_records(
                ctx.raw_records, time_range=(start, end), platform=ctx.platform
            )
            ctx.d_platform = build_d_platform(
                bundle,
                keyword=ctx.keyword,
                time_range=(since, until),
                granularity=ctx.granularity,
                platform=ctx.platform,
            )
            ctx.record(self.name, "ok", source="raw_records")
            return ctx

        if ctx.args is not None:
            platform = ctx.platform
            if platform != "bilibili":
                from PlatformCrawler.pipeline import run_platform_pipeline

                ctx.d_platform = run_platform_pipeline(
                    ctx.keyword,
                    platform,
                    since=getattr(ctx.args, "since", None),
                    until=getattr(ctx.args, "until", None),
                    granularity=ctx.granularity,
                )
            else:
                from agent.agent import run_skill1_crawler

                d_path = run_skill1_crawler(ctx.args)
                import json

                ctx.d_platform = json.loads(Path(d_path).read_text(encoding="utf-8"))
            ctx.record(self.name, "ok", source="crawler")
            return ctx

        raise ValueError("PlatformCrawler 需要 raw_records / d_platform / args 之一")


@register
class StanceProfilerSkill(Skill):
    """Skill2：立场/情绪画像 → 刷新 D_platform + stance_profile。"""

    name = "StanceProfiler"
    version = "stance_profiler_v2"

    def run(self, ctx: SkillContext) -> SkillContext:
        if ctx.d_platform is None:
            raise ValueError("StanceProfiler 需要 D_platform")
        ctx.d_platform, ctx.stance_profile = profile_d_platform(ctx.d_platform)
        ctx.record(self.name, "ok")
        return ctx


@register
class MultimodalAnalyzerSkill(Skill):
    """Skill3：多尺度时间-文本异常检测 → skill3。"""

    name = "MultimodalAnalyzer"
    version = "multimodal_analyzer_v2_cross_scale"

    def __init__(self, enable_text_tower: bool = True) -> None:
        self.enable_text_tower = enable_text_tower

    def run(self, ctx: SkillContext) -> SkillContext:
        if ctx.d_platform is None:
            raise ValueError("MultimodalAnalyzer 需要 D_platform")
        cfg = AnalyzerConfig(enable_text_tower=self.enable_text_tower)
        ctx.skill3 = run_analysis(ctx.d_platform, cfg)
        ctx.record(self.name, "ok")
        return ctx


@register
class KnowledgeAugmentorSkill(Skill):
    """Skill4：知识库写入 + BM25/DTW 案例检索（备用补充）。"""

    name = "KnowledgeAugmentor"
    version = "knowledge_augmentor_v2_case_icl"

    def __init__(self, index_path: str | Path | None = None) -> None:
        self.index_path = index_path

    def run(self, ctx: SkillContext) -> SkillContext:
        from KnowledgeAugmentor.store import KnowledgeStore

        if ctx.d_platform is None:
            raise ValueError("KnowledgeAugmentor 需要 D_platform")
        store = KnowledgeStore(self.index_path)
        store.write_d_platform(ctx.d_platform)
        case_examples = store.retrieve_analysis_examples(ctx.d_platform)

        if case_examples.get("example_retrieval_used"):
            ctx.rag = {
                **case_examples,
                "augment_used": True,
                "rag_chunks": [],
                "history_cases": [],
            }
        else:
            keyword = (
                (ctx.d_platform.get("D_meta") or {}).get("keyword") or ctx.keyword
            )
            ctx.rag = store.retrieve(keyword, top_k=8, keyword=keyword)

        store.write_analysis_case(ctx.d_platform, ctx.skill3 or {})
        ctx.record(self.name, "ok", augment_used=bool((ctx.rag or {}).get("augment_used")))
        return ctx


@register
class ConclusionSkill(Skill):
    """Skill5+6：结论生成 + 严格校准 → conclusion(OT1)。"""

    name = "Conclusion"
    version = "conclusion_v2_risk_gate"

    def __init__(self, max_rounds: int = 2) -> None:
        self.max_rounds = max_rounds

    def run(self, ctx: SkillContext) -> SkillContext:
        from Conclusion.pipeline import run_conclusion

        if ctx.d_platform is None:
            raise ValueError("Conclusion 需要 D_platform")
        ctx.conclusion = run_conclusion(
            ctx.d_platform,
            ctx.stance_profile,
            ctx.skill3,
            ctx.rag,
            max_rounds=self.max_rounds,
        )
        ctx.record(self.name, "ok")
        return ctx


def run_pipeline(ctx: SkillContext, *, enable_text_tower: bool = True) -> SkillContext:
    """按 Skill1→6 顺序串行执行（单平台完整链路）。"""
    names = [
        "PlatformCrawler",
        "StanceProfiler",
        "MultimodalAnalyzer",
        "KnowledgeAugmentor",
        "Conclusion",
    ]
    for name in names:
        skill_cls = registry.get(name)
        if name == "MultimodalAnalyzer":
            skill = skill_cls(enable_text_tower=enable_text_tower)
        else:
            skill = skill_cls()
        ctx = skill.run(ctx)
    return ctx
