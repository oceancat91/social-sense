"""档案阵列数据源：把跨平台观测报告折算成前端所需的 5 分类 × 8 领域档案。

前端（SENSE LAB 档案终端）不再把数据烘焙进构建产物，而是运行期向本服务取数：
    GET /api/v1/archives

数据来源是 cross-platform 报告目录（``agent/dataset/real_multiplatform/reports``）：
每个领域读 bilibili / weibo 两侧的 ``{code}__broad.json``，再结合
``evaluation_report.json`` 里的 cross_platform topics 生成档案正文。

生产镜像只打包 ``backend/``，拿不到 38 MB 的原始报告，因此这里采用两级策略：
优先按报告实时计算；报告目录不可用时回落到随镜像发布的快照 JSON。
两条路径产出的 payload 结构完全一致，前端无需区分。
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

# 报告缺失时使用的快照（随 backend/ 一起发布，约 25 KB）
DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[2] / 'data' / 'archives.snapshot.json'

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

# 前端 data.ts 的档案契约，服务端提前校验，避免下发渲染不了的数据。
EXPECTED_RECORDS = 40
EXPECTED_PER_CATEGORY = 8

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_source: str | None = None


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _reports_dir() -> Path:
    from flask import current_app

    configured = current_app.config.get('ARCHIVE_DATA_DIR')
    return Path(configured) if configured else Path('.')


def _eval_path() -> Path:
    from flask import current_app

    configured = current_app.config.get('ARCHIVE_EVAL_PATH')
    return Path(configured) if configured else Path('.')


def _snapshot_path() -> Path:
    from flask import current_app

    configured = current_app.config.get('ARCHIVE_SNAPSHOT_PATH')
    return Path(configured) if configured else DEFAULT_SNAPSHOT


# --------------------------------------------------------------------------- #
# 报告 -> 档案
# --------------------------------------------------------------------------- #
def _load_platform(reports: Path, platform: str, code: str) -> dict[str, Any]:
    data = json.loads((reports / platform / f"{code}__broad.json").read_text(encoding="utf-8"))
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


def _stance_split(side: dict[str, Any]) -> str:
    d = side["dist"]
    return (
        f"{side['name']} 支持 {_pct(float(d.get('support', 0)))}"
        f" / 反对 {_pct(float(d.get('oppose', 0)))}"
        f" / 中立 {_pct(float(d.get('neutral', 0)))}"
    )


def _sentiment_split(side: dict[str, Any]) -> str:
    d = side["sent_dist"]
    return (
        f"{side['name']} 正 {_pct(float(d.get('pos', 0)))}"
        f" / 中 {_pct(float(d.get('neu', 0)))}"
        f" / 负 {_pct(float(d.get('neg', 0)))}"
    )


def _build_body(
    category: str, title: str, sides: list[dict[str, Any]], topic: dict[str, Any]
) -> tuple[str, list[str]]:
    """按分类生成 abstract 与 findings（文字原则与离线脚本保持一致）。"""
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
            f"空窗 {left['name']} {_pct(left['empty_ratio'])} / {right['name']} {_pct(right['empty_ratio'])}",
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
            f"{left['name']} {_pct(float(coverage['bilibili']['coverage_ratio']))}"
            f" / {right['name']} {_pct(float(coverage['weibo']['coverage_ratio']))}。"
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
        return abstract, [_stance_split(left), _stance_split(right)]

    abstract = f"{title}：情绪分歧 {sent_gap:.4f}，立场分歧 {stance_gap:.4f}。"
    findings = [
        _sentiment_split(left),
        _sentiment_split(right),
        f"情绪均值 {left['name']} {left['sentiment']:+.3f} / {right['name']} {right['sentiment']:+.3f}",
    ]
    return abstract, findings


def build_payload() -> dict[str, Any]:
    """从报告目录实时计算档案阵列。报告缺失时抛 FileNotFoundError。"""
    reports = _reports_dir()
    eval_file = _eval_path()

    topics = {
        item["topic"].split(":", 1)[1]: item
        for item in json.loads(eval_file.read_text(encoding="utf-8"))["cross_platform"]["topics"]
        if str(item["topic"]).startswith("broad:")
    }

    records: list[dict[str, Any]] = []
    index = 1
    for category in CATEGORIES:
        for code, title, en in DOMAINS:
            sides = [_load_platform(reports, name, code) for name in ("bilibili", "weibo")]
            abstract, findings = _build_body(category, title, sides, topics[title])
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

    return {"categories": CATEGORIES, "columns": COLUMNS, "records": records}


# --------------------------------------------------------------------------- #
# 校验 / 缓存 / 回落
# --------------------------------------------------------------------------- #
def validate(payload: Any) -> dict[str, Any]:
    """校验前端契约；不满足就抛 ValueError，绝不向客户端下发残缺数据。"""
    if not isinstance(payload, dict):
        raise ValueError('档案数据必须是 JSON 对象')

    categories, columns = payload.get("categories"), payload.get("columns")
    for key, value in (("categories", categories), ("columns", columns)):
        if not isinstance(value, list) or len(value) != 5 or not all(
            isinstance(v, str) and v.strip() for v in value
        ):
            raise ValueError(f'{key}：必须包含五个非空分类名称')

    records = payload.get("records")
    if not isinstance(records, list) or len(records) != EXPECTED_RECORDS:
        raise ValueError(f'records：当前阵列要求 {EXPECTED_RECORDS} 份档案')

    for name in columns:
        if sum(1 for r in records if isinstance(r, dict) and r.get("category") == name) != EXPECTED_PER_CATEGORY:
            raise ValueError(f'分类「{name}」：当前阵列要求 {EXPECTED_PER_CATEGORY} 份档案')

    for index, record in enumerate(records):
        expected_id = f'X-{index + 1:03d}'
        if record.get("id") != expected_id:
            raise ValueError(f'records[{index}].id：应为 {expected_id}，编号须按顺序保持稳定')
        for field in ("title", "en", "department", "category", "date", "lead", "clearance", "abstract", "source"):
            value = record.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'records[{index}].{field}：必须是非空文本')
        findings = record.get("findings")
        if not isinstance(findings, list) or not findings or not all(
            isinstance(f, str) and f.strip() for f in findings
        ):
            raise ValueError(f'records[{index}].findings：必须包含至少一条非空研究记录')
        if record["category"] not in categories:
            raise ValueError(f'records[{index}].category：未知分类 {record["category"]}')

    return payload


def _load_snapshot() -> dict[str, Any] | None:
    path = _snapshot_path()
    if not path.exists():
        return None
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return None


def get_payload(*, force: bool = False) -> tuple[dict[str, Any], str]:
    """返回 (payload, source)。source 为 'live' 或 'snapshot'，便于排障。"""
    global _cache, _cache_source

    with _lock:
        if _cache is not None and not force:
            return _cache, _cache_source or 'live'

        payload: dict[str, Any] | None = None
        source = 'live'
        try:
            payload = validate(build_payload())
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            # 报告目录不可用（生产镜像）——回落到随镜像发布的快照。
            payload = _load_snapshot()
            source = 'snapshot'
            if payload is None:
                raise RuntimeError(
                    '档案数据不可用：报告目录缺失且未找到快照 '
                    f'({_snapshot_path()})'
                )

        _cache, _cache_source = payload, source
        return payload, source


def invalidate() -> None:
    """清空进程内缓存（报告更新后调用）。"""
    global _cache, _cache_source
    with _lock:
        _cache, _cache_source = None, None


def write_snapshot() -> Path:
    """把实时计算结果写成快照，供生产镜像使用。"""
    payload = validate(build_payload())
    path = _snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def find_record(file_id: str) -> dict[str, Any] | None:
    payload, _ = get_payload()
    for record in payload["records"]:
        if record["id"] == file_id:
            return record
    return None


def archive_text(record: dict[str, Any]) -> str:
    """导出为可下载的档案文本（与前端 EXPORT 按钮对应）。"""
    lines = "\n".join(
        f"{i}. {finding}" for i, finding in enumerate(record["findings"], 1)
    )
    return (
        "\ufeffSENSE LAB · SOCIAL SENSE ARCHIVE\n"
        f"FILE {record['id']} / {record['title']}\n"
        f"{record['en']}\n\n"
        f"平台：{record['department']}\n"
        f"编目范围：{record['date']}\n"
        f"主导立场：{record['lead']}\n"
        f"访问范围：{record['clearance']}\n\n"
        f"{record['abstract']}\n\n"
        f"研究记录\n{lines}\n\n"
        f"数据来源：{record['source']}\n"
        "本文由 Social Sense 跨平台观测数据生成，数值来自已归档报告。\n"
    )
