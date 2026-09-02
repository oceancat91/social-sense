"""跨平台主控 Agent：把多个单平台 PlatformReport 对齐到同一时间轴并融合。

在 multiagent.align / fuse / master 之上封装为一个可直接调用的 Agent 对象，
额外暴露「平台时间覆盖度」观测，便于用真实历史数据验证对齐质量。

用法：
  agent = CrossPlatformAgent(reports)
  ct = agent.run(use_llm=False)   # 对齐 + 融合 + 归纳 + 校准
  coverage = agent.coverage()     # 各平台桶覆盖度
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .align import align
from .contract import normalize_report
from .fuse import fuse as _fuse
from .master import run_master


def load_reports_dir(reports_dir: str | Path) -> list[dict[str, Any]]:
    """递归读取目录下全部 JSON 报告（按路径排序保证确定性）。"""
    root = Path(reports_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"报告目录不存在：{root}")
    reports: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        reports.append(json.loads(path.read_text(encoding="utf-8")))
    return reports


class CrossPlatformAgent:
    """跨平台主控 Agent：对齐 → 融合 → 归纳，并附带平台覆盖度观测。"""

    def __init__(self, reports: list[dict[str, Any]] | None = None) -> None:
        self.raw_reports: list[dict[str, Any]] = list(reports or [])
        self.reports: list[dict[str, Any]] = [normalize_report(r) for r in self.raw_reports]
        self.aligned: dict[str, Any] = align(self.reports)
        self.fused: dict[str, Any] | None = None
        self.ct: dict[str, Any] | None = None

    @classmethod
    def from_dir(cls, reports_dir: str | Path) -> "CrossPlatformAgent":
        return cls(load_reports_dir(reports_dir))

    @property
    def platforms(self) -> list[str]:
        return list(self.aligned.get("platforms") or [])

    @property
    def time_axis(self) -> list[str]:
        return list(self.aligned.get("time_axis") or [])

    def coverage(self) -> dict[str, dict[str, Any]]:
        """各平台在公共时间轴上的桶覆盖度（缺失为空窗，不插值）。"""
        n_aligned = len(self.time_axis)
        out: dict[str, dict[str, Any]] = {}
        aligned_ts = self.aligned.get("aligned_ts") or {}
        for platform in self.platforms:
            buckets = aligned_ts.get(platform) or []
            n_own = sum(1 for b in buckets if b is not None)
            out[platform] = {
                "n_buckets_own": n_own,
                "aligned_buckets": n_aligned,
                "missing_buckets": n_aligned - n_own,
                "coverage_ratio": round(n_own / n_aligned, 4) if n_aligned else 0.0,
            }
        return out

    def compute_fusion(self) -> dict[str, Any]:
        """在对齐结果上计算跨平台分歧与茧房指数。"""
        self.fused = _fuse(self.aligned, self.reports)
        return self.fused

    def run(self, *, use_llm: bool = False) -> dict[str, Any]:
        """执行完整跨平台流程，返回终裁 CT。"""
        self.ct = run_master(self.raw_reports, use_llm=use_llm)
        self.ct["coverage"] = self.coverage()
        return self.ct

    def report(self, *, use_llm: bool = False) -> dict[str, Any]:
        """运行并返回带覆盖度的 CT（等价于 run，命名更直观）。"""
        return self.run(use_llm=use_llm)
