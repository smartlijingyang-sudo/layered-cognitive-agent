"""LCA plugin Manifest API — definition, kinds, audited PluginContext (ADR-0061).

Business plugins import from here (or via the thin ``lca.plugins._cordis_adapter``
compat shim). Vendored Cordis ``Plugin`` remains the carrier; LCA fields live
in ``Plugin.meta`` and on ``PluginDefinition``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from cordis.plugin import Plugin as CordisPlugin
from cordis.plugin import plugin as _cordis_plugin

from lca.contracts.capabilities import Capability, cap_key

__all__ = [
    "EffectClass",
    "PluginContext",
    "PluginDefinition",
    "PluginKind",
    "UndeclaredInteractionError",
    "definition_from_plugin",
    "plugin",
]


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

# Legacy taxonomy → (layer, kind) for migration-period decorators.
_LEGACY_LAYER_MAP: dict[str, tuple[str, PluginKind]] = {
    "service": ("L0", PluginKind.SEAM),
    "provider": ("L0", PluginKind.PROVIDER),
    "behavior": ("L1", PluginKind.PRIMITIVE),
    "guard": ("L1", PluginKind.PRIMITIVE),
    "sensor": ("L1", PluginKind.PRIMITIVE),
}

_LEGACY_EFFECT_MAP: dict[str, frozenset[EffectClass]] = {
    "none": frozenset({EffectClass.NONE}),
    "tools": frozenset({EffectClass.TOOLS}),
    "memory": frozenset({EffectClass.MEMORY}),
    "world": frozenset({EffectClass.WORLD}),
}


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
    """Immutable Manifest read from a module's ``@plugin`` decoration."""

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
    setup: Callable[..., Any]
    module: str | None = None


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
    *,
    side_effects: str | None,
) -> frozenset[EffectClass]:
    if effects is None and side_effects is not None:
        mapped = _LEGACY_EFFECT_MAP.get(side_effects)
        if mapped is None:
            raise ValueError(f"unknown side_effects={side_effects!r}")
        return mapped
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
        raise ValueError("@plugin requires layer= (L0–L4 or legacy taxonomy)")
    if layer in _LAYER_VALUES:
        if kind is None:
            raise ValueError("kind is required when layer is L0–L4")
        return layer, PluginKind(kind) if not isinstance(kind, PluginKind) else kind
    if layer in _LEGACY_LAYER_MAP:
        mapped_layer, mapped_kind = _LEGACY_LAYER_MAP[layer]
        if kind is None:
            return mapped_layer, mapped_kind
        return mapped_layer, PluginKind(kind) if not isinstance(kind, PluginKind) else kind
    raise ValueError(f"unknown layer={layer!r}; expected L0–L4 or legacy taxonomy")


def plugin(
    setup: Callable[..., Any] | None = None,
    *,
    id: str | None = None,
    name: str | None = None,
    Config: type[Any] | None = None,  # noqa: N803
    provides: Sequence[Capability[Any] | str] | None = None,
    requires: Sequence[Capability[Any] | str] | None = None,
    implements: Any = None,
    layer: str | None = None,
    kind: PluginKind | str | None = None,
    effects: EffectClass | str | Sequence[EffectClass | str] | None = None,
    # Legacy kwargs (migration):
    inject: list[str] | None = None,
    side_effects: str | None = None,
    policy_class: str | None = None,
    test_suite: str | None = None,
    description: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Any:
    """Declare a plugin Manifest. ``id`` (or legacy ``name``) is the primary key."""

    def _wrap(fn: Callable[..., Any]) -> CordisPlugin:
        plugin_id = id or name
        if not plugin_id:
            raise ValueError("@plugin requires id= (or legacy name=)")
        resolved_layer, resolved_kind = _resolve_layer_kind(layer=layer, kind=kind)
        config_cls = Config or _config_from_annotations(fn)

        provide_keys = _normalize_keys(provides)
        require_keys = _normalize_keys(requires)
        if inject:
            require_keys = tuple(dict.fromkeys((*require_keys, *inject)))
        impl_names = _normalize_implements(implements)
        effect_set = _normalize_effects(effects, side_effects=side_effects)
        suite = test_suite or ""
        desc = description or ""

        merged_meta: dict[str, Any] = dict(meta) if meta else {}
        merged_meta.update(
            {
                "id": plugin_id,
                "provides": list(provide_keys),
                "requires": list(require_keys),
                "implements": list(impl_names),
                "layer": resolved_layer,
                "kind": resolved_kind.value,
                "effects": sorted(e.value for e in effect_set),
                "test_suite": suite,
                "description": desc,
                "side_effects": next(iter(effect_set)).value if effect_set else "none",
                "policy_class": policy_class or "",
            }
        )
        cordis_plugin = _cordis_plugin(
            fn,
            Config=config_cls,
            name=plugin_id,
            inject=list(require_keys) or None,
            meta=merged_meta,
        )
        object.__setattr__(
            cordis_plugin,
            "_lca_definition",
            PluginDefinition(
                id=plugin_id,
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
            )
        return cached

    meta: Mapping[str, Any] = getattr(plugin_obj, "meta", {}) or {}
    plugin_id = str(meta.get("id") or getattr(plugin_obj, "name", None) or "")
    if not plugin_id:
        raise ValueError("plugin has no id/name")
    kind_raw = meta.get("kind", "primitive")
    effects_raw = meta.get("effects") or [meta.get("side_effects") or "none"]
    layer_raw = str(meta.get("layer") or "L1")
    if layer_raw not in _LAYER_VALUES:
        layer_raw, kind_default = _LEGACY_LAYER_MAP.get(layer_raw, ("L1", PluginKind.PRIMITIVE))
        if "kind" not in meta:
            kind_raw = kind_default.value
    effect_set = _normalize_effects(effects_raw, side_effects=None)
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
    )


@dataclass
class AuditedPluginContext:
    """Wraps cordis.Context; records provide/require and enforces Manifest bounds."""

    _inner: Any
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
        self._inner.provide(k, value, **kwargs)

    def require(self, key: Capability[Any] | str) -> Any:
        k = cap_key(key)
        if k not in self._definition.requires:
            raise UndeclaredInteractionError(
                f"plugin {self._definition.id!r} require({k!r}) not in Manifest requires="
                f"{list(self._definition.requires)}"
            )
        self.required.add(k)
        return self._inner.inject(k)

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
            return self._inner.inject(key)
        try:
            return self._inner.inject(key)
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
        svc = self._inner.inject(k)
        register = getattr(svc, "register", None)
        if not callable(register):
            raise TypeError(f"capability {k!r} has no register()")
        register(name, value, **kwargs)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> Any:
        self.emitted.add(event)
        events = getattr(self._inner, "events", None)
        if events is not None and hasattr(events, "emit"):
            return events.emit(event, *args, **kwargs)
        emit_fn = getattr(self._inner, "emit", None)
        if callable(emit_fn):
            return emit_fn(event, *args, **kwargs)
        raise AttributeError("underlying context has no emit")

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
