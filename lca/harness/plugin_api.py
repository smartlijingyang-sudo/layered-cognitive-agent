"""LCA plugin Manifest API — definition, kinds, audited PluginContext (ADR-0061 / ADR-0062).

Business plugins import :func:`plugin` from here directly. Vendored Cordis
``Plugin`` remains the carrier; LCA fields live in ``Plugin.meta`` and on
:data:`PluginDefinition`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from cordis.plugin import Plugin as CordisPlugin
from cordis.plugin import plugin as _cordis_plugin
from pydantic import BaseModel

from lca.contracts.capabilities import Capability, cap_key

if TYPE_CHECKING:
    from lca.contracts.atoms.functional_group import FunctionalGroup
    from lca.contracts.harness.plugin_contract import PluginContract
    from lca.contracts.protocols.logic_address import LogicAddress

__all__ = [
    "EffectClass",
    "PluginContext",
    "PluginDefinition",
    "PluginKind",
    "PluginSetupFn",
    "UndeclaredInteractionError",
    "definition_from_plugin",
    "plugin",
]

# A plugin's ``setup`` callable MUST match this signature. The constraint
# lives at the decorator entry point on purpose: mypy enforces it for every
# ``@plugin``-decorated function, so untyped ``async def setup(ctx, config)``
# is rejected at decoration time, not at use time. ``BaseModel`` is the
# abstract bound for the pydantic Config; concrete subclasses satisfy it.
PluginSetupFn = Callable[["PluginContext", BaseModel], Awaitable[None]]


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

# (ADR-0062 §1) Legacy taxonomy / kwargs were deleted: every plugin must
# declare canonical ``layer="L0".."L4"`` plus ``kind=PluginKind.X`` and
# ``effects=...``. No migration shim is kept — "delete the compat layer,
# don't keep a second track" (B7).


class UndeclaredInteractionError(RuntimeError):
    """setup() used a capability key not listed in Manifest provides/requires."""


@runtime_checkable
class PluginContext(Protocol):
    """Audited interaction surface for plugin setup (ADR-0061 §七)."""

    def provide(self, key: Capability[Any] | str, value: Any, **kwargs: Any) -> None: ...

    def require(self, key: Capability[Any] | str) -> Any: ...

    def inject(self, key: str, *, default: Any = ...) -> Any: ...

    def register(
        self, seam: Capability[Any] | str, name: str, value: Any, **kwargs: Any
    ) -> None: ...

    def emit(self, event: str, *args: Any, **kwargs: Any) -> Any: ...


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    """Immutable Manifest read from a module's ``@plugin`` decoration.

    PR-2 / ADR-0069 / ADR-0074 PR-2 新增 4 个可选字段（**全部 opt-in**）：

    - ``control`` — 该 plugin 投到哪些 Control Slot（ADR-0066 §三 + ADR-0074 §一）
    - ``functional_group`` — 13 原语群主归属（ADR-0069 §一）
    - ``logic_address`` — 6 维 LogicAddress（ADR-0069 §二）
    - ``contract`` — PluginContract 9 段 typed section（ADR-0069 §六；可选并存）

    缺失字段 → plugin 行为不变（旧 plugin 不破）；``lca plugin check``
    输出 warning（不阻断）。``lca plugin check --strict`` 才报错退出码 1。
    """

    id: str
    Config: type[Any] | None
    provides: tuple[str, ...]
    requires: tuple[str, ...]
    implements: tuple[str, ...]
    layer: str
    kind: PluginKind
    effects: frozenset[EffectClass]
    test_suite: str
    description: str
    setup: PluginSetupFn
    module: str | None = None
    # PR-2 新增字段（全部 Optional）
    control: tuple[Any, ...] = ()  # raw control entries (parsed at resolve time)
    functional_group: FunctionalGroup | None = None
    logic_address: LogicAddress | None = None
    contract: PluginContract | None = None
    spec: Any | None = None


def _normalize_keys(values: Sequence[Capability[Any] | str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    return tuple(cap_key(v) for v in values)


def _config_from_annotations(fn: Callable[..., Any]) -> type[Any] | None:
    """Pick Pydantic Config from ``config: Config`` annotation when Config= omitted."""
    try:
        import typing

        from pydantic import BaseModel

        resolved = typing.get_type_hints(fn)
        annotated = resolved.get("config")
        if isinstance(annotated, type) and issubclass(annotated, BaseModel):
            return annotated
    except Exception:
        return None
    return None


def _resolve_functional_group(
    value: Any,
) -> Any:
    """Resolve FunctionalGroup from str / enum / None; returns enum or None."""
    if value is None:
        return None
    from lca.contracts.atoms.functional_group import (
        FunctionalGroup,
        parse_functional_group,
    )

    if isinstance(value, FunctionalGroup):
        return value
    if isinstance(value, str):
        try:
            return parse_functional_group(value)
        except ValueError as exc:
            raise ValueError(f"@plugin functional_group: {exc}") from exc
    raise TypeError(
        f"@plugin functional_group must be str or FunctionalGroup, got {type(value).__name__}"
    )


def _normalize_control(
    value: Sequence[Any] | None,
) -> tuple[Any, ...]:
    """Normalize control= decorator arg into tuple; raise on non-iterable non-None."""
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(value)
    raise TypeError(f"@plugin control must be list/tuple, got {type(value).__name__}")


def _normalize_implements(values: Any) -> tuple[str, ...]:
    if not values:
        return ()
    out: list[str] = []
    for v in values:
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, type):
            out.append(v.__name__)
        else:
            out.append(str(v))
    return tuple(out)


def _normalize_effects(
    effects: EffectClass | str | Sequence[EffectClass | str] | None,
) -> frozenset[EffectClass]:
    if effects is None:
        return frozenset({EffectClass.NONE})
    if isinstance(effects, (EffectClass, str)):
        items: Sequence[EffectClass | str] = (effects,)
    else:
        items = effects
    out: set[EffectClass] = set()
    for item in items:
        out.add(EffectClass(item) if not isinstance(item, EffectClass) else item)
    if EffectClass.NONE in out and len(out) > 1:
        out.discard(EffectClass.NONE)
    return frozenset(out)


def _resolve_layer_kind(
    *,
    layer: str | None,
    kind: PluginKind | str | None,
) -> tuple[str, PluginKind]:
    if layer is None:
        raise ValueError("@plugin requires layer= (one of L0–L4)")
    if layer not in _LAYER_VALUES:
        raise ValueError(f"unknown layer={layer!r}; expected L0–L4 (no legacy taxonomy)")
    if kind is None:
        raise ValueError("kind= is required when layer is L0–L4")
    return layer, PluginKind(kind) if not isinstance(kind, PluginKind) else kind


def _native_spec_from_declaration(
    *, plugin_id: str, config_cls: type[Any] | None, provides: tuple[str, ...],
    requires: tuple[str, ...], layer: str, kind: PluginKind,
    effects: frozenset[EffectClass], test_suite: str, functional_group: Any,
    module: str,
) -> Any:
    """Create the baseline typed spec at plugin declaration time.

    Explicit ``spec=`` remains authoritative.  The baseline uses only typed
    decorator arguments, so PlanCompiler no longer owns a compatibility
    projection or a second architecture source of truth.
    """
    from lca.contracts.protocols.declarative_phase_graph import (
        CapabilityDeclaration,
        EvidenceDeclaration,
        LifecycleDeclaration,
        OwnershipDeclaration,
        PluginConfiguration,
        PluginImplementation,
        PluginSpec,
        PluginSpecKind,
        VerificationDeclaration,
    )
    kind_map = {
        PluginKind.SEAM: PluginSpecKind.SEAM, PluginKind.PROVIDER: PluginSpecKind.PROVIDER,
        PluginKind.PRIMITIVE: PluginSpecKind.PROVIDER, PluginKind.COMPOSITE: PluginSpecKind.COMPOSITE,
        PluginKind.DRIVER: PluginSpecKind.DRIVER, PluginKind.BRIDGE: PluginSpecKind.PROVIDER,
    }
    spec_kind = kind_map[kind]
    effect_values = tuple(sorted(item.value for item in effects)) or ("none",)
    if spec_kind is PluginSpecKind.SEAM and any(item != "none" for item in effect_values):
        spec_kind = PluginSpecKind.PROVIDER
    config_name = f"{config_cls.__module__}.{config_cls.__name__}" if config_cls else "builtins.dict"
    return PluginSpec(
        api_version="lca/plugin-spec/v1", id=plugin_id, revision="1.0.0", kind=spec_kind,
        layer=layer, functional_group=(functional_group.value if functional_group else f"declared-{layer.lower()}"),
        implementation=PluginImplementation(module=module, setup="setup"),
        configuration=PluginConfiguration(schema=config_name),
        provides=tuple(CapabilityDeclaration(key=key, cardinality="many", protocol="object") for key in provides),
        requires=tuple(CapabilityDeclaration(key=key, cardinality="optional", protocol="object") for key in requires),
        effects=effect_values, ownership=OwnershipDeclaration(state_mutation="forbidden"),
        lifecycle=LifecycleDeclaration(scopes=("profile", "run"), activation="true", disposal="required"),
        relations=(), evidence=EvidenceDeclaration(emits=("RuntimeObserved",), replay="required"),
        verification=VerificationDeclaration(test_suite=test_suite or "tests", properties=("typed_plugin_spec",)),
    )


def plugin(
    setup: PluginSetupFn | None = None,
    *,
    id: str,
    Config: type[Any] | None = None,  # noqa: N803
    provides: Sequence[Capability[Any] | str] | None = None,
    requires: Sequence[Capability[Any] | str] | None = None,
    implements: Any = None,
    layer: str,
    kind: PluginKind,
    effects: EffectClass | str | Sequence[EffectClass | str] | None = None,
    test_suite: str | None = None,
    description: str | None = None,
    meta: dict[str, Any] | None = None,
    control: Sequence[Any] | None = None,
    functional_group: FunctionalGroup | str | None = None,
    logic_address: LogicAddress | None = None,
    contract: PluginContract | None = None,
    spec: Any | None = None,
) -> Any:
    """Declare a plugin Manifest (ADR-0062 §1 + ADR-0074 PR-2).

    Required: ``id``, ``layer`` (``L0``–``L4``), ``kind``.
    Optional: ``provides``, ``requires``, ``implements``, ``effects``,
    ``Config``, ``test_suite``, ``description``, ``meta``,
    ``control`` (PR-2), ``functional_group`` (PR-2),
    ``logic_address`` (PR-2), ``contract`` (PR-2).

    PR-2 新增字段：

    - ``control`` — 该 plugin 投到哪些 Control Slot（raw dict 列表；
      resolver 阶段投影为 ControlEntry）
    - ``functional_group`` — 13 原语群主归属（FunctionalGroup enum）
    - ``logic_address`` — 6 维 LogicAddress（v9 评分输入）
    - ``contract`` — PluginContract 9 段 typed section（不替换元字段，
      作为可选并存）

    No legacy kwargs (``name``, ``inject``, ``side_effects``,
    ``policy_class``, taxonomy ``service``/``provider``/``behavior``/
    ``guard``/``sensor``) are accepted — every plugin must declare
    canonical fields directly.

    The ``setup`` callable (or the function the decorator is applied to)
    MUST match :data:`PluginSetupFn`: ``async def setup(ctx: PluginContext,
    config: <BaseModel>) -> None``. Type-checking is enforced by mypy via
    :data:`PluginSetupFn`; :func:`scripts.check_plugin_typing` enforces it
    as a pre-commit fallback.
    """

    def _wrap(fn: PluginSetupFn) -> CordisPlugin:
        resolved_layer, resolved_kind = _resolve_layer_kind(layer=layer, kind=kind)
        config_cls = Config or _config_from_annotations(fn)

        provide_keys = _normalize_keys(provides)
        require_keys = _normalize_keys(requires)
        impl_names = _normalize_implements(implements)
        effect_set = _normalize_effects(effects)
        suite = test_suite or ""
        desc = description or ""
        fg = _resolve_functional_group(functional_group)
        control_tuple = _normalize_control(control)

        merged_meta: dict[str, Any] = dict(meta) if meta else {}
        merged_meta.update(
            {
                "id": id,
                "provides": list(provide_keys),
                "requires": list(require_keys),
                "implements": list(impl_names),
                "layer": resolved_layer,
                "kind": resolved_kind.value,
                "effects": sorted(e.value for e in effect_set),
                "test_suite": suite,
                "description": desc,
            }
        )
        if fg is not None:
            merged_meta["functional_group"] = fg.value
        cordis_plugin = _cordis_plugin(
            fn,
            Config=config_cls,
            name=id,
            inject=list(require_keys) or None,
            meta=merged_meta,
        )
        object.__setattr__(
            cordis_plugin,
            "_lca_definition",
            PluginDefinition(
                id=id,
                Config=config_cls,
                provides=provide_keys,
                requires=require_keys,
                implements=impl_names,
                layer=resolved_layer,
                kind=resolved_kind,
                effects=effect_set,
                test_suite=suite,
                description=desc,
                setup=fn,
                control=control_tuple,
                functional_group=fg,
                logic_address=logic_address,
                contract=contract,
                spec=spec or _native_spec_from_declaration(
                    plugin_id=id, config_cls=config_cls, provides=provide_keys,
                    requires=require_keys, layer=resolved_layer, kind=resolved_kind,
                    effects=effect_set, test_suite=suite, functional_group=fg,
                    module=fn.__module__,
                ),
            ),
        )
        return cordis_plugin

    if setup is not None and callable(setup):
        return _wrap(setup)
    return _wrap


def definition_from_plugin(
    plugin_obj: CordisPlugin | Any, *, module: str | None = None
) -> PluginDefinition:
    """Extract :class:`PluginDefinition` from a Cordis Plugin or decorated module.setup."""
    cached = getattr(plugin_obj, "_lca_definition", None)
    if isinstance(cached, PluginDefinition):
        if module and cached.module != module:
            return PluginDefinition(
                id=cached.id,
                Config=cached.Config,
                provides=cached.provides,
                requires=cached.requires,
                implements=cached.implements,
                layer=cached.layer,
                kind=cached.kind,
                effects=cached.effects,
                test_suite=cached.test_suite,
                description=cached.description,
                setup=cached.setup,
                module=module,
                control=cached.control,
                functional_group=cached.functional_group,
                logic_address=cached.logic_address,
                contract=cached.contract,
                spec=cached.spec,
            )
        return cached

    meta: Mapping[str, Any] = getattr(plugin_obj, "meta", {}) or {}
    plugin_id = str(meta.get("id") or getattr(plugin_obj, "name", None) or "")
    if not plugin_id:
        raise ValueError("plugin has no id")
    kind_raw = meta.get("kind", "primitive")
    effects_raw = meta.get("effects") or ["none"]
    layer_raw = str(meta.get("layer") or "L1")
    if layer_raw not in _LAYER_VALUES:
        raise ValueError(f"plugin {plugin_id!r} has invalid layer={layer_raw!r}")
    effect_set = _normalize_effects(effects_raw)
    fg = _resolve_functional_group(meta.get("functional_group"))
    setup_fn = getattr(plugin_obj, "setup", plugin_obj)
    return PluginDefinition(
        id=plugin_id,
        Config=getattr(plugin_obj, "Config", None),
        provides=tuple(meta.get("provides") or ()),
        requires=tuple(meta.get("requires") or getattr(plugin_obj, "inject", None) or ()),
        implements=tuple(meta.get("implements") or ()),
        layer=layer_raw,
        kind=PluginKind(kind_raw),
        effects=effect_set,
        test_suite=str(meta.get("test_suite") or ""),
        description=str(meta.get("description") or ""),
        setup=setup_fn,
        module=module,
        functional_group=fg,
    )


@dataclass
class AuditedPluginContext:
    """Wraps a Context and expose only Manifest-audited setup interactions."""

    __inner: Any
    _definition: PluginDefinition
    provided: set[str] = field(default_factory=set)
    required: set[str] = field(default_factory=set)
    registered: set[tuple[str, str]] = field(default_factory=set)
    emitted: set[str] = field(default_factory=set)

    def provide(self, key: Capability[Any] | str, value: Any, **kwargs: Any) -> None:
        k = cap_key(key)
        if k not in self._definition.provides:
            raise UndeclaredInteractionError(
                f"plugin {self._definition.id!r} provide({k!r}) not in Manifest provides="
                f"{list(self._definition.provides)}"
            )
        self.provided.add(k)
        self.__inner.provide(k, value, **kwargs)

    def require(self, key: Capability[Any] | str) -> Any:
        k = cap_key(key)
        if k not in self._definition.requires:
            raise UndeclaredInteractionError(
                f"plugin {self._definition.id!r} require({k!r}) not in Manifest requires="
                f"{list(self._definition.requires)}"
            )
        self.required.add(k)
        return self.__inner.inject(k)

    def inject(self, key: str, *, default: Any = ...) -> Any:
        """Compat alias for require(); undeclared keys fail unless default given."""
        if key not in self._definition.requires:
            if default is ...:
                raise UndeclaredInteractionError(
                    f"plugin {self._definition.id!r} inject({key!r}) not in Manifest requires="
                    f"{list(self._definition.requires)}"
                )
            return default
        self.required.add(key)
        if default is ...:
            return self.__inner.inject(key)
        try:
            return self.__inner.inject(key)
        except KeyError:
            return default

    def register(self, seam: Capability[Any] | str, name: str, value: Any, **kwargs: Any) -> None:
        k = cap_key(seam)
        if k not in self._definition.requires and k not in self._definition.provides:
            raise UndeclaredInteractionError(
                f"plugin {self._definition.id!r} register({k!r}, {name!r}) needs seam in "
                f"requires or provides"
            )
        self.registered.add((k, name))
        svc = self.__inner.inject(k)
        register = getattr(svc, "register", None)
        if not callable(register):
            raise TypeError(f"capability {k!r} has no register()")
        register(name, value, **kwargs)

    @property
    def events(self) -> Any:
        """Expose the event bus without exposing capability mutation or injection."""

        events = getattr(self.__inner, "events", None)
        if events is None:
            raise AttributeError("underlying context has no events")
        return events

    def emit(self, event: str, *args: Any, **kwargs: Any) -> Any:
        self.emitted.add(event)
        events = getattr(self.__inner, "events", None)
        if events is not None and hasattr(events, "emit"):
            return events.emit(event, *args, **kwargs)
        emit_fn = getattr(self.__inner, "emit", None)
        if callable(emit_fn):
            return emit_fn(event, *args, **kwargs)
        raise AttributeError("underlying context has no emit")
