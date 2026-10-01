"""Think decision repair executor and plugin carrier."""

from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.graph.routing import RoutingDecision
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.nodes.think.decision_repair.constants import (
    _REASON_OK,
    _REASON_REJECTED_SCHEMA,
    _REASON_REJECTED_TRUNCATED,
    _REASON_REPAIRED,
    _REPAIR_REJECTED,
    _REPAIR_SUCCEEDED,
    _SCHEMA_REJECTED,
)
from lca.nodes.think.decision_repair.repair import (
    _raw_preview_from_decision,
    _validate_or_repair_calls,
    _with_tool_calls,
)


@dataclass(frozen=True, slots=True)
class ThinkDecisionRepairExecutor:
    """think 节点: validate / repair ``Decision.tool_calls[*].arguments`` -> forward or re-route."""

    semantic_name: str = "think.decision.repair"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = (PortName("decision"), PortName("tools"))
    declared_outputs: tuple[PortName, ...] = (PortName("decision"), PortName("routing"))

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml): decision, tools
        outputs 端口(yaml): decision, routing

        Reads the ``decision`` port and the optional ``tools`` typed
        port (a ``ToolRegistry`` per ADR-0047). Emits the original or
        repaired ``Decision`` plus a ``RoutingDecision`` whose
        ``next_node`` steers the waterfall toward ``think.gate``
        (ok / repaired) or ``think.route.decide`` (rejected).

        Empty ``decision`` (None) yields an empty ``NodeOutput`` so the
        bundle edge decides routing — typical wiring:
        ``when: eq port.decision value: None`` re-routes to
        ``think.route.decide`` for a full re-reason.

        ``respond`` decisions (no tool_calls but a populated
        ``response_text``) are passed through untouched: ``repair``
        is a use_tool-only concern (tool-call argument validation),
        and clearing the carry-in ``decision`` here would strip the
        outer plan's edge predicate (``decision.action_type ==
        respond``) of the very signal that lets the run complete.
        """
        decision = input.port_values.get(PortName("decision"))
        if decision is None:
            return NodeOutput(port_values={})
        if not _has_tool_calls(decision):
            # ``respond`` (or any non-use_tool) decision → pass through
            # unchanged; only use_tool paths need repair below.
            return NodeOutput(
                port_values={
                    PortName("decision"): decision,
                    PortName("routing"): _route_ok(),
                }
            )

        registry = input.port_values.get(PortName("tools"))

        outcome, repaired_calls = _validate_or_repair_calls(
            decision.tool_calls,
            raw_preview=_raw_preview_from_decision(decision),
            registry=registry,
        )

        if outcome == _SCHEMA_REJECTED:
            return NodeOutput(
                port_values={
                    PortName("decision"): decision,
                    PortName("routing"): _route_rejected_schema(),
                }
            )

        if outcome == _REPAIR_REJECTED:
            return NodeOutput(
                port_values={
                    PortName("decision"): decision,
                    PortName("routing"): _route_rejected_truncated(),
                }
            )

        if outcome == _REPAIR_SUCCEEDED:
            repaired_decision = _with_tool_calls(decision, repaired_calls)
            return NodeOutput(
                port_values={
                    PortName("decision"): repaired_decision,
                    PortName("routing"): _route_repaired(),
                }
            )

        return NodeOutput(
            port_values={
                PortName("decision"): decision,
                PortName("routing"): _route_ok(),
            }
        )


def _has_tool_calls(decision: object) -> bool:
    """``Decision`` is present and carries at least one ``ToolCall``.

    ``None`` and Decision with empty ``tool_calls`` both fall through
    to an empty ``NodeOutput`` so the bundle edge routes them. The
    rationale: upstream ``think.decision.parse`` emits an empty
    tool-call list when the LLM chose ``respond`` / ``ask_user``
    action types, and those should reach ``think.gate`` unchanged
    via the bundle predicate on the upstream parse → gate edge —
    not by a repair node returning them with a synthetic
    ``decision_ok`` routing.
    """
    if not isinstance(decision, Decision):
        return False
    return bool(decision.tool_calls)


def _route_ok() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.gate",
        next_hint=_REASON_OK,
    )


def _route_repaired() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.gate",
        next_hint=_REASON_REPAIRED,
    )


def _route_rejected_schema() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.route.decide",
        next_hint=_REASON_REJECTED_SCHEMA,
    )


def _route_rejected_truncated() -> RoutingDecision:
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.route.decide",
        next_hint=_REASON_REJECTED_TRUNCATED,
    )


@plugin(
    id="phase.think.decision.repair",
    Config=None,
    provides=("think::think.decision.repair",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_decision_repair.checked",
                "phase_think_decision_repair.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册: ``{region}::{semantic_name}``。"""
    del config
    executor = ThinkDecisionRepairExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)
