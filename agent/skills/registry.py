"""Skill 注册表：按 ``name`` 登记实现，供编排层与跨平台 Agent 统一取用。"""

from __future__ import annotations

from typing import Any

from .base import Skill, SkillContext


class SkillRegistry:
    """按名字登记 Skill 类，支持按序取用与执行。"""

    def __init__(self) -> None:
        self._skills: dict[str, type[Skill]] = {}

    def register(self, cls: type[Skill]) -> type[Skill]:
        name = getattr(cls, "name", None)
        if not name:
            raise ValueError(f"Skill {cls.__name__} 缺少 name 属性")
        self._skills[name] = cls
        return cls

    def get(self, name: str) -> type[Skill]:
        if name not in self._skills:
            raise KeyError(f"未注册的 Skill: {name}，可选: {sorted(self._skills)}")
        return self._skills[name]

    def names(self) -> list[str]:
        return sorted(self._skills)

    def run(self, name: str, ctx: SkillContext, **kwargs: Any) -> SkillContext:
        skill = self.get(name)(**kwargs)
        return skill.run(ctx)

    def __contains__(self, name: str) -> bool:
        return name in self._skills


# 默认单例：装饰器 ``@register`` 与 ``registry.get/run`` 都走这一实例
registry = SkillRegistry()
register = registry.register
