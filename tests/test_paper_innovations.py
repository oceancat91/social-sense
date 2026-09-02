from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

# 测试运行时动态加入 agent/；IDE 的静态导入分析无法解析该路径。
# pylint: disable=wrong-import-position,import-error
from Conclusion.calib.gates import run_gates
from Conclusion.gen.prompts import build_evidence_package
from Conclusion.schema import normalize_ot0
from KnowledgeAugmentor.store import KnowledgeStore
from MultimodalAnalyzer.analyzer import AnalyzerConfig, run_analysis


def make_platform(
    values: list[float],
    *,
    keyword: str,
    start: str,
    platform: str = "douyin",
) -> dict:
    d_ts = []
    for i, value in enumerate(values):
        d_ts.append(
            {
                "ts": f"{start}T{i:02d}:00:00+08:00",
                "volume": value,
                "heat": value * 1.2,
                "topic_volume": value,
                "topic_heat": value * 1.5,
                "sent_mean": 0.1,
                "sent_std": 0.05,
                "controversy": 0.1,
                "bias_proxy": 0.1,
                "stance_pos_ratio": 0.2,
                "stance_neg_ratio": 0.1,
                "stance_neu_ratio": 0.7,
                "sample_content_ids": [f"{keyword}-{i}"],
                "is_empty": False,
            }
        )
    return {
        "D_meta": {
            "platform": platform,
            "keyword": keyword,
            "time_range": {"start": start, "end": start},
            "granularity": "hour",
            "n_text": len(values),
            "n_buckets": len(values),
            "empty_ratio": 0.0,
            "is_empty": False,
            "stance_global": "neutral",
        },
        "D_ts": d_ts,
        "D_text": [],
    }


class CrossADInspiredTests(unittest.TestCase):
    def test_multiscale_detects_scale_disagreement_and_severity(self) -> None:
        values = [10.0] * 15
        values[6:9] = [100.0, 100.0, 100.0]
        d_platform = make_platform(values, keyword="scale-event", start="2026-01-01")

        result = run_analysis(
            d_platform,
            AnalyzerConfig(
                enable_text_tower=False,
                multiscale_windows=(3, 9),
                tau=3.0,
                tau_cross_scale=3.0,
            ),
        )

        self.assertEqual(result["model_version"], "multimodal_analyzer_v2_cross_scale")
        self.assertEqual(result["multiscale"]["windows"], [3, 9])
        types = {item["type"] for item in result["anomalies"]}
        self.assertIn("volume_spike", types)
        self.assertIn("cross_scale_inconsistency", types)
        cross_scale = next(
            item
            for item in result["anomalies"]
            if item["type"] == "cross_scale_inconsistency"
        )
        self.assertEqual(cross_scale["severity"], "critical")
        self.assertIn("scale_scores", cross_scale["meta"])
        self.assertEqual(result["risk_summary"]["max_severity"], "critical")


class LLMADInspiredTests(unittest.TestCase):
    def test_retrieves_anomaly_and_normal_examples(self) -> None:
        normal = make_platform([10.0] * 12, keyword="normal-history", start="2025-01-01")
        anomaly_values = [10.0] * 12
        anomaly_values[5:8] = [90.0, 100.0, 90.0]
        anomaly = make_platform(
            anomaly_values, keyword="anomaly-history", start="2025-02-01"
        )
        current = make_platform(
            anomaly_values, keyword="current-event", start="2026-01-01"
        )
        anomaly_skill3 = {
            "anomalies": [
                {
                    "ts": anomaly["D_ts"][6]["ts"],
                    "type": "volume_spike",
                    "severity": "critical",
                    "evidence_ids": anomaly["D_ts"][6]["sample_content_ids"],
                }
            ],
            "risk_summary": {"max_severity": "critical"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            store = KnowledgeStore(Path(temp_dir) / "index.jsonl")
            store.write_analysis_case(
                normal,
                {"anomalies": [], "risk_summary": {"max_severity": "none"}},
            )
            store.write_analysis_case(anomaly, anomaly_skill3)

            examples = store.retrieve_analysis_examples(current)
            self.assertTrue(examples["example_retrieval_used"])
            self.assertEqual(len(examples["anomaly_examples"]), 1)
            self.assertEqual(len(examples["normal_examples"]), 1)
            self.assertEqual(
                examples["anomaly_examples"][0]["label_source"],
                "skill3_weak_label",
            )
            self.assertEqual(
                examples["retrieval_method"], "multivariate_znorm_dtw"
            )
            self.assertEqual(store.retrieve("anomaly")["rag_chunks"], [])

    def test_risk_gate_blocks_overstatement(self) -> None:
        d_platform = make_platform(
            [10.0] * 9, keyword="risk-gate", start="2026-02-01"
        )
        evidence_id = d_platform["D_ts"][4]["ts"]
        ot0 = normalize_ot0(
            {
                "claim_trend": "unknown",
                "claim_topic_trend": "unknown",
                "claim_sentiment": "unknown",
                "claim_stance": "unclear",
                "risk_level": "critical",
                "anomaly_reasoning": {
                    "global_observation": "整体平稳",
                    "local_evidence": [evidence_id],
                    "cross_check": "未发现跨模态冲突",
                    "reassessment": "已排除空窗",
                },
                "evidence_ids": [evidence_id],
                "uncertainty": "mid",
                "summary_analysis": "存在待复核异常。",
                "cited_bucket_ids": [evidence_id],
            }
        )
        skill3 = {
            "anomalies": [
                {
                    "ts": evidence_id,
                    "type": "volume_spike",
                    "severity": "warning",
                }
            ],
            "risk_summary": {"max_severity": "warning"},
        }

        report = run_gates(ot0, d_platform, skill3=skill3)
        self.assertEqual(report["status"], "fail")
        self.assertTrue(any(item["gate"] == "G7" for item in report["deviations"]))

    def test_evidence_package_contains_case_examples(self) -> None:
        d_platform = make_platform(
            [10.0] * 6, keyword="prompt-case", start="2026-03-01"
        )
        rag = {
            "augment_used": True,
            "rag_chunks": [],
            "anomaly_examples": [{"case_id": "a", "case_label": "anomaly"}],
            "normal_examples": [{"case_id": "n", "case_label": "normal"}],
            "retrieval_method": "multivariate_znorm_dtw",
        }
        package = build_evidence_package(
            d_platform,
            stance_profile=None,
            skill3={
                "anomalies": [],
                "risk_summary": {"max_severity": "none"},
                "multiscale": {"windows": [3, 5], "primary_window": 3},
            },
            rag=rag,
        )
        self.assertEqual(package["skill3"]["multiscale"]["windows"], [3, 5])
        self.assertEqual(package["rag"]["anomaly_examples"][0]["case_id"], "a")
        self.assertEqual(package["rag"]["normal_examples"][0]["case_id"], "n")


if __name__ == "__main__":
    unittest.main()
