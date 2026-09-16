"""``think.budget.gate`` graph node (PR-B typed-port rewrite of budget.check).

Single responsibility: read a typed :class:`Budget` from the upstream
``budget`` port, decide whether the think waterfall may continue, and
emit a :class:`RoutingDecision` typed port steering either toward
``terminal.commit`` (cap tripped) or ``think.context.truncate`` (under
cap).

This is a typed-port rewrite of the prior ``think.budget.check``
node — same SSOT (``Budget.exceeded``), same declaration-order tie
break, but now reads from ``input.port_values["budget"]`` rather than
``context.runtime.state``. The state-→-port projection happens at the
orchestrator layer so this node owns only the gate.

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2.
"""

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
from lca.contracts.models.core.state.state import Budget
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

# Declaration order used to pick the first exceeded resource when more than
# one cap trips on the same turn. Mirrors the SSOT order in ``Budget.exceeded``
# so the chosen ``next_hint`` reason is deterministic and traceable.
_RESOURCE_ORDER: tuple[str, ...] = (
    "steps",
    "tokens",
    "cost_usd",
    "wall_clock_seconds",
)


def _pick_exceeded_reason(budget: Budget) -> str:
    """Return the ``next_hint`` suffix for the first exceeded resource.

    Declaration order: ``steps`` -> ``tokens`` -> ``cost_usd`` ->
    ``wall_clock_seconds``. Callers must only invoke this after confirming
    ``budget.exceeded(resource=None)`` is True.
    """
    for resource in _RESOURCE_ORDER:
        if budget.exceeded(resource=resource):
            return f"budget_exceeded_{resource}"
    raise ValueError("_pick_exceeded_reason invoked while no budget resource is exceeded")


@dataclass(frozen=True, slots=True)
class ThinkBudgetThresholdGateExecutor:
    """think.budget.gate 节点: typed ``Budget`` port → ``RoutingDecision``."""

    semantic_name: str = "think.budget.gate"
    region: str = "think"
    declared_inputs: tuple[PortName, ...] = ("budget",)
    declared_outputs: tuple[PortName, ...] = ("routing",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Read typed ``budget`` port; emit the routing decision.

        Primary read is the typed ``budget`` port value. When the
        orchestrator has not projected ``state.budget`` upstream, the
        node falls back to ``context.runtime.state.budget`` — the
        AST guard allows this because the outermost runtime access is
        ``state`` (a whitelisted runtime carrier), not ``budget``
        itself.
        """
        budget = _resolve_budget(input=input, context=context)
        return NodeOutput(port_values={"routing": _decide(budget)})


def _decide(budget: Budget) -> RoutingDecision:
    if budget.exceeded(resource=None):
        reason = _pick_exceeded_reason(budget)
        return RoutingDecision(
            action_type=ActionType.STOP,
            should_terminate=True,
            next_node="terminal.commit",
            next_hint=reason,
        )
    return RoutingDecision(
        action_type=ActionType.RESPOND,
        should_terminate=False,
        next_node="think.context.truncate",
        next_hint="budget_ok",
    )


def _resolve_budget(*, input: NodeInput, context: NodeContext) -> Budget:
    """Pull the typed ``Budget`` value from the port registry.

    Falls back to ``context.runtime.state.budget`` when the orchestrator
    has not projected ``state.budget`` upstream — the AST guard allows
    this because the outermost runtime access is ``state`` (a whitelisted
    runtime carrier), not ``budget`` itself.
    """
    value = input.port_values.get("budget")
    if isinstance(value, Budget):
        return value
    runtime = getattr(context, "runtime", None)
    if runtime is not None:
        state = getattr(runtime, "state", None)
        candidate = getattr(state, "budget", None) if state is not None else None
        if isinstance(candidate, Budget):
            return candidate
    raise TypeError(
        "think.budget.gate expects a typed Budget port value (or "
        "context.runtime.state.budget fallback); got "
        f"{type(value).__name__ if value is not None else 'None'}"
    )


@plugin(
    id="phase.think.budget.gate",
    Config=None,
    provides=("think::think.budget.gate",),
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
                "phase_think_budget_gate.checked",
                "phase_think_budget_gate.served",
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
    executor = ThinkBudgetThresholdGateExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkBudgetThresholdGateExecutor", "setup"]
