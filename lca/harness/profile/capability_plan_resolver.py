"""CapabilityPlan 投影 resolver（ADR-0068 §一 + ADR-0074 PR-2.5）。

职责：

1. 把已解析 profile（``ResolvedProfile``）投影为不可变 CapabilityPlan
2. 从 ``ResolvedProfile.dag_edges`` 派生 5 老关系
   （provides / requires / contributes_to / reads_fact / emits_fact）
3. 从每个 plugin 的 ``meta.relations:`` 段读取用户声明的 11 关系
   （含 6 新关系 governs / executes / delegates / projects / revises /
   evaluates）
4. 校验每条关系引用：source / target 必须指向某 plugin id 或
   capability key；非法引用 → ``CapabilityPlanResolveError``
5. 计算 ``plan_hash`` 用于 PR-3 / PR-6 plan_ref 绑定

PR-2.5 阶段：runtime 不消费 CapabilityPlan（PR-3 PlanCompiler 才
读取并编译为 CompiledRunPlan）；本 resolver 是纯数据面。

全局不变量（ADR-0069 §三）：

1. authority 仅可向子 scope 衰减
2. world effect 仅可经 G7 的 CommandEnvelope 穿出
3. facts 仅可追加，state 仅可由 Reducer 投影
4. profile / artifact 的变更只能形成 immutable PlanRevision
5. projection 不得回写 facts 或 business state
6. plugin 不得通过 live Context / global helper 绕开这些关系
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from lca.contracts.atoms.relation import (
    Relation,
)
from lca.contracts.protocols.capability_plan import (
    CapabilityPlan,
    ProviderBinding,
    provider_bindings_from_iter,
)
from lca.contracts.protocols.relation import (
    TypedRelation,
    typed_relations_from_iter,
)
from lca.harness.profile.resolve import ResolvedPlugin, ResolvedProfile


class CapabilityPlanResolveError(ValueError):
    """CapabilityPlan 投影失败（relation 引用非法 / slot / aggregation 不合法）。"""


@dataclass(frozen=True, slots=True)
class CapabilityPlanOptions:
    """投影选项。

    - ``include_disabled`` — 是否包含 ``disabled: true`` 的插件
    - ``validate_targets`` — 是否校验 relation.source / .target 引用
      必须存在于 plugin id 或 capability key 集合（默认 True）
    """

    include_disabled: bool = False
    validate_targets: bool = True


def project_capability_plan(
    resolved: ResolvedProfile,
    *,
    options: CapabilityPlanOptions | None = None,
) -> CapabilityPlan:
    """从 ``ResolvedProfile`` 投影 CapabilityPlan。

    步骤：

    1. 遍历每个 plugin，构造 ``ProviderBinding``（capability key →
       owner plugin + effect class）
    2. 从每个 plugin 的 ``meta.relations:`` 段读取用户声明的 typed 关系
    3. 校验每条 relation 引用（source / target 必须存在）
    4. 计算 ``plan_hash``（PR-3 / PR-6 引用）

    任何 plugin **未**声明 ``relations:`` 段 → 不产生新关系；只有
    ResolvedProfile.dag_edges 派生的 provides / requires 关系。
    """
    opts = options or CapabilityPlanOptions()
    plugin_ids = {p.id for p in resolved.plugins if (opts.include_disabled or not p.disabled)}
    capability_keys: set[str] = set()
    for plugin in resolved.plugins:
        if plugin.disabled and not opts.include_disabled:
            continue
        capability_keys.update(plugin.definition.provides)

    bindings = _build_bindings(resolved, opts)
    relations = _build_relations(resolved, plugin_ids, capability_keys, opts)

    return CapabilityPlan(
        profile_path=resolved.profile_path,
        provider_bindings=bindings,
        relations=relations,
        revision="v1",
    )


# ── Internals ────────────────────────────────────────────────────────


def _build_bindings(
    resolved: ResolvedProfile,
    opts: CapabilityPlanOptions,
) -> tuple[ProviderBinding, ...]:
    """从每个 plugin 的 ``provides`` 字段构造 ``ProviderBinding``。

    与 ``ResolvedProfile.dag_edges`` 同源；本函数镜像到 typed
    ProviderBinding，加入 effect_class / revision 字段。
    """
    raw: list[dict[str, Any]] = []
    for plugin in resolved.plugins:
        if plugin.disabled and not opts.include_disabled:
            continue
        effect_classes = sorted(e.value for e in plugin.definition.effects) or ["none"]
        effect_class = effect_classes[0]  # 简化：取第一个 effect class
        for capability in plugin.definition.provides:
            raw.append(
                {
                    "capability": capability,
                    "owner_plugin": plugin.id,
                    "effect_class": effect_class,
                    "revision": "",
                }
            )
    return provider_bindings_from_iter(raw)


def _build_relations(
    resolved: ResolvedProfile,
    plugin_ids: set[str],
    capability_keys: set[str],
    opts: CapabilityPlanOptions,
) -> tuple[TypedRelation, ...]:
    """从 plugin ``meta.relations:`` 段读取 typed 关系 + 校验。

    meta 段读取与 PR-1/PR-2 控制字段相同的 fallback 模式：typed
    ``definition.relations`` 字段（PR-2.5 暂未引入，扩展点保留）
    → ``setup.meta['relations']`` → 空列表。
    """
    raw_relations: list[dict[str, Any]] = []
    for plugin in resolved.plugins:
        if plugin.disabled and not opts.include_disabled:
            continue
        for raw in _extract_relations_from_plugin(plugin):
            # 默认 source = plugin.id（若 user 未指定）
            if "source" not in raw:
                raw["source"] = plugin.id
            raw_relations.append(raw)
    relations = typed_relations_from_iter(raw_relations)
    if opts.validate_targets:
        _validate_relation_targets(relations, plugin_ids, capability_keys)
    return relations


def _extract_relations_from_plugin(plugin: ResolvedPlugin) -> list[dict[str, Any]]:
    """从 plugin meta 提取 relations 段。

    PR-2.5 阶段：typed ``PluginDefinition.relations`` 字段未引入（PR-3
    引入）；本函数读 ``setup.meta['relations']``（与 control 字段
    同源）。
    """
    setup_obj = plugin.definition.setup
    raw_meta = getattr(setup_obj, "meta", None)
    meta: dict[str, Any] = {}
    if isinstance(raw_meta, Mapping):
        meta.update(raw_meta)
    module_meta = getattr(setup_obj, "plugin_meta", None)
    if isinstance(module_meta, Mapping):
        meta.update(module_meta)
    if "relations" not in meta:
        return []
    raw = meta["relations"]
    if not isinstance(raw, (list, tuple)):
        raise CapabilityPlanResolveError(
            f"plugin {plugin.id}: meta.relations must be list/tuple, got {type(raw).__name__}"
        )
    out: list[dict[str, Any]] = []
    for idx, item in enumerate(raw):
        if not isinstance(item, Mapping):
            raise CapabilityPlanResolveError(
                f"plugin {plugin.id}: relations[{idx}] must be mapping, got {type(item).__name__}"
            )
        out.append(dict(item))
    return out


def _validate_relation_targets(
    relations: tuple[TypedRelation, ...],
    plugin_ids: set[str],
    capability_keys: set[str],
) -> None:
    """校验每条 relation.source / .target 必须指向已知 plugin / capability。

    source 必填（默认 = plugin.id）；target 可指 plugin / capability / 自由
    字符串（一些关系 like evaluates 目标可能是 fact descriptor）。本
    校验保留 source 必填 + target 必须 ∈ known set 或以 `descriptor:`
    / `fact:` 前缀开头（journal catalog 引用）。
    """
    for rel in relations:
        if rel.source not in plugin_ids:
            raise CapabilityPlanResolveError(
                f"relation.source={rel.source!r} (kind={rel.kind.value}) not in known plugin ids"
            )
        # target 校验：plugin id / capability key / descriptor 引用
        if rel.target in plugin_ids:
            continue
        if rel.target in capability_keys:
            continue
        if rel.target.startswith(("descriptor:", "fact:", "journal.")):
            continue
        # relation.kind 提示：emits_fact / reads_fact 必是 fact descriptor
        if rel.kind in (Relation.READS_FACT, Relation.EMITS_FACT):
            # reads_fact / emits_fact 的 target 必是 fact descriptor 风格
            raise CapabilityPlanResolveError(
                f"relation[{rel.source} -> {rel.target}] kind="
                f"{rel.kind.value}: target must be fact descriptor "
                f"(e.g. 'fact:policy.gate.denied' or 'journal.<descriptor>')"
            )
        raise CapabilityPlanResolveError(
            f"relation.source={rel.source!r} -> target={rel.target!r} "
            f"(kind={rel.kind.value}): target must be a known plugin id, "
            f"capability key, or descriptor reference "
            f"(prefix 'descriptor:'/'fact:'/'journal.')"
        )


__all__ = [
    "CapabilityPlanOptions",
    "CapabilityPlanResolveError",
    "project_capability_plan",
]
