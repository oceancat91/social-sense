"""Skill 封装层：统一抽象 + 注册表 + 六项具体实现。"""

from .base import Skill, SkillContext
from .registry import SkillRegistry, register, registry
from .impls import (
    ConclusionSkill,
    KnowledgeAugmentorSkill,
    MultimodalAnalyzerSkill,
    PlatformCrawlerSkill,
    StanceProfilerSkill,
    run_pipeline,
)

__all__ = [
    "Skill",
    "SkillContext",
    "SkillRegistry",
    "register",
    "registry",
    "PlatformCrawlerSkill",
    "StanceProfilerSkill",
    "MultimodalAnalyzerSkill",
    "KnowledgeAugmentorSkill",
    "ConclusionSkill",
    "run_pipeline",
]
