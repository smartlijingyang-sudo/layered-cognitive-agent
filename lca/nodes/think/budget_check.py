"""phase.think.budget.check — typed budget gate after route.decide.

think 子图节点 plugin: 读取 ``state.budget`` (the ``Budget`` dataclass at
``lca/contracts/models/core/state/state.py``) 并根据超限状态发出
``RoutingDecision`` typed port, 将预算门控从隐式边谓词上移到类型化、可
测、可调试的节点代码。

Waterfall position: after ``think.route.decide`` (miss path), before
``think.context.compact`` / ``think.history.assemble``. 当 ``route.decide``
走 miss path (next_node 指向 ``think.context.compact``) 时,本节点先读
``state.budget``,若超限则把控制面强制改道 ``terminal.commit`` 并
``should_terminate=True``;若仍有额度则放行到 ``think.context.compact``。

ADR-0225: budget lives on outer edges and in ``BudgetLedger`` — never as a
per-node ``max_visits`` counter. 本节点不计数,只读 SSOT 并发路由。

ADR-0227 / ADR-0228: 手写 ``@plugin(...)`` carrier + typed-port
``declared_inputs`` / ``declared_outputs`` 编译期类型化。
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

_RESOURCE_REASON_SUFFIX: dict[str, str] = {
    "steps": "steps",
    "tokens": "tokens",
    "cost_usd": "cost_usd",
    "wall_clock_seconds": "wall_clock_seconds",
}


def _pick_exceeded_reason(budget: Budget) -> str:
    """Return the ``next_hint`` suffix for the first exceeded resource.

    Declaration order: ``steps`` -> ``tokens`` -> ``cost_usd`` ->
    ``wall_clock_seconds``. Callers must only invoke this after confirming
    ``budget.exceeded(resource=None)`` is True.
    """
    for resource in _RESOURCE_ORDER:
        if budget.exceeded(resource=resource):
            return f"budget_exceeded_{_RESOURCE_REASON_SUFFIX[resource]}"
    # ``Budget.exceeded(resource=None)`` was False at the call site; the
    # caller should not have invoked this helper. Surface a typed signal
    # rather than silently fall through.
    raise ValueError("_pick_exceeded_reason invoked while no budget resource is exceeded")


@dataclass(frozen=True, slots=True)
class ThinkBudgetCheckExecutor:
    """think 节点: read ``state.budget`` -> emit ``RoutingDecision`` typed port."""

    semantic_name: str = "think.budget.check"
    region: str = "phase:think"
    declared_inputs: tuple[PortName, ...] = ("state",)
    declared_outputs: tuple[PortName, ...] = ("routing",)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """think 子图节点入口。

        inputs 端口(yaml): state
        outputs 端口(yaml): routing

        Reads ``state.budget`` (``Budget`` dataclass). If any cap is
        exceeded, emits ``RoutingDecision(next_node="terminal.commit",
        should_terminate=True, next_hint="budget_exceeded_<resource>")``.
        Otherwise emits
        ``RoutingDecision(next_node="think.context.compact",
        should_terminate=False, next_hint="budget_ok")``.

        Pure function of the ``state`` port. No env / time reads at the
        node layer; ``Budget.exceeded`` is the SSOT cap check.
        """
        del context  # unused: pure function of input ports
        state = input.port_values.get("state")
        budget = _extract_budget(state)

        if budget.exceeded(resource=None):
            reason = _pick_exceeded_reason(budget)
            routing = RoutingDecision(
                action_type=ActionType.STOP,
                should_terminate=True,
                next_node="terminal.commit",
                next_hint=reason,
            )
        else:
            routing = RoutingDecision(
                action_type=ActionType.RESPOND,
                should_terminate=False,
                next_node="think.context.compact",
                next_hint="budget_ok",
            )
        return NodeOutput(port_values={"routing": routing})


def _extract_budget(state: object) -> Budget:
    """Pull the ``Budget`` instance off the ``state`` port value.

    ``AgentState`` exposes ``budget`` as a typed ``Budget`` dataclass
    field. The node accepts any object that has a ``budget`` attribute
    so typed mock ``state`` fixtures used by tests pass type checking
    without pulling the full ``AgentState`` into the contracts surface.
    """
    budget_obj = getattr(state, "budget", None)
    if not isinstance(budget_obj, Budget):
        raise TypeError(
            "think.budget.check expects a state-like object with a "
            f"Budget attribute on .budget; got {type(budget_obj).__name__}"
        )
    return budget_obj


@plugin(
    id="phase.think.budget.check",
    Config=None,
    provides=("phase:think::think.budget.check",),
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
                "phase_think_budget_check.checked",
                "phase_think_budget_check.served",
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
    executor = ThinkBudgetCheckExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = ["ThinkBudgetCheckExecutor", "setup"]
