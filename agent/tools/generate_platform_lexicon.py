"""调用 LLM 为平台黑话 / 常用词生成标签。

把候选词交给 DeepSeek，输出五类标签：
  - support_cues  明确「支持 / 夸赞」站队表态（不含纯情绪词）
  - oppose_cues   明确「反对 / 批判」站队表态（不含纯情绪词）
  - pos_sent      正面情绪（可与立场解耦，允许与 support 重叠）
  - neg_sent      负面情绪（可与立场解耦，允许与 oppose 重叠）
  - markers       无明确极性的圈层标记词 / 梗

产出后可 `--merge` 回写 StanceProfiler/labelers/platform_lexicons.py，
直接提升 LexiconLabeler 的情绪标注准确率（当前情绪准确率偏低，
根因正是黑话进了立场词表、却缺情绪词表）。

用法：
  python -m tools.generate_platform_lexicon [--platform bilibili] \
      [--extra-file extra_words.json] [--out out.json] [--merge] [--dry-run]
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

PLATFORMS = ("bilibili", "weibo", "douyin", "xiaohongshu", "zhihu", "kuaishou")
FIVE_KEYS = ("support_cues", "oppose_cues", "pos_sent", "neg_sent", "markers")

SYSTEM_PROMPT = (
    "你是中文社媒平台圈层用语标注专家。给一批平台黑话/常用词打标签，输出 JSON，"
    "只含五个键：support_cues、oppose_cues、pos_sent、neg_sent、markers，"
    "每个键是一个字符串数组。\n"
    "分类标准：\n"
    "1. support_cues：明确「支持/站队/夸赞」表态，如 支持、三连、挺、力挺、封神；纯情绪词不放这里。\n"
    "2. oppose_cues：明确「反对/批判/避雷」表态，如 反对、避雷、翻车、取关、抵制；纯情绪词不放这里。\n"
    "3. pos_sent：正面情绪，如 泪目、感动、上头、治愈、yyds；可与 support 重叠（一词可多类）。\n"
    "4. neg_sent：负面情绪，如 破防、裂开、无语、失望、翻车；可与 oppose 重叠（一词可多类）。\n"
    "5. markers：无明确极性或情绪复杂的圈层标记词/梗，如 家人们、吃瓜、谢邀、前方高能。\n"
    "规则：一个词可以同时属于多个类别（例如「封神」既是 support 又是 pos，「翻车」既是 oppose 又是 neg）；"
    "无法归入前四类的口语/圈层词放进 markers；不要新增候选词之外的词；不要输出任何解释或注释。"
)


def _collect_words(platform: str) -> list[str]:
    """提取该平台现有词表中的全部词作为候选集（去重保序）。"""
    lexicon = PLATFORM_LEXICONS.get(platform) or {}
    seen: list[str] = []
    for key in FIVE_KEYS:
        for word in lexicon.get(key) or []:
            if word and word not in seen:
                seen.append(word)
    return seen


def _load_extra(path: str | Path) -> list[str]:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [str(w) for w in raw if str(w).strip()]
    if isinstance(raw, dict):
        return [str(w) for w in raw.get("words") or [] if str(w).strip()]
    raise ValueError("--extra-file 需为 list 或 {'words': [...]}")


def generate(platform: str, words: list[str], *, temperature: float = 0.2) -> dict[str, list[str]]:
    """调用 LLM 为一批词生成五类标签。"""
    user = (
        f"平台：{platform}\n"
        f"候选词（每行一个）：\n" + "\n".join(words) + "\n\n"
        f"请为以上 {len(words)} 个词逐个分类，输出 JSON。"
    )
    text = chat(SYSTEM_PROMPT, user, temperature=temperature)
    data = extract_json(text)
    result: dict[str, list[str]] = {}
    for key in FIVE_KEYS:
        values = data.get(key) or []
        result[key] = [str(v).strip() for v in values if str(v).strip()]
    return result


def _sanitize(lexicon: dict[str, list[str]]) -> dict[str, list[str]]:
    """保证五键齐全、词非空。"""
    out: dict[str, list[str]] = {}
    for key in FIVE_KEYS:
        out[key] = [w for w in (lexicon.get(key) or []) if w and str(w).strip()]
    return out


def _render_block(platform: str, lexicon: dict[str, list[str]], words_per_line: int = 6) -> str:
    lines = [f'    "{platform}": {{']
    for key in FIVE_KEYS:
        if key == "support_cues":
            lines.append("        # 立场（站队）：只保留明确「支持/夸赞」表态，不含纯情绪词")
        elif key == "oppose_cues":
            lines.append("        # 立场（站队）：只保留明确「反对/批判」表态，不含纯情绪词")
        elif key == "pos_sent":
            lines.append("        # 情绪（褒贬）：纯情绪词 + 带强烈正面情绪的夸赞词")
        elif key == "neg_sent":
            lines.append("        # 情绪（褒贬）：纯情绪词 + 带强烈负面情绪的批判词")
        elif key == "markers":
            lines.append("        # 圈层标记词/梗（无明确极性或情绪复杂）")
        values = lexicon.get(key) or []
        lines.append(f'        "{key}": [')
        for i in range(0, max(1, len(values)), words_per_line):
            chunk = values[i : i + words_per_line]
            quoted = ", ".join(f'"{w}"' for w in chunk)
            comma = "," if i + words_per_line < len(values) else ""
            lines.append(f"            {quoted}{comma}")
        lines.append("        ],")
    lines[-1] = lines[-1].rstrip(",")
    lines.append("    },")
    return "\n".join(lines)


def anchored_merge(cur: dict[str, list[str]], llm: dict[str, list[str]]) -> dict[str, list[str]]:
    """锚定合并：以人工词表为基底，只采纳 LLM 的情绪极性补充。

    规则（保护人工立场与 markers 的权威性，规避 LLM 对圈层梗的误判）：
      - 人工 support_cues 中的词，若 LLM 也判为 pos_sent，则补进 pos_sent；
      - 人工 oppose_cues 中的词，若 LLM 也判为 neg_sent，则补进 neg_sent；
      - 其余 LLM 判断（markers 重排、立场词丢失、纯新增词）一律忽略。
    """
    merged = {k: [w for w in (cur.get(k) or []) if w] for k in FIVE_KEYS}
    cur_support = set(merged["support_cues"])
    cur_oppose = set(merged["oppose_cues"])
    llm_pos = set(llm.get("pos_sent") or [])
    llm_neg = set(llm.get("neg_sent") or [])
    for word in cur_support:
        if word in llm_pos and word not in merged["pos_sent"]:
            merged["pos_sent"].append(word)
    for word in cur_oppose:
        if word in llm_neg and word not in merged["neg_sent"]:
            merged["neg_sent"].append(word)
    return merged


def verified_merge(cur: dict[str, list[str]], verified: dict[str, list[str]]) -> dict[str, list[str]]:
    """人工复核合并：以现有人工词表为基底，仅追加复核通过的词。

    verified 形如 {"support_cues": [...], "pos_sent": [...], "markers": [...]}，
    每个键的值是「已通过人工复核、应新增的词」。对已在人工词表中的词自动跳过
    （不去重整理、不删词、不改现有分类），保证合并可逆、可追溯。
    """
    merged = {k: [w for w in (cur.get(k) or []) if w] for k in FIVE_KEYS}
    for key in FIVE_KEYS:
        for word in verified.get(key) or []:
            if word and word not in merged[key]:
                merged[key].append(word)
    return merged


def merge_into_file(
    platform: str,
    lexicon: dict[str, list[str]],
    *,
    path: Path | None = None,
    dry_run: bool = False,
) -> str:
    """把 LLM 生成的词表回写 platform_lexicons.py（替换该平台块）。"""
    target = path or (AGENT_DIR / "StanceProfiler" / "labelers" / "platform_lexicons.py")
    text = target.read_text(encoding="utf-8")
    block = _render_block(platform, lexicon)

    marker = f'    "{platform}": {{'
    if marker not in text:
        raise ValueError(f"platform_lexicons.py 中找不到平台块：{platform}")

    start = text.index(marker)
    # 该块结束于「对应闭合的 "    },\n」：从 start 找下一个以 '    },' 开头且缩进匹配的行
    end = text.index("    },", start) + len("    },")
    new_text = text[:start] + block + text[end:]

    if dry_run:
        return new_text
    target.write_text(new_text, encoding="utf-8")
    return new_text


def main(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="LLM 为平台黑话/常用词生成标签")
    parser.add_argument("--platform", choices=list(PLATFORMS) + ["all"], default="all")
    parser.add_argument("--extra-file", default=None, help="额外候选词 JSON")
    parser.add_argument(
        "--from-file",
        default=None,
        help="从已有 LLM 结果 JSON 合并（跳过 LLM 调用，需配合 --merge）",
    )
    parser.add_argument("--out", default=None, help="输出合并结果 JSON")
    parser.add_argument("--merge", action="store_true", help="回写 platform_lexicons.py")
    parser.add_argument(
        "--merge-mode",
        choices=["anchored", "verified", "replace"],
        default="anchored",
        help="anchored=只补情绪极性；verified=追加人工复核词(推荐)；replace=全量用 LLM 结果替换",
    )
    parser.add_argument("--dry-run", action="store_true", help="只生成不写文件")
    parser.add_argument("--temperature", type=float, default=0.2)
    args = parser.parse_args(argv)

    platforms = list(PLATFORMS) if args.platform == "all" else [args.platform]
    results: dict[str, dict[str, list[str]]] = {}

    # 从已有结果文件合并：跳过 LLM 调用
    if args.from_file:
        cached = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        for platform in platforms:
            lexicon = cached.get(platform)
            if lexicon is None:
                print(f"[{platform}] 结果文件中无此平台，跳过")
                continue
            results[platform] = _sanitize(lexicon)
            if args.merge:
                current = PLATFORM_LEXICONS.get(platform) or {}
                if args.merge_mode == "anchored":
                    final = anchored_merge(current, lexicon)
                elif args.merge_mode == "verified":
                    final = verified_merge(current, lexicon)
                else:
                    final = lexicon
                merge_into_file(platform, _sanitize(final), dry_run=args.dry_run)
                print(f"[{platform}] 已按 {args.merge_mode} 模式回写 platform_lexicons.py")
        if args.out:
            out = Path(args.out).resolve()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        return results

    for platform in platforms:
        words = _collect_words(platform)
        if args.extra_file:
            words.extend(w for w in _load_extra(args.extra_file) if w not in words)
        if not words:
            print(f"[{platform}] 无候选词，跳过")
            continue
        print(f"[{platform}] 候选词 {len(words)} 个，调用 LLM ...")
        try:
            lexicon = _sanitize(generate(platform, words, temperature=args.temperature))
        except Exception as exc:  # noqa: BLE001
            print(f"[{platform}] LLM 调用失败：{exc}")
            continue
        results[platform] = lexicon
        n = {k: len(v) for k, v in lexicon.items()}
        print(f"[{platform}] 完成：{n}")

        if args.merge:
            final = lexicon
            if args.merge_mode == "anchored":
                final = anchored_merge(PLATFORM_LEXICONS.get(platform) or {}, lexicon)
            merge_into_file(platform, _sanitize(final), dry_run=args.dry_run)
            print(
                f"[{platform}] 已{'（dry-run）' if args.dry_run else ''}"
                f"按 {args.merge_mode} 模式回写 platform_lexicons.py"
            )

    if args.out and results:
        out = Path(args.out).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"结果已保存：{out}")

    return results


if __name__ == "__main__":
    main()
