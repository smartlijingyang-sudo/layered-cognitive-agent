"""Brain factory registry — 运行时动态切换 Brain 策略。

L2 层职责：
    将策略名称映射到 BrainFactory，由 assembly 在构造时从注册表
    解析具体策略，实现策略与运行时的解耦。
"""

from __future__ import annotations

from lca.contracts.protocols.cognition import BrainFactory
from lca.layer0_infra.component_registry import NamedRegistry

_global_brain_registry: NamedRegistry[BrainFactory] | None = None


def get_global_brain_factory_registry() -> NamedRegistry[BrainFactory]:
    global _global_brain_registry
    if _global_brain_registry is None:
        _global_brain_registry = NamedRegistry[BrainFactory]()
    return _global_brain_registry
