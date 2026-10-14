"""可选依赖缺失时跳过本目录的测试，而不是让整个 pytest 会话收集中断。

背景：本项目约定用 `pytest -c tests/pytest.ini`（testpaths 限定在 tests/）。
但从仓库根跑裸 `pytest` 会把本目录也收集进来，而这里的测试依赖 scikit-learn
等预测专用包；没装时 pytest 会报收集错误、连后端测试也一起跑不了。

这里按依赖是否存在决定是否收集：装齐了照常跑，没装就安静跳过。
"""
from __future__ import annotations

import importlib.util

# 本目录测试所需的可选依赖
_REQUIRED = ("sklearn", "torch", "numpy")

collect_ignore_glob: list[str] = []

_missing = [name for name in _REQUIRED if importlib.util.find_spec(name) is None]
if _missing:
    # 缺依赖时不收集本目录的测试文件
    collect_ignore_glob.append("test_*.py")
