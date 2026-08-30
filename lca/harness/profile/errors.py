"""Profile 解析路径共享的错误契约。"""

from __future__ import annotations


class ProfileResolveError(ValueError):
    """Profile 输入、结构或依赖在插件 setup 前无法被安全解析。"""


__all__ = ["ProfileResolveError"]
