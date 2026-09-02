"""Skill 准确率验证 + 历史数据验证。

验证三个问题：
  1. StanceProfiler（Skill2）：用人工标注 golden 计算立场/情绪标注准确率；
  2. 跨平台对齐/融合：用真实历史数据验证时间覆盖度与茧房指数；
  3. MultimodalAnalyzer（Skill3）：统计历史数据上的异常检测行为。

用法：
  python -m tools.evaluate_skills [--golden tools/golden_stance.json] \
      [--reports-dir dataset/real_multiplatform/reports] \
      [--out dataset/eval/evaluation_report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# —— 路径注入：agent 目录（顶层包）+ 仓库根（multiagent 包）—— #
AGENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_DIR.parent
for _path in (str(AGENT_DIR), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position,import-error
from StanceProfiler.labelers.lexicon import LexiconLabeler  # noqa: E402
from multiagent.cross_platform_agent import CrossPlatformAgent  # noqa: E402

STANCE_CLASSES = ("support", "oppose", "neutral", "mixed", "unclear")
SENT_CLASSES = ("pos", "neu", "neg")


def _sentiment_class(score: float) -> str:
    if score > 0.15:
        return "pos"
    if score < -0.15:
        return "neg"
    return "neu"


def _prf(
    y_true: list[str],
    y_pred: list[str],
    classes: list[str],
) -> dict[str, Any]:
    """计算 accuracy、各类 precision/recall/f1、宏平均与混淆矩阵。"""
    pairs = list(zip(y_true, y_pred))
    n = len(pairs)
    correct = sum(1 for t, p in pairs if t == p)
    confusion = Counter(f"{t}->{p}" for t, p in pairs)

    per_class: dict[str, dict[str, Any]] = {}
    p_sum = r_sum = f_sum = 0.0
    for cls in classes:
        tp = sum(1 for t, p in pairs if t == cls and p == cls)
        fp = sum(1 for t, p in pairs if t != cls and p == cls)
        fn = sum(1 for t, p in pairs if t == cls and p != cls)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        per_class[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
        p_sum += precision
        r_sum += recall
        f_sum += f1

    m = len(classes) or 1
    return {
        "accuracy": round(correct / n, 4) if n else 0.0,
        "macro_precision": round(p_sum / m, 4),
        "macro_recall": round(r_sum / m, 4),
        "macro_f1": round(f_sum / m, 4),
        "per_class": per_class,
        "confusion": dict(confusion),
    }


def evaluate_stance(golden_path: str | Path) -> dict[str, Any]:
    """用人工标注 golden 计算 Skill2 立场/情绪准确率。"""
    golden = json.loads(Path(golden_path).read_text(encoding="utf-8"))

    labelers: dict[str, LexiconLabeler] = {}
    y_true_stance: list[str] = []
    y_pred_stance: list[str] = []
    y_true_sent: list[str] = []
    y_pred_sent: list[str] = []
    errors: list[dict[str, Any]] = []

    for item in golden:
        text = str(item.get("text") or "")
        platform = str(item.get("platform") or "")
        gold_stance = str(item.get("stance") or "unclear")
        gold_sent = str(item.get("sentiment") or "neu")

        labeler = labelers.get(platform)
        if labeler is None:
            labeler = LexiconLabeler(platform=platform or None)
            labelers[platform] = labeler
        ann = labeler.label(text)

        pred_stance = str(ann.get("stance_label") or "unclear")
        pred_sent = _sentiment_class(float(ann.get("sentiment_score") or 0.0))

        y_true_stance.append(gold_stance)
        y_pred_stance.append(pred_stance)
        y_true_sent.append(gold_sent)
        y_pred_sent.append(pred_sent)

        if pred_stance != gold_stance or pred_sent != gold_sent:
            errors.append(
                {
                    "text": text,
                    "platform": platform,
                    "stance": {"gold": gold_stance, "pred": pred_stance},
                    "sentiment": {"gold": gold_sent, "pred": pred_sent},
                }
            )

    return {
        "golden_n": len(golden),
        "stance": _prf(y_true_stance, y_pred_stance, list(STANCE_CLASSES)),
        "sentiment": _prf(y_true_sent, y_pred_sent, list(SENT_CLASSES)),
        "errors": errors,
        "n_errors": len(errors),
    }


def _group_reports(reports: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """按 (scope, keyword) 分组；scope 来自 source.scope，缺省按关键词。"""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in reports:
        source = r.get("source") or {}
        scope = str(source.get("scope") or "broad")
        keyword = str(
            r.get("keyword")
            or (r.get("meta") or {}).get("keyword")
            or source.get("domain_name")
            or "unknown"
        )
        groups[(scope, keyword)].append(r)
    return groups


def evaluate_alignment(reports_dir: str | Path) -> dict[str, Any]:
    """用真实历史数据验证跨平台对齐：覆盖度 + 分歧 + 茧房指数。"""
    reports = []
    for path in sorted(Path(reports_dir).rglob("*.json")):
        reports.append(json.loads(path.read_text(encoding="utf-8")))

    topics: list[dict[str, Any]] = []
    for (scope, keyword), rs in sorted(_group_reports(reports).items()):
        if len(rs) < 2:
            continue
        agent = CrossPlatformAgent(rs)
        coverage = agent.coverage()
        ct = agent.run(use_llm=False)
        fusion = ct.get("fusion") or {}
        topics.append(
            {
                "topic": f"{scope}:{keyword}",
                "platforms": [str(r.get("platform")) for r in rs],
                "time_axis_length": len(agent.time_axis),
                "coverage": coverage,
                "echo_chamber_score": (ct.get("echo_chamber") or {}).get("score"),
                "stance_divergence": fusion.get("stance_divergence"),
                "sentiment_divergence": fusion.get("sentiment_divergence"),
                "CT_status": ct.get("CT_status"),
            }
        )

    return {"n_topics": len(topics), "topics": topics}


def evaluate_anomaly(reports_dir: str | Path) -> dict[str, Any]:
    """统计历史数据上的 Skill3 异常检测行为。"""
    type_counter: Counter[str] = Counter()
    severity_counter: Counter[str] = Counter()
    n_reports = 0
    n_need_recrawl = 0

    for path in sorted(Path(reports_dir).rglob("*.json")):
        report = json.loads(path.read_text(encoding="utf-8"))
        skill3 = report.get("skill3") or {}
        n_reports += 1
        if skill3.get("need_recrawl"):
            n_need_recrawl += 1

        # 严重度优先用存储的全量计数（生成时已聚合），缺失时回退到逐条统计
        stored_severity = skill3.get("severity_counts")
        if stored_severity:
            for key, value in stored_severity.items():
                severity_counter[str(key)] += int(value or 0)
        else:
            for anomaly in skill3.get("anomalies") or []:
                severity_counter[str(anomaly.get("severity") or "warning")] += 1

        # 异常类型优先用存储的全量计数，缺失时回退到逐条统计
        stored_types = skill3.get("anomaly_type_counts")
        if stored_types:
            for key, value in stored_types.items():
                type_counter[str(key)] += int(value or 0)
        else:
            for anomaly in skill3.get("anomalies") or []:
                anomaly_type = anomaly.get("type")
                if anomaly_type:
                    type_counter[str(anomaly_type)] += 1

    return {
        "n_reports": n_reports,
        "n_need_recrawl": n_need_recrawl,
        "anomaly_type_distribution": dict(type_counter),
        "severity_distribution": dict(severity_counter),
        "note": (
            "severity_distribution 来自报告内置的全量 severity_counts；"
            "anomaly_type_distribution 来自报告内置的 anomaly_type_counts，"
            "旧报告未内置时回退到 top-100 异常统计"
        ),
    }


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Skill 准确率验证 + 历史数据验证")
    parser.add_argument(
        "--golden", default="tools/golden_stance.json", help="人工标注 golden JSON"
    )
    parser.add_argument(
        "--reports-dir",
        default="dataset/real_multiplatform/reports",
        help="平台报告目录",
    )
    parser.add_argument(
        "--out", default="dataset/eval/evaluation_report.json", help="输出报告 JSON"
    )
    args = parser.parse_args(argv)

    golden_path = Path(args.golden)
    if not golden_path.is_absolute():
        golden_path = AGENT_DIR / golden_path
    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_absolute():
        reports_dir = AGENT_DIR / reports_dir

    print(f"==> 立场/情绪标注验证：{golden_path}")
    stance = evaluate_stance(golden_path)
    print(
        f"    golden_n={stance['golden_n']} "
        f"立场 acc={stance['stance']['accuracy']} macro_f1={stance['stance']['macro_f1']} "
        f"情绪 acc={stance['sentiment']['accuracy']} macro_f1={stance['sentiment']['macro_f1']}"
    )

    print(f"==> 跨平台对齐验证：{reports_dir}")
    alignment = evaluate_alignment(reports_dir)
    print(f"    对齐话题数={alignment['n_topics']}")

    print(f"==> Skill3 异常检测验证：{reports_dir}")
    anomaly = evaluate_anomaly(reports_dir)
    print(
        f"    报告数={anomaly['n_reports']} 需回采={anomaly['n_need_recrawl']} "
        f"异常类型={anomaly['anomaly_type_distribution']}"
    )

    report = {
        "schema_version": "skill_evaluation_v1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stance_profiler": stance,
        "cross_platform": alignment,
        "multimodal_analyzer": anomaly,
    }

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = AGENT_DIR / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n评估报告已保存：{out_path}")
    return report


if __name__ == "__main__":
    main()
