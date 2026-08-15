"""
Skill4 命令行入口：

  写入：python -m KnowledgeAugmentor write --in path/to/D_platform.json [--min-weight 0.5]
  检索：python -m KnowledgeAugmentor retrieve --query "话题词" [--top-k 8] [--keyword 话题]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .store import KnowledgeStore


def _cmd_write(args: argparse.Namespace) -> None:
    inp = Path(args.inp)
    if not inp.exists():
        raise SystemExit(f"找不到输入文件：{inp}")
    with inp.open("r", encoding="utf-8") as f:
        d_platform = json.load(f)
    store = KnowledgeStore()
    stats = store.write_d_platform(d_platform, min_evidence_weight=args.min_weight)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def _cmd_retrieve(args: argparse.Namespace) -> None:
    store = KnowledgeStore()
    tr = (args.since, args.until) if (args.since or args.until) else None
    result = store.retrieve(
        args.query,
        top_k=args.top_k,
        time_range=tr,
        stance_label=args.stance,
        platform=args.platform,
        keyword=args.keyword,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="KnowledgeAugmentor：知识写入 + 按需检索")
    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="写入 D_platform 高权重样本")
    w.add_argument("--in", dest="inp", required=True, help="D_platform.json")
    w.add_argument("--min-weight", type=float, default=0.5, help="evidence_weight 下限")
    w.set_defaults(func=_cmd_write)

    r = sub.add_parser("retrieve", help="BM25 检索")
    r.add_argument("--query", required=True, help="检索查询")
    r.add_argument("--top-k", type=int, default=8)
    r.add_argument("--since", default=None)
    r.add_argument("--until", default=None)
    r.add_argument("--stance", default=None, help="按立场过滤")
    r.add_argument("--platform", default=None)
    r.add_argument("--keyword", default=None, help="用于历史同类事件对照")
    r.set_defaults(func=_cmd_retrieve)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
