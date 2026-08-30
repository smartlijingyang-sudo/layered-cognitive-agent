"""插件启动时的受审计交互接缝。

运行期能力读取、提供、注册与事件投递都通过 ``AuditedPluginContext`` 记录并核对
Manifest。它不理解装饰器参数或 Cordis 载体投影，从而让 setup 授权保持局部可测。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, cast, runtime_checkable

from lca.contracts.capabilities import Capability, cap_key
from lca.harness.plugin_manifest import PluginDefinition

__all__ = [
    "AuditedPluginContext",
    "PluginContext",
    "PluginEventBus",
    "UndeclaredInteractionError",
]


class PluginEventBus(Protocol):
    """Minimal event surface available to plugin setup without exposing Context."""

    def emit(self, event: str, *args: object, **kwargs: object) -> object: ...


class _PluginRuntimeCarrier(Protocol):
    """Minimal Cordis context surface used behind the audited facade."""

    def provide(self, key: str, value: object, **kwargs: object) -> None: ...

    def inject(self, key: str) -> Any: ...  # 动态能力注入边界


class UndeclaredInteractionError(RuntimeError):
    """setup() used a capability key not listed in Manifest provides/requires."""


@runtime_checkable
class PluginContext(Protocol):
    """Audited interaction surface for plugin setup (ADR-0061 §七)."""

    def provide(self, key: Capability[object] | str, value: object, **kwargs: object) -> None: ...

    def require(self, key: Capability[object] | str) -> Any: ...  # 动态能力注入边界

    def register(
        self, seam: Capability[object] | str, name: str, value: object, **kwargs: object
    ) -> None: ...

    @property
    def events(self) -> PluginEventBus: ...

    def emit(self, event: str, *args: object, **kwargs: object) -> object: ...


@dataclass
class AuditedPluginContext:
    """Wraps a Context and expose only Manifest-audited setup interactions."""

    __inner: object
    _definition: PluginDefinition
    provided: set[str] = field(default_factory=set)
    required: set[str] = field(default_factory=set)
    registered: set[tuple[str, str]] = field(default_factory=set)
    emitted: set[str] = field(default_factory=set)

    def _runtime(self) -> _PluginRuntimeCarrier:
        """Return the narrow operational surface without exposing it to plugins."""
        return cast("_PluginRuntimeCarrier", self.__inner)

    def _assert_declared(
        self,
        key: str,
        operation: str,
        allowed: Sequence[str],
        declaration: str | None = None,
    ) -> None:
        """Enforce one audited interaction against its manifest declaration."""
        if key not in allowed:
            declared_as = declaration or f"{operation}s"
            raise UndeclaredInteractionError(
                f"plugin {self._definition.id!r} {operation}({key!r}) not in native "
                f"PluginSpec {declared_as}={list(allowed)}"
            )

    def provide(self, key: Capability[object] | str, value: object, **kwargs: object) -> None:
        capability_key = cap_key(key)
        self._assert_declared(
            capability_key,
            "provide",
            self._definition.provided_capability_keys,
        )
        self.provided.add(capability_key)
        self._runtime().provide(capability_key, value, **kwargs)

    def require(self, key: Capability[object] | str) -> Any:  # 动态能力注入边界
        capability_key = cap_key(key)
        self._assert_declared(
            capability_key,
            "require",
            self._definition.required_capability_keys,
        )
        self.required.add(capability_key)
        return self._runtime().inject(capability_key)

    def register(
        self,
        seam: Capability[object] | str,
        name: str,
        value: object,
        **kwargs: object,
    ) -> None:
        capability_key = cap_key(seam)
        if (
            capability_key not in self._definition.required_capability_keys
            and capability_key not in self._definition.provided_capability_keys
        ):
            raise UndeclaredInteractionError(
                f"plugin {self._definition.id!r} register({capability_key!r}, {name!r}) needs seam in "
                "requires or provides"
            )
        self.registered.add((capability_key, name))
        service = self._runtime().inject(capability_key)
        register = getattr(service, "register", None)
        if not callable(register):
            raise TypeError(f"capability {capability_key!r} has no register()")
        register(name, value, **kwargs)

    @property
    def events(self) -> PluginEventBus:
        """Expose the event bus without exposing capability mutation or injection."""
        events = getattr(self.__inner, "events", None)
        if events is None:
            raise AttributeError("underlying context has no events")
        return cast("PluginEventBus", events)

    def emit(self, event: str, *args: object, **kwargs: object) -> object:
        self.emitted.add(event)
        events = getattr(self.__inner, "events", None)
        if events is not None and hasattr(events, "emit"):
            return events.emit(event, *args, **kwargs)
        emit_fn = getattr(self.__inner, "emit", None)
        if callable(emit_fn):
            return emit_fn(event, *args, **kwargs)
        raise AttributeError("underlying context has no emit")
