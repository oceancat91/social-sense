"""把跨平台观测数据写成 RhineLab 阵列要求的 5 列 × 8 份档案。

注意：档案数据的**权威来源已改为后端**（``backend/app/services/archive_service.py``，
经 ``GET /api/v1/archives`` 下发，见 ``src/archives-api.ts``）。本脚本现在只负责生成
构建期兜底副本 ``content/archives.json``——后端不可用或离线时前端回落到它。

两处实现必须保持一致：修改映射规则时请同时改 archive_service.py，并重新生成：
    python frontend/scripts/build-sense-archives.py
（两边产出目前逐字段相同，可用 scripts/check-content.mjs 校验。）

文字原则：abstract 只写该领域的结论，findings 只放数值。
不放方法论免责句——那些对四十份档案同样成立，重复四十遍只是噪音。
空窗这类「必须诚实」的信息改成数据驱动：只在真的偏高时才出现。
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "agent" / "dataset" / "real_multiplatform" / "reports"
EVAL = ROOT / "agent" / "dataset" / "eval" / "evaluation_report.json"
OUT = Path(__file__).resolve().parents[1] / "content" / "archives.json"
SOURCE = "https://github.com/oceancat91/social-sense"

CATEGORIES = ["舆情概览", "跨平台结论", "节奏对齐", "立场共振", "分歧演化"]
COLUMNS = ["节奏对齐", "立场共振", "舆情概览", "分歧演化", "跨平台结论"]
DOMAINS = [
    ("education_science", "教育科研与科普", "EDUCATION & SCIENCE"),
    ("entertainment", "影视娱乐与明星", "FILM & ENTERTAINMENT"),
    ("public_affairs", "时政与公共治理", "PUBLIC AFFAIRS"),
    ("society_law", "社会事件与法治", "SOCIETY & LAW"),
    ("technology_industry", "科技工业与交通", "TECHNOLOGY & INDUSTRY"),
    ("health_psychology", "医疗健康与心理", "HEALTH & PSYCHOLOGY"),
    ("economy_business", "财经商业与职场", "ECONOMY & BUSINESS"),
    ("sports_fitness", "体育竞技与健身", "SPORTS & FITNESS"),
]
STANCE_ZH = {
    "support": "支持",
    "oppose": "反对",
    "neutral": "中立",
    "mixed": "混合",
    "unclear": "不明",
}
PLATFORM_ZH = {"bilibili": "B站", "weibo": "微博"}
# 空窗过半才提示：低于此值时读者自己能从数字看出稀疏程度，无需额外一句。
EMPTY_NOTE_AT = 0.7


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def load_platform(platform: str, code: str) -> dict:
    data = json.loads((REPORTS / platform / f"{code}__broad.json").read_text(encoding="utf-8"))
    meta = data["meta"]
    return {
        "name": PLATFORM_ZH[platform],
        "n_text": int(meta["n_text"]),
        "n_buckets": int(meta["n_buckets"]),
        "empty_ratio": float(meta["empty_ratio"]),
        "stance": STANCE_ZH.get(str(meta["stance_global"]), str(meta["stance_global"])),
        "bias": float(meta["bias_score"]),
        "confidence": float(meta["confidence"]),
        "sentiment": float(meta["sentiment_global_mean"]),
        "start": str(meta["time_range"]["start"])[:10],
        "end": str(meta["time_range"]["end"])[:10],
        "dist": data.get("stance_dist") or {},
        "sent_dist": (data.get("stance_profile") or {}).get("sentiment_dist") or {},
    }


def stance_split(side: dict) -> str:
    d = side["dist"]
    return (
        f"{side['name']} 支持 {pct(float(d.get('support', 0)))}"
        f" / 反对 {pct(float(d.get('oppose', 0)))}"
        f" / 中立 {pct(float(d.get('neutral', 0)))}"
    )


def sentiment_split(side: dict) -> str:
    d = side["sent_dist"]
    return (
        f"{side['name']} 正 {pct(float(d.get('pos', 0)))}"
        f" / 中 {pct(float(d.get('neu', 0)))}"
        f" / 负 {pct(float(d.get('neg', 0)))}"
    )


def build(category: str, title: str, sides: list[dict], topic: dict) -> tuple[str, list[str]]:
    left, right = sides
    coverage = topic["coverage"]
    axis = topic["time_axis_length"]
    echo = float(topic["echo_chamber_score"])
    stance_gap = float(topic["stance_divergence"])
    sent_gap = float(topic["sentiment_divergence"])
    status = topic["CT_status"]
    span = f"{min(left['start'], right['start'])} 至 {max(left['end'], right['end'])}"

    if category == "舆情概览":
        confidence = (left["confidence"] + right["confidence"]) / 2
        abstract = (
            f"{title}：{left['name']} {left['n_text']} 条、{right['name']} {right['n_text']} 条，"
            f"观测 {span}。"
        )
        findings = [
            f"时间桶 {left['name']} {left['n_buckets']} / {right['name']} {right['n_buckets']}",
            f"空窗 {left['name']} {pct(left['empty_ratio'])} / {right['name']} {pct(right['empty_ratio'])}",
            f"综合置信 {confidence:.2f}",
        ]
        if max(left["empty_ratio"], right["empty_ratio"]) >= EMPTY_NOTE_AT:
            findings.append("空窗偏高，只记录已观测分布")
        return abstract, findings

    if category == "跨平台结论":
        abstract = f"{title}：融合 {status}，对齐轴长 {axis}，茧房指数 {echo:.3f}。"
        findings = [
            f"{left['name']} {left['stance']}（偏向 {left['bias']:.2f}，情绪 {left['sentiment']:+.3f}）",
            f"{right['name']} {right['stance']}（偏向 {right['bias']:.2f}，情绪 {right['sentiment']:+.3f}）",
            f"立场分歧 {stance_gap:.4f} / 情绪分歧 {sent_gap:.4f}",
        ]
        return abstract, findings

    if category == "节奏对齐":
        abstract = (
            f"{title}：对齐轴长 {axis}，覆盖 "
            f"{left['name']} {pct(float(coverage['bilibili']['coverage_ratio']))}"
            f" / {right['name']} {pct(float(coverage['weibo']['coverage_ratio']))}。"
        )
        findings = [
            f"自有时间桶 {left['name']} {coverage['bilibili']['n_buckets_own']}"
            f" / {right['name']} {coverage['weibo']['n_buckets_own']}",
            f"缺桶 {left['name']} {coverage['bilibili']['missing_buckets']}"
            f" / {right['name']} {coverage['weibo']['missing_buckets']}",
        ]
        return abstract, findings

    if category == "立场共振":
        abstract = f"{title}：立场分歧 {stance_gap:.4f}，情绪分歧 {sent_gap:.4f}。"
        findings = [stance_split(left), stance_split(right)]
        return abstract, findings

    abstract = f"{title}：情绪分歧 {sent_gap:.4f}，立场分歧 {stance_gap:.4f}。"
    findings = [
        sentiment_split(left),
        sentiment_split(right),
        f"情绪均值 {left['name']} {left['sentiment']:+.3f} / {right['name']} {right['sentiment']:+.3f}",
    ]
    return abstract, findings


def main() -> None:
    topics = {
        item["topic"].split(":", 1)[1]: item
        for item in json.loads(EVAL.read_text(encoding="utf-8"))["cross_platform"]["topics"]
        if str(item["topic"]).startswith("broad:")
    }
    records = []
    index = 1
    for category in CATEGORIES:
        for code, title, en in DOMAINS:
            sides = [load_platform(name, code) for name in ("bilibili", "weibo")]
            abstract, findings = build(category, title, sides, topics[title])
            confidence = (sides[0]["confidence"] + sides[1]["confidence"]) / 2
            records.append(
                {
                    "id": f"X-{index:03d}",
                    "title": title,
                    "en": en,
                    "department": " / ".join(side["name"] for side in sides),
                    "category": category,
                    "date": f"{min(s['start'] for s in sides)} 至 {max(s['end'] for s in sides)}",
                    "lead": max(sides, key=lambda side: side["n_text"])["stance"],
                    "clearance": "RESTRICTED" if confidence < 0.45 else "REFERENCE AREA",
                    "abstract": abstract,
                    "findings": findings,
                    "source": SOURCE,
                }
            )
            index += 1

    payload = {"categories": CATEGORIES, "columns": COLUMNS, "records": records}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(records)} records -> {OUT}")


if __name__ == "__main__":
    main()
