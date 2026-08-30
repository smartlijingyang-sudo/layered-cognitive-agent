"""已解析 Profile 的不可变投影。

这个 module 是 Profile 编译路径读取兼容字段的唯一 seam。它把已解析事实
收敛成稳定的只读视图：插件选择、原生 ``PluginSpec``、配置值、provider
provenance 以及 fallback policy 都在构造时规范化。下游 module 只消费此
投影，不再分别检查 ``setup.meta`` / ``setup.plugin_meta``、旧 ``provides``
字段或 Pydantic 配置形状。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

from lca.contracts.protocols.declarative_plugin import PluginSpec
from lca.harness.profile.immutable import freeze_mapping
from lca.harness.profile.plugin_metadata import plugin_metadata
from lca.harness.profile.resolve import ResolvedPlugin, ResolvedProfile


@dataclass(frozen=True, slots=True)
class ResolvedProfileProjection:
    """Compile-time Profile facts with one narrow, immutable interface.

    ``plugins`` contains the selection requested by the caller; ``all_plugins``
    remains available only for diagnostic provenance, so a disabled provider can
    still be reported when a production runtime closure is incomplete.

    ``plugin_specs`` is the canonical native capability catalog for the selected
    plugins. Capability closure, provider bindings, phase compilation, and plan
    diagnostics must all derive their capability facts from this one catalog.
    """

    resolved: ResolvedProfile
    include_disabled: bool
    plugins: tuple[ResolvedPlugin, ...]
    all_plugins: tuple[ResolvedPlugin, ...]
    plugin_ids: frozenset[str]
    capability_keys: frozenset[str]
    providers: Mapping[str, tuple[str, ...]]
    fallback_policy: Mapping[str, str]
    plugin_specs: tuple[PluginSpec, ...]
    _metadata: Mapping[str, Mapping[str, Any]]
    _configuration: Mapping[str, Mapping[str, Any]]
    _plugin_specs: Mapping[str, PluginSpec]

    @classmethod
    def build(
        cls,
        resolved: ResolvedProfile,
        *,
        include_disabled: bool = False,
    ) -> ResolvedProfileProjection:
        """Create the sole normalized read model for one resolved Profile."""
        all_plugins = tuple(resolved.plugins)
        plugins = tuple(plugin for plugin in all_plugins if include_disabled or not plugin.disabled)
        metadata = {
            plugin.id: freeze_mapping(_metadata_from_plugin(plugin)) for plugin in all_plugins
        }
        configuration = {
            plugin.id: freeze_mapping(_configuration_values(plugin.config))
            for plugin in all_plugins
        }
        specs_by_plugin_id = {
            plugin.id: _configured_native_spec(plugin, configuration[plugin.id])
            for plugin in plugins
            if _has_native_spec(plugin)
        }
        providers: dict[str, list[str]] = {}
        for plugin in plugins:
            spec = specs_by_plugin_id.get(plugin.id)
            if spec is None:
                continue
            for capability in spec.provides:
                providers.setdefault(capability.key, []).append(plugin.id)
        fallback = (
            dict(resolved.fallback_policy) if isinstance(resolved.fallback_policy, Mapping) else {}
        )
        return cls(
            resolved=resolved,
            include_disabled=include_disabled,
            plugins=plugins,
            all_plugins=all_plugins,
            plugin_ids=frozenset(plugin.id for plugin in plugins),
            capability_keys=frozenset(providers),
            providers=MappingProxyType(
                {key: tuple(provider_ids) for key, provider_ids in providers.items()}
            ),
            fallback_policy=MappingProxyType(fallback),
            plugin_specs=tuple(
                specs_by_plugin_id[plugin.id]
                for plugin in plugins
                if plugin.id in specs_by_plugin_id
            ),
            _metadata=MappingProxyType(metadata),
            _configuration=MappingProxyType(configuration),
            _plugin_specs=MappingProxyType(specs_by_plugin_id),
        )

    @classmethod
    def reuse_or_build(
        cls,
        resolved: ResolvedProfile,
        *,
        include_disabled: bool,
        projection: ResolvedProfileProjection | None = None,
    ) -> ResolvedProfileProjection:
        """Return a compatible projection or build the single normalized view.

        A compilation pass may share one projection across its capability,
        control, declarative, and runtime-closure steps. Rejecting a projection
        for another resolved profile or plugin-selection mode keeps that reuse
        fail-closed rather than silently mixing plan facts.
        """
        if projection is None:
            return cls.build(resolved, include_disabled=include_disabled)
        if projection.resolved is not resolved:
            raise ValueError("profile projection belongs to a different resolved profile")
        if projection.include_disabled is not include_disabled:
            raise ValueError(
                "profile projection include_disabled does not match the requested projection"
            )
        return projection

    def metadata_for(self, plugin: ResolvedPlugin) -> Mapping[str, Any]:
        """Return the merged legacy metadata for a resolved plugin."""
        return self._metadata.get(plugin.id, MappingProxyType({}))

    def configuration_for(self, plugin: ResolvedPlugin) -> Mapping[str, Any]:
        """Return JSON-ready profile configuration values for a resolved plugin."""
        return self._configuration.get(plugin.id, MappingProxyType({}))

    def require_native_plugin_specs(self) -> tuple[PluginSpec, ...]:
        """Return the selected native specs or reject an incomplete executable catalog."""
        missing = tuple(plugin.id for plugin in self.plugins if plugin.id not in self._plugin_specs)
        if missing:
            raise ValueError(
                "PS-002: active plugins must declare native PluginSpec values; missing "
                + ", ".join(missing)
            )
        return self.plugin_specs

    def spec_for(self, plugin: ResolvedPlugin) -> PluginSpec:
        """Return one configured native PluginSpec from the canonical catalog."""
        try:
            return self._plugin_specs[plugin.id]
        except KeyError as exc:
            raise ValueError(
                f"PS-002: active plugin {plugin.id!r} must declare a native PluginSpec"
            ) from exc

    def fallback_for(self, capability: str, *, default: str) -> str:
        """Return one normalized closure fallback policy."""
        return self.fallback_policy.get(capability, default)

    def candidates_for(self, capability: str) -> tuple[str, ...]:
        """Return diagnostic sources, including disabled plugins when relevant."""
        candidates: list[str] = []
        capability_fragment = (
            capability.replace("_registry", "").replace("_store", "").replace("_", "")
        )
        for plugin in self.all_plugins:
            if capability_fragment and (
                capability_fragment in plugin.module.lower()
                or capability_fragment in plugin.id.lower()
            ):
                candidates.append(
                    f"{plugin.id} (module={plugin.module}, source={plugin.source or '?'})"
                )
        if not candidates:
            candidates.extend(f"bundle: {bundle}" for bundle in self.resolved.bundles)
        return tuple(candidates)


@dataclass(frozen=True, slots=True)
class ProfileCompilationProjections:
    """Compile-time views with explicit runtime and inspection selection.

    Runtime closure always consumes ``active`` so disabled plugins can never
    satisfy production requirements. The remaining compilation passes consume
    ``selected``, which may include disabled plugins only for an explicit
    inspection request. Keeping this selection here prevents plan compilers
    from re-implementing profile activation semantics.
    """

    active: ResolvedProfileProjection
    selected: ResolvedProfileProjection

    @classmethod
    def build(
        cls,
        resolved: ResolvedProfile,
        *,
        include_disabled: bool = False,
    ) -> ProfileCompilationProjections:
        """Build the minimum immutable views needed by one compilation pass."""
        active = ResolvedProfileProjection.build(resolved)
        selected = (
            active
            if not include_disabled
            else ResolvedProfileProjection.build(resolved, include_disabled=True)
        )
        return cls(active=active, selected=selected)


def _has_native_spec(plugin: ResolvedPlugin) -> bool:
    """Return whether one resolved plugin exposes the required native declaration."""
    return isinstance(getattr(plugin.definition, "spec", None), PluginSpec)


def _configured_native_spec(
    plugin: ResolvedPlugin,
    configuration: Mapping[str, Any],
) -> PluginSpec:
    """Freeze the profile-selected configuration into one native declaration."""
    declared = plugin.definition.spec
    if not isinstance(declared, PluginSpec):
        raise TypeError(f"plugin {plugin.id!r} has no native PluginSpec")
    if declared.id != plugin.id:
        raise ValueError(f"PS-001: PluginSpec id {declared.id!r} != profile id {plugin.id!r}")
    values = {**dict(declared.configuration.values), **dict(configuration)}
    return replace(declared, configuration=replace(declared.configuration, values=values))


def _metadata_from_plugin(plugin: ResolvedPlugin) -> dict[str, Any]:
    """Delegate legacy metadata compatibility to the shared profile seam."""
    return dict(plugin_metadata(plugin))


def _configuration_values(config: Any) -> dict[str, Any]:
    """Convert supported resolved configuration forms to a stable mapping."""
    model_dump = getattr(config, "model_dump", None)
    if callable(model_dump):
        values = model_dump(mode="json")
        return dict(values) if isinstance(values, Mapping) else {}
    return dict(config) if isinstance(config, Mapping) else {}


__all__ = ["ProfileCompilationProjections", "ResolvedProfileProjection"]
