"""统一 Skill 抽象：把单平台 Agent 的六项能力封装为可复用、可独立验证的单元。

每个 Skill 以 ``SkillContext`` 为输入/输出，围绕 ``D_platform`` 做链式转换：
  - Skill1 PlatformCrawler     采集 + 清洗 → D_platform
  - Skill2 StanceProfiler      立场/情绪画像 → 刷新 D_platform + stance_profile
  - Skill3 MultimodalAnalyzer  多尺度时间-文本异常 → skill3
  - Skill4 KnowledgeAugmentor  写入 + 检索案例（BM25 / DTW 相似）
  - Skill5+6 Conclusion        结论生成 + 严格校准 → conclusion(OT1)

设计约定：
  - 每个 Skill 声明 ``name`` 与 ``version``，便于日志与契约追踪；
  - ``run`` 可原地修改传入的 ctx，随后返回更新后的完整状态（不依赖全局可变目录）；
  - 失败时抛出异常并写入 ``ctx.log``，交由上层统一兜底。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class SkillContext:
    """贯穿六项 Skill 的共享状态载体。"""

    platform: str = "bilibili"
    keyword: str = ""
    time_range: tuple[str, str] | None = None
    granularity: str = "day"
    args: Any = None
    # 原始字段列表（Skill1 输入，来自爬虫/外部 CSV/ZIP）
    raw_records: list[dict[str, Any]] | None = None
    # 各 Skill 输出
    d_platform: dict[str, Any] | None = None
    stance_profile: dict[str, Any] | None = None
    skill3: dict[str, Any] | None = None
    rag: dict[str, Any] | None = None
    conclusion: dict[str, Any] | None = None
    # 运行期记账
    log: list[dict[str, Any]] = field(default_factory=list)

    def record(self, skill: str, status: str, **extra: Any) -> None:
        self.log.append(
            {
                "skill": skill,
                "status": status,
                "ts": datetime.now().isoformat(timespec="seconds"),
                **extra,
            }
        )


class Skill(ABC):
    """Skill 基类：声明 name/version，并实现 ``run(ctx) -> ctx``。"""

    name: str = "base"
    version: str = "v0"

    @abstractmethod
    def run(self, ctx: SkillContext) -> SkillContext:
        raise NotImplementedError
