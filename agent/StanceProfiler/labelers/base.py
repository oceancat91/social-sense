"""标注器基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseLabeler(ABC):
    name: str = "base"
    version: str = "v0"

    @abstractmethod
    def label(self, text: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        返回:
          stance_label, sentiment_score, stance_conf, topic_tags
        """
        raise NotImplementedError
