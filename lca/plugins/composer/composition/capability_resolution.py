"""计划绑定的能力解析适配器。

``CompiledRunPlan`` 使用不可变的 ``ProviderBinding`` 描述运行闭包，而已
启动的 Cordis scope 以注入键提供实现。本模块是两者之间唯一的适配器：它
直接消费编译计划投影出的解析键，并保留精确 composer 查找的严格语义。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from lca.contracts.protocols.perceive.capability_plan import ProviderBinding


class CapabilityResolutionError(LookupError):
    """计划声明的能力无法从已启动 scope 解析。"""


@dataclass(frozen=True, slots=True)
class ScopeCapabilityResolver:
    """将已启动 scope 的 ``inject`` 操作适配为计划能力解析接口。"""

    _inject: Callable[[str], Any]

    @classmethod
    def from_scope(cls, scope: object) -> ScopeCapabilityResolver:
        """创建只依赖已启动 Cordis scope 的解析器。"""

        inject = getattr(scope, "inject", None)
        if not callable(inject):
            raise CapabilityResolutionError("scope does not expose inject()")
        return cls(inject)

    def require_exact(self, capability: str) -> object:
        """解析必须使用完整声明键的能力，例如 ``composer.brain``。"""

        try:
            return self._inject(capability)
        except (KeyError, LookupError) as exc:
            raise CapabilityResolutionError(capability) from exc

    def require_provider_binding(self, binding: ProviderBinding) -> object:
        """Resolve one provider binding through its compiled scope key."""

        try:
            return self._inject(binding.resolution_key)
        except (KeyError, LookupError) as exc:
            raise CapabilityResolutionError(
                f"capability {binding.capability!r} declares unavailable resolution key "
                f"{binding.resolution_key!r}: {exc}"
            ) from exc

    def require_declared_capabilities(
        self,
        bindings: Iterable[ProviderBinding],
        capabilities: Iterable[str],
    ) -> dict[str, object]:
        """Resolve a closed capability snapshot through compiled provider bindings.

        Callers name the capabilities they need, while the immutable plan owns
        the resolution keys that expose their providers in a booted scope.  The
        adapter validates missing and ambiguous declarations before the first
        lookup, so a consumer cannot obtain a partial closure or silently
        re-infer a scope key from a capability name.
        """

        requested = tuple(sorted(set(capabilities)))
        requested_set = set(requested)
        selected: dict[str, ProviderBinding] = {}
        for binding in bindings:
            if binding.capability not in requested_set:
                continue
            previous = selected.get(binding.capability)
            if previous is not None:
                raise CapabilityResolutionError(
                    f"compiled plan declares multiple provider bindings for "
                    f"capability {binding.capability!r}: "
                    f"{previous.owner_plugin!r} and {binding.owner_plugin!r}"
                )
            selected[binding.capability] = binding

        missing = tuple(capability for capability in requested if capability not in selected)
        if missing:
            raise CapabilityResolutionError(
                "compiled plan does not declare required capabilities: " + ", ".join(missing)
            )
        return {
            capability: self.require_provider_binding(selected[capability])
            for capability in requested
        }

    def require_exact_bindings(self, capabilities: Iterable[str]) -> dict[str, object]:
        """解析一份稳定的精确能力快照，供计划消费者在调用前闭合依赖。

        每项能力始终以完整声明键查找，不允许退化到命名空间根键。排序与去重
        使查找顺序可复现；任何能力缺失都会在返回局部快照前失败，从而避免不同
        运行时消费者各自直接访问 scope 并形成不一致的错误语义。
        """

        return {
            capability: self.require_exact(capability) for capability in sorted(set(capabilities))
        }


__all__ = [
    "CapabilityResolutionError",
    "ScopeCapabilityResolver",
]
