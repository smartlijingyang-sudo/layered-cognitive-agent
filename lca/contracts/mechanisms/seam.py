"""Capability Seam 三角色约束（DSH-inspired）。

设计来源：DSH ``docs/capability-seams.md`` —— 每个可替换能力必须包含三个角色：
1. **Service Definition**：接口契约（Protocol）
2. **Service Provider**：具体实现
3. **Consumer**：使用方

一个 seam 只有三角色齐全才算完整能力。单独一个角色不是 seam。

本模块提供：
- ``SeamRole`` 枚举：标记一个 Protocol/类属于哪个角色
- ``seam`` 装饰器：声明 seam 名称和角色
- ``SeamRegistry``：注册和校验 seam 完整性
- ``validate_seam``：检查 seam 三角色是否齐全

消费方式（LCA 不引入 Service Locator）：
    Consumer **只通过构造函数注入 Definition**。这是唯一消费路径。
    ``consume(seam, provider, consumer)`` 是组合期门：确认 ``consumer``
    已登记为该 seam 的 CONSUMER，然后原样返回 provider。
    领域类不查询注册表；L4 / 工厂在接线时过门。

    factory:
        reasoner = PromptReasoner(consume("llm", llm, PromptReasoner), ...)
    PromptReasoner.__init__:
        self.llm = llm
        ...
        await self.llm.complete(...)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar

T = TypeVar("T")


class SeamRole(str, Enum):
    """Capability Seam 的三个角色。"""

    DEFINITION = "definition"
    """接口契约（Protocol）。声明能力的形状，不包含实现。"""

    PROVIDER = "provider"
    """具体实现。实现 Definition 声明的接口。"""

    CONSUMER = "consumer"
    """使用方。注入 Definition，调用其方法。"""


@dataclass(frozen=True)
class SeamDeclaration:
    """一个 seam 的声明记录。"""

    seam_name: str
    role: SeamRole
    cls: type
    """实现该角色的类或 Protocol。"""


@dataclass
class SeamRegistry:
    """Seam 注册表：跟踪所有 seam 的角色分配，校验完整性。

    一个 seam 只有三角色齐全才算完整能力。
    """

    _declarations: dict[str, dict[SeamRole, list[type]]] = field(default_factory=dict)

    def register(self, cls: Any, seam_name: str, role: SeamRole) -> None:
        """注册一个类或可调用对象为某个 seam 的某个角色（同类同角色幂等）。"""
        if seam_name not in self._declarations:
            self._declarations[seam_name] = {}
        if role not in self._declarations[seam_name]:
            self._declarations[seam_name][role] = []
        holders = self._declarations[seam_name][role]
        if cls not in holders:
            holders.append(cls)

    def consumers_of(self, seam_name: str) -> list[type]:
        """该 seam 已登记的 Consumer 类。"""
        return list(self._declarations.get(seam_name, {}).get(SeamRole.CONSUMER, ()))

    def is_registered_consumer(self, seam_name: str, consumer: type) -> bool:
        """``consumer`` 是否登记为该 seam 的 Consumer（含子类）。"""
        for cls in self.consumers_of(seam_name):
            if consumer is cls:
                return True
            if isinstance(cls, type) and isinstance(consumer, type):
                try:
                    if issubclass(consumer, cls):
                        return True
                except TypeError:
                    continue
        return False

    def is_complete(self, seam_name: str) -> bool:
        """检查 seam 是否三角色齐全。"""
        if seam_name not in self._declarations:
            return False
        roles = self._declarations[seam_name]
        return (
            SeamRole.DEFINITION in roles
            and SeamRole.PROVIDER in roles
            and SeamRole.CONSUMER in roles
        )

    def get_missing_roles(self, seam_name: str) -> list[SeamRole]:
        """返回 seam 缺失的角色列表。"""
        if seam_name not in self._declarations:
            return [SeamRole.DEFINITION, SeamRole.PROVIDER, SeamRole.CONSUMER]
        roles = self._declarations[seam_name]
        missing = []
        for role in SeamRole:
            if role not in roles:
                missing.append(role)
        return missing

    def get_seams(self) -> list[str]:
        """返回所有已注册的 seam 名称。"""
        return list(self._declarations.keys())

    def get_roles(self, seam_name: str) -> dict[SeamRole, list[type]]:
        """返回指定 seam 的角色映射。"""
        return self._declarations.get(seam_name, {})


# ── 装饰器语法糖 ──────────────────────────────────────────


def seam(seam_name: str, role: SeamRole) -> Any:
    """声明一个类为某个 seam 的某个角色（装饰器）。

    用法：
        @seam("shell", SeamRole.DEFINITION)
        class Shell(Protocol):
            ...
    """

    def decorator(cls: type) -> type:
        # 在类上附加 seam 元数据
        cls.__seam_name__ = seam_name  # type: ignore[attr-defined]
        cls.__seam_role__ = role  # type: ignore[attr-defined]
        return cls

    return decorator


# ── 全局 seam 注册表（可选）──────────────────────────────

_global_registry = SeamRegistry()


def get_global_seam_registry() -> SeamRegistry:
    """获取全局 seam 注册表。"""
    return _global_registry


def register_seam(cls: Any, seam_name: str, role: SeamRole) -> None:
    """注册到全局 seam 注册表。"""
    _global_registry.register(cls, seam_name, role)


def validate_all_seams() -> list[str]:
    """校验所有已注册 seam 的完整性，返回不完整的 seam 列表。"""
    incomplete = []
    for seam_name in _global_registry.get_seams():
        if not _global_registry.is_complete(seam_name):
            incomplete.append(seam_name)
    return incomplete


class UnauthorizedConsumerError(TypeError):
    """组合期：该类未登记为指定 seam 的 Consumer，无权接收 Provider。"""


class IncompleteSeamError(RuntimeError):
    """声明为完整的 seam 缺角色。"""


def consume(
    seam_name: str, provider: T, consumer: type, *, registry: SeamRegistry | None = None
) -> T:
    """组合期消费门：校验 ``consumer`` 有权注入该 seam 的 Provider，原样返回。

    不持有实例、不解析实现——实例仍由调用方构造并传入。
    这保持 ADR-0005：组合根显式接线，禁止 Service Locator。
    """
    table = registry if registry is not None else _global_registry
    if not table.consumers_of(seam_name):
        return provider
    if not table.is_registered_consumer(seam_name, consumer):
        known = ", ".join(cls.__name__ for cls in table.consumers_of(seam_name)) or "(none)"
        raise UnauthorizedConsumerError(
            f"{consumer.__name__} is not a registered consumer of seam {seam_name!r}; "
            f"registered: {known}"
        )
    return provider


def require_complete(*seam_names: str, registry: SeamRegistry | None = None) -> None:
    """组合期：列出的 seam 必须三角色齐全。"""
    table = registry if registry is not None else _global_registry
    missing = [name for name in seam_names if not table.is_complete(name)]
    if missing:
        detail = {name: [role.value for role in table.get_missing_roles(name)] for name in missing}
        raise IncompleteSeamError(f"incomplete capability seams: {detail}")
