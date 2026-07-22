"""识别器注册入口（保证具体识别器被 `register()` 添加）。

顺序：import 此模块 → 内部 import 各具体识别器 → 都自动注册到 `REGISTRY`。
"""
from .base import REGISTRY, Recognizer, find_control_root, register  # noqa: F401

# 让具体识别器完成 self-register
from . import table  # noqa: F401
from . import div_grid  # noqa: F401
from . import field_group  # noqa: F401
from . import list_block  # noqa: F401

__all__ = ["REGISTRY", "Recognizer", "find_control_root", "register"]
