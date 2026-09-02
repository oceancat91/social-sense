"""Skill 封装层 + 跨平台 Agent + Skill 验证工具的回归测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
for _path in (str(AGENT_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# 测试运行时动态加入 agent/；IDE 的静态导入分析无法解析该路径。
# pylint: disable=wrong-import-position,import-error
from skills import registry  # noqa: E402
from multiagent.cross_platform_agent import CrossPlatformAgent  # noqa: E402
from tools.evaluate_skills import (  # noqa: E402
    evaluate_anomaly,
    evaluate_alignment,
    evaluate_stance,
)


def make_report(
    platform: str,
    keyword: str,
    start: str,
    *,
    n: int = 5,
    shift: float = 0.0,
) -> dict:
    d_ts = []
    for i in range(n):
        d_ts.append(
            {
                "ts": f"{start}T{i:02d}:00:00+08:00",
                "volume": 10.0 + i + shift,
                "heat": 12.0 + i,
                "sent_mean": 0.1,
                "sent_std": 0.05,
                "stance_pos_ratio": 0.3,
                "stance_neg_ratio": 0.1,
                "stance_neu_ratio": 0.6,
                "bias_proxy": 0.1,
                "controversy": 0.1,
                "is_empty": False,
            }
        )
    return {
        "platform": platform,
        "keyword": keyword,
        "meta": {
            "platform": platform,
            "keyword": keyword,
            "time_range": {"start": start, "end": start},
            "granularity": "hour",
            "n_text": n,
            "n_buckets": n,
            "empty_ratio": 0.0,
            "is_empty": False,
            "stance_global": "neutral",
            "bias_score": 0.1,
            "confidence": 0.5,
            "sentiment_global_mean": 0.1,
        },
        "D_ts": d_ts,
        "stance_dist": {
            "support": 0.3,
            "oppose": 0.1,
            "neutral": 0.6,
            "mixed": 0.0,
            "unclear": 0.0,
        },
    }


class SkillRegistryTests(unittest.TestCase):
    def test_five_skills_registered(self) -> None:
        names = registry.names()
        self.assertEqual(
            names,
            [
                "Conclusion",
                "KnowledgeAugmentor",
                "MultimodalAnalyzer",
                "PlatformCrawler",
                "StanceProfiler",
            ],
        )

    def test_skill_metadata(self) -> None:
        skill_cls = registry.get("StanceProfiler")
        self.assertEqual(skill_cls.name, "StanceProfiler")
        self.assertTrue(skill_cls.version)

    def test_get_missing_raises(self) -> None:
        with self.assertRaises(KeyError):
            registry.get("NonExistentSkill")


class CrossPlatformAgentTests(unittest.TestCase):
    def test_align_and_run_two_platforms(self) -> None:
        reports = [
            make_report("bilibili", "共同话题", "2026-01-01", n=6),
            make_report("weibo", "共同话题", "2026-01-01", n=4, shift=5.0),
        ]
        agent = CrossPlatformAgent(reports)
        self.assertEqual(set(agent.platforms), {"bilibili", "weibo"})
        # 覆盖度：weibo 桶少于 bilibili，缺失桶应被统计
        coverage = agent.coverage()
        self.assertLessEqual(
            coverage["weibo"]["n_buckets_own"], coverage["bilibili"]["n_buckets_own"]
        )
        ct = agent.run(use_llm=False)
        self.assertEqual(ct["CT_status"], "accepted")
        self.assertIn("score", ct["echo_chamber"])


class SkillValidationTests(unittest.TestCase):
    def test_evaluate_stance_golden(self) -> None:
        golden = AGENT_ROOT / "tools" / "golden_stance.json"
        result = evaluate_stance(golden)
        self.assertEqual(result["golden_n"], 40)
        # 立场标注高且稳定；情绪标注经 LLM 补充极性后应显著高于纯词表基线
        self.assertGreaterEqual(result["stance"]["accuracy"], 0.85)
        self.assertGreaterEqual(result["sentiment"]["accuracy"], 0.7)

    def test_evaluate_alignment_and_anomaly(self) -> None:
        reports_dir = AGENT_ROOT / "dataset" / "real_multiplatform" / "reports"
        if not reports_dir.is_dir():
            self.skipTest("真实多平台报告目录不存在")
        alignment = evaluate_alignment(reports_dir)
        self.assertEqual(alignment["n_topics"], 24)
        anomaly = evaluate_anomaly(reports_dir)
        self.assertEqual(anomaly["n_reports"], 60)


if __name__ == "__main__":
    unittest.main()
