"""采集 + LLM 标注平台黑话/常用词，生成并合并五类词表。

读取 discovery JSON（含 word / platforms / category_hint / meaning），
对每个平台（跳过已存在于 platform_lexicons 的词），调用 DeepSeek 为每个词
标注五类之一或多项，产出可审查标注文件。

五类：support_cues / oppose_cues / pos_sent / neg_sent / markers
分类标准与 generate_platform_lexicon.py 一致；本工具额外利用 discovery 里的
meaning（含义 + 来源）做提示，明显提升标注质量。

重要：LLM 首标可能高估梗/概念词的极性（把 markers 标成 support/pos）。
因此本工具只产出「待审标注」，由人工（或复核层）校正后，再用：
  python -m tools.generate_platform_lexicon --from-file <已复核json> \\
      --merge --merge-mode verified
写回词表。勿直接用 LLM 首标自动合并。

用法：
  python -m tools.discover_lexicon \\
      --discovery tools/slang_discovery_2026q3.json \\
      --out tools/slang_annotated_2026q3.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

AGENT_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AGENT_DIR.parent
for _path in (str(AGENT_DIR), str(REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# pylint: disable=wrong-import-position,import-error
from Conclusion.llm import chat, extract_json  # noqa: E402
from StanceProfiler.labelers.platform_lexicons import PLATFORM_LEXICONS  # noqa: E402
from tools.generate_platform_lexicon import _sanitize  # noqa: E402

FIVE_KEYS = ("support_cues", "oppose_cues", "pos_sent", "neg_sent", "markers")

SYSTEM_PROMPT = (
    "你是中文网络流行语/黑话标注专家。你会收到一个平台、若干候选词（每行格式：词|含义）。\n"
    "请为每个词选择类别，可多选，只允许以下五类：\n"
    "support_cues 明确支持/站队/夸赞（不含纯情绪词）；oppose_cues 明确反对/批判/避雷（不含纯情绪词）；\n"
    "pos_sent 正面情绪（可与 support 重叠）；neg_sent 负面情绪（可与 oppose 重叠）；\n"
    "markers 无明确极性/情绪复杂的圈层词或梗（戏谑、自嘲、事件梗、句式梗、黑话缩写、空耳等）。\n"
    "关键规则：分不清或非明确褒贬的玩梗/黑话一律给 markers，宁少勿错；不要新增候选词之外的词。\n"
    "只输出 JSON：{\"词\": [\"support_cues\", ...], ...}"
)


def _platform_words(
    discovery: dict[str, Any],
    platform: str,
) -> list[dict[str, Any]]:
    """收集该平台候选词，剔除已在词表中的，附含义。"""
    cur = PLATFORM_LEXICONS.get(platform) or {}
    existing = {w for v in cur.values() for w in v}
    items: list[dict[str, Any]] = []
    for entry in discovery.get("words") or []:
        platforms = entry.get("platforms") or []
        if platform not in platforms:
            continue
        word = str(entry.get("word") or "")
        if not word or word in existing:
            continue
        hint = str(entry.get("category_hint") or "")
        meaning = str(entry.get("meaning") or "")
        items.append(
            {"word": word, "meaning": meaning, "category_hint": hint}
        )
    return items


def _chunk(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _label_batch(platform: str, batch: list[dict[str, Any]]) -> dict[str, list[str]]:
    lines = [f"{item['word']}|{item['meaning']}" for item in batch]
    user = (
        f"平台：{platform}\n候选词（词|含义）：\n" + "\n".join(lines)
        + "\n\n为以上每个词选择类别，只输出 JSON。"
    )
    text = chat(SYSTEM_PROMPT, user, temperature=0.1)
    data = extract_json(text)

    # 校验：过滤掉输出中的非候选词（防 LLM 幻觉）
    valid_words = {item["word"] for item in batch}
    result: dict[str, list[str]] = {}
    for word, cats in data.items():
        word = str(word).strip()
        if word not in valid_words:
            continue
        allowed = [c for c in cats if c in FIVE_KEYS] if isinstance(cats, list) else []
        if allowed:
            result[word] = allowed
    return result


def annotate_platform(
    platform: str,
    items: list[dict[str, Any]],
    *,
    batch_size: int = 20,
) -> dict[str, list[str]]:
    """分批标注一个平台的所有候选词，汇总为 {word: [cat...]}。"""
    labeled: dict[str, list[str]] = {}
    for batch in _chunk(items, batch_size):
        part = _label_batch(platform, batch)
        labeled.update(part)
        missed = [item["word"] for item in batch if item["word"] not in part]
        if missed:
            print(f"  [warn] LLM 未返回/过滤 {len(missed)} 词: {missed}")
    return labeled


def to_platform_lexicon(
    platform: str,
    labeled: dict[str, list[str]],
) -> dict[str, list[str]]:
    """把 {word: [cat...]} 转成五类词表结构。"""
    lexicon: dict[str, list[str]] = {k: [] for k in FIVE_KEYS}
    for word, cats in labeled.items():
        for cat in cats:
            lexicon[cat].append(word)
    return _sanitize(lexicon)


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="LLM 标注平台黑话（产出待审文件）")
    parser.add_argument("--discovery", default="tools/slang_discovery_2026q3.json")
    parser.add_argument("--out", default="tools/slang_annotated_2026q3.json")
    parser.add_argument("--platform", default=None, help="只处理指定平台")
    parser.add_argument("--batch-size", type=int, default=20)
    args = parser.parse_args(argv)

    discovery_path = Path(args.discovery)
    if not discovery_path.is_absolute():
        discovery_path = AGENT_DIR / discovery_path
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))

    platforms = list(PLATFORM_LEXICONS.keys())
    if args.platform:
        platforms = [args.platform]

    per_platform: dict[str, dict[str, list[str]]] = {}
    for platform in platforms:
        items = _platform_words(discovery, platform)
        if not items:
            print(f"[{platform}] 无新候选词")
            continue
        print(f"[{platform}] {len(items)} 个新词，调用 LLM ...")
        labeled = annotate_platform(platform, items, batch_size=args.batch_size)
        if not labeled:
            print(f"[{platform}] 标注结果为空")
            continue
        lexicon = to_platform_lexicon(platform, labeled)
        per_platform[platform] = lexicon
        n = {k: len(v) for k, v in lexicon.items()}
        print(f"[{platform}] 完成 {sum(len(v) for v in lexicon.values())} 词：{n}")

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = AGENT_DIR / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(per_platform, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n标注文件已保存：{out_path}")
    print(
        "提示：此为 LLM 首标，需人工复核校正后，用 "
        "generate_platform_lexicon --from-file <复核json> --merge --merge-mode verified 写回。"
    )
    return per_platform


if __name__ == "__main__":
    main()
