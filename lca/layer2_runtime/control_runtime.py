"""CompiledRunPlan 控制面的运行时解释器。

``ControlPlan`` 是不可变声明。本模块在受限 Activation DSL 上选择有效投稿，
再用槽位定义的单调规则将投稿 verdict 统一聚合。运行循环只经
``evaluate_control`` 消费控制面；它不会读取 slot 字符串或分散的 policy 条件。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.models.core.state import AgentState
from lca.contracts.protocols.control_plan import (
    SLOT_DEFAULT_AGGREGATION,
    Activation,
    AggregationMode,
    ControlEntry,
    ControlPlan,
    slot_entries,
)


class ControlVerdictKind(str, Enum):
    """Closed verdict vocabulary shared by the eleven control slots."""

    ALLOW = "allow"
    DENY = "deny"
    EXHAUSTED = "exhausted"
    STOP = "stop"
    ASK_HUMAN = "ask_human"
    REWRITE = "rewrite"


@dataclass(frozen=True, slots=True)
class ControlVerdict:
    """One active plugin's typed contribution to a control-slot decision."""

    plugin_id: str
    kind: ControlVerdictKind
    detail: str = ""


@dataclass(frozen=True, slots=True)
class ControlSelection:
    """A slot's ordered, activation-filtered plan contributions."""

    slot: ControlSlot
    entries: tuple[ControlEntry, ...]
    facts: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ControlEvaluation:
    """Deterministic aggregation result for an evaluated control slot.

    ``effective`` is ``None`` for ``NO_AGGREGATE`` slots because those slots
    retain every independent contribution for observers or dispatchers. All
    other modes produce exactly one typed verdict.
    """

    selection: ControlSelection
    aggregation: AggregationMode
    verdicts: tuple[ControlVerdict, ...]
    effective: ControlVerdict | None

    @property
    def blocking_verdict(self) -> ControlVerdict | None:
        """Return the first phase-blocking verdict, including no-aggregate slots."""
        blocking = {
            ControlVerdictKind.DENY,
            ControlVerdictKind.EXHAUSTED,
            ControlVerdictKind.STOP,
            ControlVerdictKind.ASK_HUMAN,
        }
        if self.effective is not None and self.effective.kind in blocking:
            return self.effective
        return next((verdict for verdict in self.verdicts if verdict.kind in blocking), None)

    @property
    def is_blocking(self) -> bool:
        """Whether any independent or aggregated verdict blocks this phase."""
        return self.blocking_verdict is not None


def select_control_entries(
    plan: ControlPlan,
    slot: ControlSlot,
    state: AgentState,
    *,
    facts: Mapping[str, Any] | None = None,
) -> ControlSelection:
    """Return activation-matching contributions in stable plan order."""
    merged_facts = control_facts(state, extra=facts)
    selected = tuple(
        entry
        for entry in slot_entries(plan, slot)
        if evaluate_activation(entry.activation, merged_facts)
    )
    return ControlSelection(slot=slot, entries=selected, facts=merged_facts)


def evaluate_control(
    plan: ControlPlan,
    slot: ControlSlot,
    state: AgentState,
    *,
    facts: Mapping[str, Any] | None = None,
    verdicts: Sequence[ControlVerdict] = (),
) -> ControlEvaluation:
    """Select a slot's active entries and aggregate their typed verdicts.

    Omitting a plugin verdict means the contribution is the constitutional
    no-op ``allow``. Callers that execute concrete policies pass their actual
    verdicts keyed by ``plugin_id``; unknown or inactive contributors fail
    closed with ``ValueError`` instead of silently affecting another slot.
    """
    selection = select_control_entries(plan, slot, state, facts=facts)
    return aggregate_control_verdicts(selection, verdicts)


def aggregate_control_verdicts(
    selection: ControlSelection,
    verdicts: Sequence[ControlVerdict] = (),
) -> ControlEvaluation:
    """Aggregate verdicts according to the resolved slot rule.

    The four monotonic rules are deliberately centralized here:
    ``deny_on_any_deny``, ``deny_on_exhausted``, ``stop_on_any_stop`` and
    ``decision_priority``. A plan with conflicting per-entry aggregation
    overrides is invalid because it would make one slot non-deterministic.
    """
    aggregation = _resolved_aggregation(selection)
    resolved_verdicts = _resolve_verdicts(selection, verdicts)
    effective = _aggregate(aggregation, resolved_verdicts)
    return ControlEvaluation(
        selection=selection,
        aggregation=aggregation,
        verdicts=resolved_verdicts,
        effective=effective,
    )


def _resolved_aggregation(selection: ControlSelection) -> AggregationMode:
    modes = {
        entry.aggregation or SLOT_DEFAULT_AGGREGATION[selection.slot] for entry in selection.entries
    }
    if not modes:
        return SLOT_DEFAULT_AGGREGATION[selection.slot]
    if len(modes) != 1:
        values = ", ".join(sorted(mode.value for mode in modes))
        raise ValueError(
            f"control slot {selection.slot.value} has conflicting aggregation modes: {values}"
        )
    return next(iter(modes))


def _resolve_verdicts(
    selection: ControlSelection,
    supplied: Sequence[ControlVerdict],
) -> tuple[ControlVerdict, ...]:
    by_plugin: dict[str, ControlVerdict] = {}
    for verdict in supplied:
        if verdict.plugin_id in by_plugin:
            raise ValueError(f"duplicate control verdict for plugin {verdict.plugin_id!r}")
        by_plugin[verdict.plugin_id] = verdict

    active_plugins = {entry.plugin_id for entry in selection.entries}
    unexpected = sorted(set(by_plugin) - active_plugins)
    if unexpected:
        raise ValueError(
            f"control verdicts supplied for inactive or unknown plugins in "
            f"{selection.slot.value}: {unexpected}"
        )

    return tuple(
        by_plugin.get(entry.plugin_id, ControlVerdict(entry.plugin_id, ControlVerdictKind.ALLOW))
        for entry in selection.entries
    )


def _aggregate(
    aggregation: AggregationMode,
    verdicts: tuple[ControlVerdict, ...],
) -> ControlVerdict | None:
    if aggregation is AggregationMode.NO_AGGREGATE:
        return None
    if not verdicts:
        return ControlVerdict(plugin_id="control.default", kind=ControlVerdictKind.ALLOW)

    if aggregation is AggregationMode.DENY_ON_ANY_DENY:
        return _first_matching(verdicts, {ControlVerdictKind.DENY})
    if aggregation is AggregationMode.DENY_ON_EXHAUSTED:
        return _first_matching(verdicts, {ControlVerdictKind.EXHAUSTED, ControlVerdictKind.DENY})
    if aggregation is AggregationMode.STOP_ON_ANY_STOP:
        return _first_matching(verdicts, {ControlVerdictKind.STOP})
    if aggregation is AggregationMode.DECISION_PRIORITY:
        priorities = {
            ControlVerdictKind.ALLOW: 0,
            ControlVerdictKind.REWRITE: 1,
            ControlVerdictKind.ASK_HUMAN: 2,
            ControlVerdictKind.STOP: 3,
        }
        return max(verdicts, key=lambda verdict: priorities.get(verdict.kind, -1))
    raise ValueError(f"unsupported control aggregation mode: {aggregation.value}")


def _first_matching(
    verdicts: tuple[ControlVerdict, ...],
    blocking: set[ControlVerdictKind],
) -> ControlVerdict:
    for verdict in verdicts:
        if verdict.kind in blocking:
            return verdict
    return ControlVerdict(plugin_id="control.default", kind=ControlVerdictKind.ALLOW)


def control_facts(
    state: AgentState,
    *,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the only runtime fact snapshot visible to the Activation DSL."""
    budget = state.budget
    facts: dict[str, Any] = {
        "task": state.task,
        "state.step": state.step,
        "state.status": state.status.value,
        "state.agent_role": state.agent_role,
        "state.wall_clock": budget.max_wall_clock_seconds,
        "state.budget.max_steps": budget.max_steps,
        "state.budget.used_steps": budget.used_steps,
    }
    if extra:
        facts.update(extra)
    return facts


def evaluate_activation(activation: Activation, facts: Mapping[str, Any]) -> bool:
    """Evaluate a resolver-validated Activation DSL against a fact snapshot."""
    return _evaluate_node(activation.predicate, facts)


def _evaluate_node(node: Mapping[str, Any], facts: Mapping[str, Any]) -> bool:
    if "always" in node:
        return True
    if "all" in node:
        return all(_evaluate_node(item, facts) for item in node["all"])
    if "any" in node:
        return any(_evaluate_node(item, facts) for item in node["any"])
    if "not" in node:
        return not _evaluate_node(node["not"], facts)

    value = facts.get(str(node["fact"]))
    if "exists" in node:
        return value is not None
    if "missing" in node:
        return value is None
    if "eq" in node:
        return bool(value == node["eq"])
    if "ne" in node:
        return bool(value != node["ne"])
    if "in" in node:
        return bool(value in node["in"])
    if "not_in" in node:
        return bool(value not in node["not_in"])
    if value is None:
        return False
    if "lt" in node:
        return bool(value < node["lt"])
    if "le" in node:
        return bool(value <= node["le"])
    if "gt" in node:
        return bool(value > node["gt"])
    if "ge" in node:
        return bool(value >= node["ge"])
    raise ValueError(f"unsupported validated activation predicate: {node!r}")


__all__ = [
    "ControlEvaluation",
    "ControlSelection",
    "ControlVerdict",
    "ControlVerdictKind",
    "aggregate_control_verdicts",
    "control_facts",
    "evaluate_activation",
    "evaluate_control",
    "select_control_entries",
]
