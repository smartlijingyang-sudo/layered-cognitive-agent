"""ControlPlan 投影 resolver（ADR-0066 §六 / ADR-0074 PR-1）。

职责：

1. 把已解析 profile（``ResolvedProfile``）投影为不可变 ControlPlan
2. 校验每条 ControlEntry 的 slot ∈ ADR-0066 §二 + tracker §19 闭集
3. 同 slot 内按 ``order`` 稳定排序
4. 计算 ``plan_hash`` 用于 PR-3 / PR-6 plan_ref 绑定
5. 不做运行时 activation 求值（那是 PR-3 PlanCompiler 的职责）

PR-1 阶段：插件默认不声明 ``control`` 段，profile 解析后产出
**空** ControlPlan（plan_hash 由 entries 列表 hash 得到；空 entries
hash 仍稳定）。这是 §4 不变量的"不变量 1 — 不扩张到 PR-2 范围"的
具体形态：保持 control 是 opt-in，不静默注入默认投稿。

激活路径：

- 插件 Manifest 通过 ``@plugin(meta={"control": [...]})`` 或 plugin
  ``setup`` 暴露 ``control: list[Mapping]`` 字段声明 control 段（PR-2）
- 本 resolver 从 ``ResolvedPlugin.definition`` 与 plugin meta 读取
  control 段；若未来 PluginDefinition.control 是 typed 字段，则
  ``_extract_control_meta`` 是唯一切换点

严格保持"决议 = 观察"：本模块**不修改** ResolvedProfile 或 plugin
definition；只是从已有数据派生 ControlPlan。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot, parse_slot
from lca.contracts.protocols.control_plan import (
    SLOT_DEFAULT_AGGREGATION,
    SLOT_DEFAULT_FAILURE,
    Activation,
    AggregationMode,
    ControlEntry,
    ControlPlan,
    FailureMode,
    always,
    compute_control_plan_hash,
    slot_entries,
)
from lca.harness.profile.resolve import ResolvedPlugin, ResolvedProfile


class ControlPlanResolveError(ValueError):
    """ControlPlan 投影失败（slot / aggregation / failure_mode 不合法）。"""


@dataclass(frozen=True, slots=True)
class ControlPlanOptions:
    """投影选项。

    - ``include_disabled`` — 是否包含 ``disabled: true`` 的插件（默认 False）
    - ``strict_aggregation`` — aggregation 必须 ∈ AggregationMode；非默认覆盖
      是否被允许（默认 True：必须显式声明合法值）
    - ``require_known_effect_class`` — effect_class 是否必须 ∈ 已知 effect
      枚举（默认 False：保守接受未知值，由 PR-7 architecture test 收口）
    """

    include_disabled: bool = False
    strict_aggregation: bool = True
    require_known_effect_class: bool = False


_KNOWN_AGGREGATION_VALUES: frozenset[str] = frozenset(m.value for m in AggregationMode)
_KNOWN_FAILURE_VALUES: frozenset[str] = frozenset(m.value for m in FailureMode)


def project_control_plan(
    resolved: ResolvedProfile,
    *,
    options: ControlPlanOptions | None = None,
) -> ControlPlan:
    """从 ``ResolvedProfile`` 投影 ControlPlan。

    步骤：

    1. 遍历每个 plugin，从其 meta / setup / config 提取 ``control: list``
    2. 每条记录解析为 ``ControlEntry``（严格校验 slot / aggregation /
       failure_mode / activation）
    3. 按 (slot, order, plugin_id) 排序
    4. 建 by_slot 索引
    5. 计算 ``plan_hash``

    任何 plugin **未**声明 control 段 → 不产生 entry。这是 PR-1 阶段
    的目标行为：保留 opt-in 语义。
    """
    opts = options or ControlPlanOptions()
    entries: list[ControlEntry] = []
    for plugin in resolved.plugins:
        if plugin.disabled and not opts.include_disabled:
            continue
        for entry in _extract_entries(plugin):
            entries.append(entry)

    sorted_entries = tuple(sorted(entries, key=lambda e: (e.slot.value, e.order, e.plugin_id)))
    by_slot: dict[ControlSlot, list[ControlEntry]] = {}
    for entry in sorted_entries:
        by_slot.setdefault(entry.slot, []).append(entry)
    frozen_by_slot = {slot: tuple(items) for slot, items in by_slot.items()}

    plan_hash = compute_control_plan_hash(sorted_entries, resolved.profile_path)

    return ControlPlan(
        profile_path=resolved.profile_path,
        entries=sorted_entries,
        by_slot=frozen_by_slot,
        plan_hash=plan_hash,
    )


def explain_control_slot(
    plan: ControlPlan,
    slot: ControlSlot | str,
) -> dict[str, Any]:
    """``lca-ops explain control <slot>`` 输出（PR-3 完善，本 PR-1 提供最小版）。

    返回字段：

    - ``slot`` — 槽位字符串
    - ``phase`` — C1 阶段归属（``observe`` for cross-cutting）
    - ``default_aggregation`` / ``default_failure_mode`` — 槽位默认
    - ``entries`` — 按 order 排序的 entry 列表（plugin_id / order /
      aggregation / failure_mode / effect_class / source）
    - ``missing`` — 是否无任何 entry
    """
    from lca.contracts.atoms.control_slot import as_phase_label

    s = parse_slot(slot)
    entries = slot_entries(plan, s)
    return {
        "slot": s.value,
        "phase": as_phase_label(s),
        "default_aggregation": SLOT_DEFAULT_AGGREGATION[s].value,
        "default_failure_mode": SLOT_DEFAULT_FAILURE[s].value,
        "missing": not entries,
        "entries": [
            {
                "plugin_id": e.plugin_id,
                "order": e.order,
                "aggregation": (e.aggregation.value if e.aggregation is not None else None),
                "failure_mode": (e.failure_mode.value if e.failure_mode is not None else None),
                "effect_class": e.effect_class,
                "source": e.source,
                "activation": dict(e.activation.predicate),
                "authority": list(e.authority),
                "reads": list(e.reads),
                "emits": list(e.emits),
            }
            for e in entries
        ],
    }


# ── Internals ────────────────────────────────────────────────────────


def _extract_entries(plugin: ResolvedPlugin) -> list[ControlEntry]:
    """从 plugin meta 提取 control 段并解析为 ControlEntry 列表。

    当前 PR-1 阶段：插件 control 字段是 opt-in；本函数返回空列表是合法
    结果。PR-2 引入 ``PluginDefinition.control`` typed 字段后，本函数
    是唯一切换点。
    """
    definition = plugin.definition
    setup_obj = definition.setup
    raw_meta: Mapping[str, Any] | None = getattr(setup_obj, "meta", None)
    # cordis Plugin exposes meta attribute; if not present, fall back to
    # plugin_api plugin() decorator which stores _lca_definition.
    meta: dict[str, Any] = {}
    if isinstance(raw_meta, Mapping):
        meta.update(raw_meta)
    # Some plugin setups expose a module-level ``META`` dict — be tolerant
    # but do not silently invent entries.
    module_meta = getattr(setup_obj, "plugin_meta", None)
    if isinstance(module_meta, Mapping):
        meta.update(module_meta)
    if "control" not in meta:
        return []
    return _parse_control_list(plugin, meta["control"])


def _parse_control_list(
    plugin: ResolvedPlugin,
    raw: Any,
) -> list[ControlEntry]:
    if not isinstance(raw, (list, tuple)):
        raise ControlPlanResolveError(
            f"plugin {plugin.id}: control must be list, got {type(raw).__name__}"
        )
    entries: list[ControlEntry] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise ControlPlanResolveError(f"plugin {plugin.id}: control[{idx}] must be mapping")
        entries.append(_parse_control_entry(plugin, item, idx))
    return entries


def _parse_control_entry(
    plugin: ResolvedPlugin,
    raw: Mapping[str, Any],
    idx: int,
) -> ControlEntry:
    if "slot" not in raw:
        raise ControlPlanResolveError(f"plugin {plugin.id}: control[{idx}] missing 'slot'")
    try:
        slot = parse_slot(raw["slot"])
    except (ValueError, TypeError) as exc:
        raise ControlPlanResolveError(
            f"plugin {plugin.id}: control[{idx}].slot invalid: {exc}"
        ) from exc

    aggregation = _parse_enum(
        raw.get("aggregation"),
        AggregationMode,
        "aggregation",
        plugin=plugin,
        idx=idx,
        required=False,
    )
    failure_mode = _parse_enum(
        raw.get("failure_mode"),
        FailureMode,
        "failure_mode",
        plugin=plugin,
        idx=idx,
        required=False,
    )

    activation = _parse_activation(plugin, idx, raw.get("activation"))

    return ControlEntry(
        plugin_id=plugin.id,
        slot=slot,
        activation=activation,
        order=int(raw.get("order", 100)),
        aggregation=aggregation,
        failure_mode=failure_mode,
        authority=tuple(str(a) for a in raw.get("authority", ()) or ()),
        reads=tuple(str(r) for r in raw.get("reads", ()) or ()),
        emits=tuple(str(e) for e in raw.get("emits", ()) or ()),
        effect_class=str(raw.get("effect_class", "none")),
        source=plugin.source,
    )


def _parse_enum(
    value: Any,
    enum_type: Any,
    field_name: str,
    *,
    plugin: ResolvedPlugin,
    idx: int,
    required: bool,
) -> Any:
    if value is None:
        if required:
            raise ControlPlanResolveError(
                f"plugin {plugin.id}: control[{idx}].{field_name} required"
            )
        return None
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            constructed = enum_type(value)
        except ValueError as exc:
            allowed = [str(member.value) for member in enum_type]
            raise ControlPlanResolveError(
                f"plugin {plugin.id}: control[{idx}].{field_name}={value!r} "
                f"unknown (allowed: {allowed})"
            ) from exc
        return constructed
    raise ControlPlanResolveError(
        f"plugin {plugin.id}: control[{idx}].{field_name} must be str "
        f"or {enum_type.__name__}, got {type(value).__name__}"
    )


def _parse_activation(plugin: ResolvedPlugin, idx: int, raw: Any) -> Activation:
    if raw is None:
        return always()
    if isinstance(raw, Activation):
        return raw
    return Activation(raw)


__all__ = [
    "ControlPlanOptions",
    "ControlPlanResolveError",
    "explain_control_slot",
    "project_control_plan",
]
