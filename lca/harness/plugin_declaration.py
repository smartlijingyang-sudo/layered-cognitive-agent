"""插件声明的 Cordis 载体适配器。

``@plugin`` 是开放装饰器参数进入不可变 ``PluginDefinition`` 的唯一接缝。输入字段
规范化、类型化 ``PluginSpec`` 构造委派给 ``plugin_spec_projection``；本模块同时
承载 Cordis 载体创建、已装饰插件的 Manifest 提取以及输入字段规范化规则。

**ADR-0110 PR-A：** ``@plugin(...)`` 当前接收三入口
``functional_group=`` / ``logic_address=`` / ``contract=`` 表达同一概念；
本模块通过 ``compose_plugin_contract`` 归一到单一 ``PluginContract``，
并把 canonical snapshot 写入 ``meta["contract_snapshot"]``。其中
``functional_group=`` 与 ``logic_address=`` 是 **alias 键**（D3），
新代码建议直接传 ``contract=PluginContract(...)``。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING, Any, Protocol, cast

from cordis.plugin import Plugin as CordisPlugin
from cordis.plugin import plugin as _cordis_plugin
from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.capabilities import Capability, cap_key
from lca.contracts.harness.composition.plugin_contract import (
    PluginContract,
    compose_plugin_contract,
    contract_snapshot_for_meta,
)
from lca.contracts.protocols.composition.logic_address import LogicAddress
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
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
    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        PhaseContribution,
        PluginSpec,
    )


def _resolve_plugin_contract(
    canonical_contract: PluginContract,
) -> LogicAddress | None:
    """Synthesize the legacy ``LogicAddress`` view from the canonical contract.

    ADR-0110 D3 promises a deprecation window where readers using
    ``definition.logic_address`` keep working even after the author migrates
    to ``contract=PluginContract(...)``. This shim folds the canonical 5
    sections back into the 6-dim flat struct that pre-ADR-0110 readers
    expect; PR-D (six months out) deletes this and the corresponding field.
    """
    has_content = (
        canonical_contract.architecture.group is not None
        or bool(canonical_contract.architecture.control_slots)
        or bool(canonical_contract.lifecycle.allowed_scopes)
        or bool(canonical_contract.authority.grants)
        or bool(canonical_contract.observability.descriptors)
        or bool(canonical_contract.identity.version)
    )
    if not has_content:
        return None
    return LogicAddress(
        functional_group=canonical_contract.architecture.group,
        control_slot=(
            canonical_contract.architecture.control_slots[0]
            if canonical_contract.architecture.control_slots
            else None
        ),
        scope=(
            canonical_contract.lifecycle.allowed_scopes[0]
            if canonical_contract.lifecycle.allowed_scopes
            else None
        ),
        authority=tuple(canonical_contract.authority.grants),
        evidence=tuple(canonical_contract.observability.descriptors),
        revision=canonical_contract.identity.version or None,
    )


__all__ = ["PluginCarrier", "definition_from_plugin", "plugin"]


class PluginCarrier(Protocol):
    """Profile Resolve 读取 Manifest 时所需的最小 Cordis 载体形状。"""

    setup: PluginSetupFn[Any]
    Config: type[BaseModel] | None
    name: str | None
    inject: Sequence[str] | None
    meta: PluginMetadata


def plugin(
    setup: PluginSetupFn[Any] | None = None,
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
    ownership: OwnershipDeclaration | None = None,
    marker_class: type | None = None,
) -> CordisPlugin | Callable[[PluginSetupFn[Any]], CordisPlugin]:
    """Declare a plugin Manifest and adapt it to the Cordis carrier.

    Required: ``id``, ``layer`` (``L0``–``L4``), ``kind``. Optional declaration
    inputs are normalized before Profile Resolve consumes the immutable
    ``PluginDefinition`` cached on the carrier.

    ``marker_class``（PR-5）：当插件作为事件 publisher / subscriber / sink
    在 yaml 鉴权矩阵中以 id 形式被引用时，记录"代表本插件的 marker 类"。
    ``EventRegistry`` 装载时按 id → marker class 解析（详见
    ``lca_kernel.events.registry.EventRegistry.register_marker``）；
    缺省 = 无 marker（不参与事件 yaml id 鉴权）。
    """

    def _wrap(fn: PluginSetupFn[Any]) -> CordisPlugin:
        resolved_layer, resolved_kind = _resolve_layer_kind(layer=layer, kind=kind)
        config_cls = Config or _config_from_annotations(fn)
        provide_keys = _normalize_keys(provides)
        require_keys = _normalize_keys(requires)
        implementation_names = _normalize_implements(implements)
        effect_set = _normalize_effects(effects)
        suite = test_suite or ""
        desc = description or ""
        functional_group_value = _resolve_functional_group(functional_group)
        relation_tuple = _normalize_relations(relations)
        contributes_tuple = _normalize_contributes(contributes)
        marker = _normalize_marker_class(marker_class, plugin_id=id)

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
                "marker_class": f"{marker.__module__}.{marker.__qualname__}" if marker is not None else None,
            }
        )
        if functional_group_value is not None:
            merged_meta["functional_group"] = functional_group_value.value

        # ADR-0110 PR-A: unify the 3 declaration keys into one canonical contract.
        # ``contract=`` wins over ``logic_address=`` and ``functional_group=``;
        # the resulting PluginContract is stored on PluginDefinition and as
        # ``contract_snapshot`` on the cordis meta for downstream readers.
        canonical_contract = compose_plugin_contract(
            functional_group=functional_group_value,
            logic_address=logic_address,
            contract=contract,
        )
        merged_meta["contract_snapshot"] = contract_snapshot_for_meta(canonical_contract)

        # ADR-0110 D3 back-compat shim: when the author migrates to
        # ``contract=`` we still synthesize ``logic_address`` so pre-ADR-0110
        # readers (e.g. ``definition.logic_address``) keep working during the
        # deprecation window. PR-D removes this and the corresponding field.
        legacy_logic_address = logic_address or _resolve_plugin_contract(canonical_contract)
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
            PluginDefinition[Any](
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
                    ownership=ownership,
                ),
                description=desc,
                relations=relation_tuple,
                functional_group=functional_group_value,
                logic_address=legacy_logic_address,
                contract=canonical_contract,
                ownership=ownership,
                marker_class=marker,
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
    functional_group = _resolve_functional_group(functional_group_raw)
    kind = PluginKind(kind_raw)
    effects = _normalize_effects(effects_raw)
    test_suite = str(meta.get("test_suite") or "")
    setup_fn = cast("PluginSetupFn[Any]", raw_setup)
    module_name = module or getattr(raw_setup, "__module__", "__main__")
    if not isinstance(module_name, str):
        module_name = "__main__"
    marker_raw = meta.get("marker_class")
    marker = _normalize_marker_class(
        _import_marker(marker_raw) if isinstance(marker_raw, str) else None,
        plugin_id=plugin_id,
    )
    return PluginDefinition[Any](
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
        marker_class=marker,
    )


# ---------------------------------------------------------------------------
# Input-field normalization helpers (folded in from plugin_declaration_normalization).
# Private because they are internal plumbing for ``@plugin`` /
# ``definition_from_plugin``; public callers go through
# ``lca.harness.plugin_api``. Renamed with underscore prefix to mark them as
# module-private.
# ---------------------------------------------------------------------------


def _config_from_annotations(fn: Callable[..., object]) -> type[BaseModel] | None:
    """Pick Pydantic Config from ``config: Config`` annotation when Config= omitted."""
    try:
        import typing

        resolved = typing.get_type_hints(fn)
        annotated = resolved.get("config")
        if isinstance(annotated, type) and issubclass(annotated, BaseModel):
            return annotated
    except (NameError, TypeError, ValueError):
        return None
    return None


def _normalize_marker_class(value: type | None, *, plugin_id: str) -> type | None:
    """Validate ``@plugin(marker_class=...)`` 形参。

    marker_class 必须是 type；非 type（string 等）→ TypeError。
    返回 class 对象（直接复用，不做额外包装）。
    """
    if value is None:
        return None
    if not isinstance(value, type):
        raise TypeError(
            f"@plugin marker_class ({plugin_id!r}) must be type, got {type(value).__name__}"
        )
    return value


def _import_marker(path: str) -> type:
    """从 ``module.qualname`` 字符串导入 marker class。

    仅在 ``@plugin(marker_class=...)`` 被省略、改走 meta["marker_class"]
    序列化字符串路径时调用；用于 ``definition_from_plugin`` 回放。
    """
    from importlib import import_module

    module_path, _, class_name = path.rpartition(".")
    if not module_path:
        raise ValueError(f"invalid marker_class path: {path!r}")
    module = import_module(module_path)
    cls = getattr(module, class_name, None)
    if cls is None or not isinstance(cls, type):
        raise ValueError(f"marker_class {path!r} not importable as type")
    return cls


def _normalize_keys(values: Sequence[Capability[object] | str] | None) -> tuple[str, ...]:
    """Normalize typed and textual capability keys at the declaration seam."""
    if not values:
        return ()
    return tuple(cap_key(value) for value in values)


def _resolve_functional_group(value: FunctionalGroup | str | None) -> FunctionalGroup | None:
    """Resolve FunctionalGroup from str / enum / None; returns enum or None."""
    if value is None:
        return None
    from lca.contracts.atoms.functional_group import parse_functional_group

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


def _normalize_declaration_entries(
    value: Sequence[Mapping[str, object]] | None,
    *,
    field: str,
) -> tuple[Mapping[str, object], ...]:
    """Reject malformed open declaration entries before plan compilation."""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"@plugin {field} must be list/tuple, got {type(value).__name__}")

    normalized: list[Mapping[str, object]] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise TypeError(f"@plugin {field}[{index}] must be mapping, got {type(item).__name__}")
        if any(not isinstance(key, str) for key in item):
            raise TypeError(f"@plugin {field}[{index}] keys must be str")
        normalized.append(dict(item))
    return tuple(normalized)


def _normalize_relations(
    value: Sequence[RawRelationEntry] | None,
) -> tuple[RawRelationEntry, ...]:
    """Normalize open relation declarations without assigning plan semantics."""
    return _normalize_declaration_entries(value, field="relations")


def _normalize_contributes(value: Sequence[object] | None) -> tuple[PhaseContribution, ...]:
    """Normalize ``contributes`` into typed phase entries."""
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"@plugin contributes must be list/tuple, got {type(value).__name__}")
    from lca.contracts.protocols.declarative.declarative_phase_graph import (
        ContributionRole,
        PhaseContribution,
        SemanticPhase,
    )

    normalized: list[PhaseContribution] = []
    for index, item in enumerate(value):
        if isinstance(item, PhaseContribution):
            normalized.append(item)
            continue
        if isinstance(item, Mapping):
            phase_value = item.get("phase")
            role_value = item.get("role")
            if not isinstance(phase_value, SemanticPhase):
                raise TypeError(
                    "@plugin contributes["
                    f"{index}].phase must be SemanticPhase, got {type(phase_value).__name__}"
                )
            if not isinstance(role_value, ContributionRole):
                raise TypeError(
                    "@plugin contributes["
                    f"{index}].role must be ContributionRole, got {type(role_value).__name__}"
                )
            executor = item.get("executor")
            output = item.get("output")
            order = item.get("order", index)
            aggregation = item.get("aggregation")
            if not isinstance(executor, str) or not executor:
                raise TypeError(f"@plugin contributes[{index}].executor must be non-empty str")
            if not isinstance(output, str) or not output:
                raise TypeError(f"@plugin contributes[{index}].output must be non-empty str")
            if not isinstance(order, int) or isinstance(order, bool):
                raise TypeError(f"@plugin contributes[{index}].order must be int")
            if aggregation is not None and not isinstance(aggregation, str):
                raise TypeError(f"@plugin contributes[{index}].aggregation must be str or None")
            normalized.append(
                PhaseContribution(
                    phase=phase_value,
                    role=role_value,
                    executor=executor,
                    output=output,
                    order=order,
                    aggregation=aggregation,
                )
            )
            continue
        raise TypeError(
            "@plugin contributes["
            f"{index}] must be PhaseContribution or mapping, got {type(item).__name__}"
        )
    return tuple(normalized)


def _normalize_implements(values: object) -> tuple[str, ...]:
    """Normalize class, Protocol alias, or string implementation declarations."""
    if not values:
        return ()
    if isinstance(values, (str, type)):
        items: Sequence[object] = (values,)
    elif isinstance(values, Sequence):
        items = values
    else:
        items = (values,)

    out: list[str] = []
    for value in items:
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, type):
            out.append(value.__name__)
        else:
            out.append(str(value))
    return tuple(out)


def _normalize_effects(
    effects: EffectClass | str | Sequence[EffectClass | str] | None,
) -> frozenset[EffectClass]:
    """Normalize effect declarations while rejecting no valid effect values."""
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
    """Validate and normalize the canonical layer and kind declarations."""
    if layer is None:
        raise ValueError("@plugin requires layer= (one of L0–L4)")
    if layer not in _LAYER_VALUES:
        raise ValueError(f"unknown layer={layer!r}; expected L0–L4 (no legacy taxonomy)")
    if kind is None:
        raise ValueError("kind= is required when layer is L0–L4")
    return layer, PluginKind(kind) if not isinstance(kind, PluginKind) else kind
