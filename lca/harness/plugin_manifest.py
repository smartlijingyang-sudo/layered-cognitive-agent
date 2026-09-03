"""插件 Manifest 的不可变领域模型。

此模块只承载解析和编译共同消费的声明事实；装饰器输入适配位于
``plugin_declaration``，运行期受审计交互位于 ``plugin_context``。通过这条接缝，
Profile Resolve 无需依赖 Cordis 载体或运行时 Context，即可读取稳定的 Manifest。

``PluginSpec`` 是插件的身份、能力、层级、效果和验证信息的唯一结构化目录。
``PluginDefinition`` 仅保留该目录与不可序列化的启动载体；它不再存储平行的
``provides``、``requires``、``layer`` 等字段，避免解析、启动审计和计划编译从不同
事实源得出不同结论。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Generic, TypeAlias, TypeVar

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.protocols.declarative.declarative_plugin import PluginSpec

if TYPE_CHECKING:
    from lca.contracts.harness.composition.plugin_contract import PluginContract
    from lca.contracts.protocols.composition.logic_address import LogicAddress
    from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
    from lca.harness.plugin_context import PluginContext


__all__ = [
    "EffectClass",
    "PluginDefinition",
    "PluginKind",
    "PluginMetadata",
    "PluginSetupFn",
    "RawRelationEntry",
]


# ``C`` is the bound for a plugin's concrete pydantic ``Config``. Every
# ``@plugin`` setup declares ``config: MyConfig`` (a subclass of BaseModel),
# so ``PluginSetupFn[C]`` lets the decorator preserve that specificity instead
# of erasing it to ``Callable[..., BaseModel]`` (which mypy would reject via
# the contravariant argument position of ``Callable``).
C = TypeVar("C", bound=BaseModel)

# A plugin's ``setup`` callable MUST match this signature. The constraint
# lives at the decorator entry point on purpose: mypy enforces it for every
# ``@plugin``-decorated function, so untyped ``async def setup(ctx, config)``
# is rejected at decoration time, not at use time. ``PluginSetupFn[C]`` is
# invariant across C (it's both read and passed back), so concrete ``Config``
# subclasses remain valid as long as ``C`` is bound consistently with the
# adjacent ``Config: type[C]`` field on ``PluginDefinition``.
PluginSetupFn = Callable[["PluginContext", C], Awaitable[None]]

# These aliases mark the only intentionally open payloads at the declaration
# seam. Runtime resolution turns them into closed plan entries before a plan
# reaches the interpreter.
PluginMetadata: TypeAlias = Mapping[str, object]
RawRelationEntry: TypeAlias = Mapping[str, object]


class PluginKind(str, Enum):
    SEAM = "seam"
    PROVIDER = "provider"
    PRIMITIVE = "primitive"
    COMPOSITE = "composite"
    DRIVER = "driver"
    BRIDGE = "bridge"


class EffectClass(str, Enum):
    NONE = "none"
    TOOLS = "tools"
    MEMORY = "memory"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    WORLD = "world"


_LAYER_VALUES = frozenset({"L0", "L1", "L2", "L3", "L4"})


@dataclass(frozen=True, slots=True)
class PluginDefinition(Generic[C]):
    """连接原生声明目录与 Cordis 启动载体的深模块。

    ``spec`` 是插件身份、能力、层级、效果和验证信息的唯一事实源；``Config`` 与
    ``setup`` 则是启动期不可序列化载体。调用方必须通过 ``provided_capability_keys``
    和 ``required_capability_keys`` 读取审计能力，不能重新解析装饰器元数据。

    泛型参数 ``C`` 与 ``Config: type[C]`` 与 ``setup: PluginSetupFn[C]`` 共享同一
    个 TypeVar，使得调用方在静态层面知道 ``definition.setup`` 期望的 config
    类型；保留 ``Config: type[C] | None`` 是因为某些插件（譬如 L1 启动器、
    兜底 stub）没有具体 Config schema。
    """

    Config: type[C] | None
    setup: PluginSetupFn[C]
    spec: PluginSpec
    description: str
    relations: tuple[RawRelationEntry, ...] = ()
    functional_group: FunctionalGroup | None = None
    logic_address: LogicAddress | None = None
    contract: PluginContract | None = None
    ownership: OwnershipDeclaration | None = None
    marker_class: type | None = None
    """PR-5：插件作为事件 yaml 鉴权矩阵的 marker 类（详见 plugin_declaration）。

    当插件在 yaml 中以 id 形式被引用时，``EventRegistry`` 按
    ``id → marker_class`` 解析。仅声明了 ``@plugin(marker_class=...)``
    的插件才会进入 EventRegistry 的 catalog；其余插件无 marker。
    """

    @property
    def id(self) -> str:
        """Return the identity held by the native specification."""
        return str(self.spec.id)

    @property
    def module(self) -> str:
        """Return the executable module recorded by the native specification."""
        return str(self.spec.implementation.module)

    @property
    def provided_capability_keys(self) -> tuple[str, ...]:
        """Return the closed provider catalog used by Resolve and boot audit."""
        return tuple(capability.key for capability in self.spec.provides)

    @property
    def required_capability_keys(self) -> tuple[str, ...]:
        """Return the closed dependency catalog used by Resolve and boot audit."""
        return tuple(capability.key for capability in self.spec.requires)

    def with_config(self, config: type[C]) -> PluginDefinition[C]:
        """Attach a resolved Config carrier while keeping its native schema truthful."""
        schema = f"{config.__module__}.{config.__name__}"
        return replace(
            self,
            Config=config,
            spec=replace(
                self.spec,
                configuration=replace(self.spec.configuration, schema=schema),
            ),
        )

    def with_module(self, module: str) -> PluginDefinition[C]:
        """Attribute the executable implementation to the module Resolve imported."""
        return replace(
            self,
            spec=replace(
                self.spec,
                implementation=replace(self.spec.implementation, module=module),
            ),
        )
