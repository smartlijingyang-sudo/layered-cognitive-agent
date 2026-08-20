"""组合期注册表包 —— 用显式值对象替代进程级全局单例。

Registries 是一次组合过程（一次 ``spawn_team``）共享的全部可插拔组件注册表。
字段类型全部是 contracts 已有的 Protocol，不引用任何具体实现类，
因此可以被 L0-L4 任意层安全导入而不违反 import-linter 的单向依赖契约。

刻意不提供默认值：拿到"一份可用的具体注册表实例"是组合根
（layer4_app）的职责，不是 contracts 的职责——contracts 只声明形状。
"""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.mechanisms import (
    ComponentRegistryProtocol,
    NamedRegistryProtocol,
    OrchestrationRegistryProtocol,
)


@dataclass(frozen=True)
class Registries:
    """一次组合过程共享的三个发现型注册表。"""

    components: ComponentRegistryProtocol
    brain_factories: NamedRegistryProtocol
    orchestration: OrchestrationRegistryProtocol
