"""``@plugin`` 开放声明输入的规范化规则。

此模块不创建 Cordis 载体也不读取运行时 Context；它将可变的装饰器参数变为稳定、
可验证的 Manifest 值，供声明适配器一次性消费。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel

from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.capabilities import Capability, cap_key
from lca.harness.plugin_manifest import _LAYER_VALUES, EffectClass, PluginKind, RawRelationEntry

if TYPE_CHECKING:
    from lca.contracts.protocols.declarative.declarative_phase_graph import PhaseContribution


def config_from_annotations(fn: Callable[..., object]) -> type[BaseModel] | None:
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


def normalize_keys(values: Sequence[Capability[object] | str] | None) -> tuple[str, ...]:
    """Normalize typed and textual capability keys at the declaration seam."""
    if not values:
        return ()
    return tuple(cap_key(value) for value in values)


def resolve_functional_group(value: FunctionalGroup | str | None) -> FunctionalGroup | None:
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


def normalize_declaration_entries(
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


def normalize_relations(
    value: Sequence[RawRelationEntry] | None,
) -> tuple[RawRelationEntry, ...]:
    """Normalize open relation declarations without assigning plan semantics."""
    return normalize_declaration_entries(value, field="relations")


def normalize_contributes(value: Sequence[object] | None) -> tuple[PhaseContribution, ...]:
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


def normalize_implements(values: object) -> tuple[str, ...]:
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


def normalize_effects(
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


def resolve_layer_kind(
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
