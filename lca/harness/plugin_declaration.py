"""插件声明的 Cordis 载体适配器。

``@plugin`` 是开放装饰器参数进入不可变 ``PluginDefinition`` 的唯一接缝。输入字段
规范化委派给 ``plugin_declaration_normalization``，类型化 ``PluginSpec`` 构造委派给
``plugin_spec_projection``；本模块仅负责载体创建与已装饰插件的 Manifest 提取。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Protocol, cast

from cordis.plugin import Plugin as CordisPlugin
from cordis.plugin import plugin as _cordis_plugin
from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.capabilities import Capability
from lca.harness.plugin_declaration_normalization import (
    config_from_annotations,
    normalize_contributes,
    normalize_effects,
    normalize_implements,
    normalize_keys,
    normalize_relations,
    resolve_functional_group,
    resolve_layer_kind,
)
from lca.harness.plugin_manifest import (
    _LAYER_VALUES,
    EffectClass,
    PluginDefinition,
    PluginKind,
    PluginMetadata,
    PluginSetupFn,
    RawRelationEntry,
)
from lca.harness.plugin_spec_projection import native_spec_from_declaration

if TYPE_CHECKING:
    from lca.contracts.harness.plugin_contract import PluginContract
    from lca.contracts.protocols.declarative.declarative_phase_graph import PluginSpec
    from lca.contracts.protocols.composition.logic_address import LogicAddress


__all__ = ["PluginCarrier", "definition_from_plugin", "plugin"]


class PluginCarrier(Protocol):
    """Profile Resolve 读取 Manifest 时所需的最小 Cordis 载体形状。"""

    setup: PluginSetupFn
    Config: type[BaseModel] | None
    name: str | None
    inject: Sequence[str] | None
    meta: PluginMetadata


def plugin(
    setup: PluginSetupFn | None = None,
    *,
    id: str,
    Config: type[BaseModel] | None = None,  # noqa: N803
    provides: Sequence[Capability[object] | str] | None = None,
    requires: Sequence[Capability[object] | str] | None = None,
    implements: object = None,
    layer: str,
    kind: PluginKind,
    effects: EffectClass | str | Sequence[EffectClass | str] | None = None,
    test_suite: str | None = None,
    description: str | None = None,
    meta: PluginMetadata | None = None,
    relations: Sequence[RawRelationEntry] | None = None,
    contributes: Sequence[object] | None = None,
    functional_group: FunctionalGroup | str | None = None,
    logic_address: LogicAddress | None = None,
    contract: PluginContract | None = None,
    spec: PluginSpec | None = None,
) -> CordisPlugin | Callable[[PluginSetupFn], CordisPlugin]:
    """Declare a plugin Manifest and adapt it to the Cordis carrier.

    Required: ``id``, ``layer`` (``L0``–``L4``), ``kind``. Optional declaration
    inputs are normalized before Profile Resolve consumes the immutable
    ``PluginDefinition`` cached on the carrier.
    """

    def _wrap(fn: PluginSetupFn) -> CordisPlugin:
        resolved_layer, resolved_kind = resolve_layer_kind(layer=layer, kind=kind)
        config_cls = Config or config_from_annotations(fn)
        provide_keys = normalize_keys(provides)
        require_keys = normalize_keys(requires)
        implementation_names = normalize_implements(implements)
        effect_set = normalize_effects(effects)
        suite = test_suite or ""
        desc = description or ""
        functional_group_value = resolve_functional_group(functional_group)
        relation_tuple = normalize_relations(relations)
        contributes_tuple = normalize_contributes(contributes)

        merged_meta: dict[str, object] = dict(meta) if meta else {}
        merged_meta.update(
            {
                "id": id,
                "provides": list(provide_keys),
                "requires": list(require_keys),
                "implements": list(implementation_names),
                "layer": resolved_layer,
                "kind": resolved_kind.value,
                "effects": sorted(effect.value for effect in effect_set),
                "test_suite": suite,
                "description": desc,
            }
        )
        if functional_group_value is not None:
            merged_meta["functional_group"] = functional_group_value.value
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
                Config=config_cls,
                setup=fn,
                spec=spec
                or native_spec_from_declaration(
                    plugin_id=id,
                    config_cls=config_cls,
                    provides=provide_keys,
                    requires=require_keys,
                    implements=implementation_names,
                    layer=resolved_layer,
                    kind=resolved_kind,
                    effects=effect_set,
                    test_suite=suite,
                    functional_group=functional_group_value,
                    module=fn.__module__,
                    contributes=contributes_tuple,
                ),
                description=desc,
                relations=relation_tuple,
                functional_group=functional_group_value,
                logic_address=logic_address,
                contract=contract,
            ),
        )
        return cordis_plugin

    if setup is not None and callable(setup):
        return _wrap(setup)
    return _wrap


def definition_from_plugin(
    plugin_obj: CordisPlugin | PluginCarrier, *, module: str | None = None
) -> PluginDefinition:
    """Extract ``PluginDefinition`` from a Cordis Plugin or decorated module.setup."""
    cached = getattr(plugin_obj, "_lca_definition", None)
    if isinstance(cached, PluginDefinition):
        return cached.with_module(module) if module and cached.module != module else cached

    raw_meta: object = getattr(plugin_obj, "meta", {})
    meta: PluginMetadata = (
        {key: value for key, value in raw_meta.items() if isinstance(key, str)}
        if isinstance(raw_meta, Mapping)
        else {}
    )
    plugin_id = str(meta.get("id") or getattr(plugin_obj, "name", None) or "")
    if not plugin_id:
        raise ValueError("plugin has no id")
    kind_raw = meta.get("kind", "primitive")
    if not isinstance(kind_raw, (PluginKind, str)):
        raise ValueError(f"plugin {plugin_id!r} has invalid kind={kind_raw!r}")
    effects_raw = meta.get("effects") or ["none"]
    if not isinstance(effects_raw, (EffectClass, str, list, tuple)):
        raise ValueError(f"plugin {plugin_id!r} has invalid effects metadata")
    layer_raw = str(meta.get("layer") or "L1")
    if layer_raw not in _LAYER_VALUES:
        raise ValueError(f"plugin {plugin_id!r} has invalid layer={layer_raw!r}")
    functional_group_raw = meta.get("functional_group")
    if functional_group_raw is not None and not isinstance(
        functional_group_raw, (FunctionalGroup, str)
    ):
        raise ValueError(f"plugin {plugin_id!r} has invalid functional_group metadata")
    raw_setup: object = getattr(plugin_obj, "setup", plugin_obj)
    if not callable(raw_setup):
        raise ValueError(f"plugin {plugin_id!r} has no callable setup")
    raw_config: object = getattr(plugin_obj, "Config", None)
    config_cls = (
        raw_config if isinstance(raw_config, type) and issubclass(raw_config, BaseModel) else None
    )

    def _meta_strings(field: str, fallback: object = None) -> tuple[str, ...]:
        value = meta.get(field) or fallback
        return (
            tuple(item for item in value if isinstance(item, str))
            if isinstance(value, (list, tuple))
            else ()
        )

    provides = _meta_strings("provides")
    requires = _meta_strings("requires", getattr(plugin_obj, "inject", None))
    implements = _meta_strings("implements")
    functional_group = resolve_functional_group(functional_group_raw)
    kind = PluginKind(kind_raw)
    effects = normalize_effects(effects_raw)
    test_suite = str(meta.get("test_suite") or "")
    setup_fn = cast("PluginSetupFn", raw_setup)
    module_name = module or getattr(raw_setup, "__module__", "__main__")
    if not isinstance(module_name, str):
        module_name = "__main__"
    return PluginDefinition(
        Config=config_cls,
        setup=setup_fn,
        spec=native_spec_from_declaration(
            plugin_id=plugin_id,
            config_cls=config_cls,
            provides=provides,
            requires=requires,
            implements=implements,
            layer=layer_raw,
            kind=kind,
            effects=effects,
            test_suite=test_suite,
            functional_group=functional_group,
            module=module_name,
        ),
        description=str(meta.get("description") or ""),
        functional_group=functional_group,
    )
