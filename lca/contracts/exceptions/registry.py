"""Registry key lookup error, shared across layers (contract-level).

``RegistryKeyError`` is raised when a named-registry lookup fails. It lives in
contracts so ``harness`` and ``cognition`` consumers can catch it without
depending on the infrastructure registry implementation (AGENTS.md §2.1:
harness depends only on contracts).
"""

from __future__ import annotations

__all__ = ["RegistryKeyError"]


class RegistryKeyError(ValueError):
    """按名称查找注册表条目失败。

    继承 ValueError 以保持向后兼容（已有测试 assertRaises(ValueError)）。
    """

    def __init__(self, key: str, registry_kind: str, available: list[str]) -> None:
        self.key = key
        self.registry_kind = registry_kind
        self.available = available
        super().__init__(f"未注册{registry_kind} {key!r}，可用: {available}")
