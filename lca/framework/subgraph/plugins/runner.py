"""SubgraphRunner — outer-facing seam for one subgraph execution (ADR-0219 §6).

Single-purpose module: each call to :meth:`SubgraphRunner.run` resolves
one :class:`SubgraphReference` through the injected resolver/runtime,
guards cycle + depth per run, delegates the inner node loop to
:class:`NodeGraphDriver`, and returns ``(state, PhaseOutput)``.

Out of scope:
- any outer-interpreter / fold logic;
- the inner node loop (driver's job);
- mutable outer state (returns updated state).

Composition is wired in :func:`setup` from the two Cordis
capabilities (``subgraph_resolver`` / ``subgraph_runtime``) — no
``__init__`` injection (per plan R6).
"""

from __future__ import annotations

from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.exceptions.subgraph import (
    SubgraphCycleError,
    SubgraphDepthExceededError,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.framework.subgraph.plugins.channel import (
    PhaseOutput,
    PhaseOutputChannel,
)
from lca.framework.subgraph.plugins.node_graph_driver import (
    MAX_SUBGRAPH_DEPTH_DEFAULT,
    NodeGraphDriver,
)
from lca.framework.subgraph.plugins.plan_lift import lift_subgraph_reference_to_v2
from lca.framework.subgraph.plugins.runtime import SubgraphRuntime
from lca.harness.declarative.execute.outcome_projection import (
    InterpretationResult,
    PhaseVisit,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin


class SubgraphRunner:
    """One-call wrapper around :class:`NodeGraphDriver.run` with cycle + depth guards.

    Per ADR-0219 §6: the runner owns recursion depth + cycle detection
    (per-run); the inner node loop is the driver's job. The runner
    delegates the actual driver call, projects the terminal
    :class:`PhaseOutput` from the driver, and returns
    ``(state, output)`` to the outer caller.
    """

    def __init__(
        self,
        *,
        resolver: object,
        runtime: SubgraphRuntime,
        max_subgraph_depth: int = MAX_SUBGRAPH_DEPTH_DEFAULT,
    ) -> None:
        self._resolver = resolver
        self._runtime = runtime
        self._max_depth = max_subgraph_depth
        self._recursion_stack: set[str] = set()

    async def run(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        channel: PhaseOutputChannel,
    ) -> tuple[AgentState, PhaseOutput]:
        """Execute ``ref``'s subgraph and return ``(state, output)``.

        Cycle and depth guards fire *before* any inner execution; the
        stack is unwound on both success and failure. The driver
        publishes the terminal ``PhaseOutput`` on ``channel`` before
        this method returns; we additionally return it so the caller
        can ``absorb`` or forward without a second channel read.
        """
        if ref.plan_ref in self._recursion_stack:
            raise SubgraphCycleError(ref.plan_ref)
        if len(self._recursion_stack) >= self._max_depth:
            raise SubgraphDepthExceededError(
                len(self._recursion_stack), self._max_depth,
            )
        self._recursion_stack.add(ref.plan_ref)
        try:
            sub_plan_obj = self._resolver.resolve(ref.plan_ref)  # type: ignore[union-attr]
            spec = lift_subgraph_reference_to_v2(ref, sub_plan_obj)
            driver = NodeGraphDriver(
                spec=spec,
                plan_ref=ref.plan_ref,
                scope=self._runtime,
            )
            sub_result = await driver.run(
                outer_state=outer_state,
                channel=channel,
                artifacts={},
            )
            return sub_result.state, sub_result.output or _failed_output()
        finally:
            self._recursion_stack.discard(ref.plan_ref)


def _failed_output() -> PhaseOutput:
    """Empty :class:`PhaseOutput` for failure paths that lose the driver result.

    The driver itself never raises; it folds failures into an
    :class:`InterpretationResult` whose ``output`` field still carries
    the last published :class:`PhaseOutput`. This helper is the
    fallback when the driver returns without an ``output`` (defensive
    only — the driver always sets one in production).
    """
    return PhaseOutput()


def _failed_result(
    *,
    plan_ref: str,
    outer_state: AgentState,
    node_id: str,
    error: BaseException,
    visits: tuple[PhaseVisit, ...],
    facts: tuple[Any, ...],
    output: PhaseOutput,
) -> InterpretationResult:
    """Build the FAILED :class:`InterpretationResult` for a driver failure.

    Per ADR-0219 §6: this constructor lives on the runner (single
    owner of all subgraph failure shapes); the driver calls it via a
    top-level import for ``resolve_factory`` / executor exceptions.
    """
    from lca.contracts.models.core.policy.stop import StopDecision, StopReason
    from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
        DeclarativeRunOutcome,
        ExecutionOutcome,
        PhaseRunCursor,
    )

    cursor = PhaseRunCursor(
        plan_ref=plan_ref,
        node_id=node_id,
        visit_counts=(),
        edge_counts=(),
        artifacts={},
        causation_refs=(),
        budget_snapshot={"step": 0},
    )
    outcome = DeclarativeRunOutcome(
        kind=ExecutionOutcome.FAILED,
        cursor=cursor,
        stop=StopDecision(should_stop=True, reason=StopReason.ERROR),
        error_fact=None,
    )
    return InterpretationResult(
        state=outer_state,
        artifact=None,
        visits=visits,
        facts=facts,
        terminal_node=node_id,
        outcome=outcome,
        output=output,
    )


@plugin(
    id="subgraph.runner",
    Config=None,
    provides=("subgraph_runner",),
    requires=("subgraph_resolver", "subgraph_runtime"),
    layer="L1",
    kind=PluginKind.DRIVER,
    effects="none",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(
            grants=("plugin.serve", "subgraph.run"),
        ),
        observability=EvidenceContract(
            descriptors=("subgraph_runner.served", "subgraph_runner.executed"),
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve", "subgraph_resolver", "subgraph_runtime"),
        emits=("subgraph.executed",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Wire SubgraphRunner from Cordis-injected capabilities and provide it.

    The declared ``requires=`` keys are checked at boot by Cordis
    (per ADR-0110); a profile that fails to provide any of them raises
    :class:`cordis.fiber.ValidationError` before this ``setup`` runs.
    """
    resolver = ctx.inject("subgraph_resolver")
    runtime = ctx.inject("subgraph_runtime")
    runner = SubgraphRunner(resolver=resolver, runtime=runtime)
    ctx.provide("subgraph_runner", runner)


__all__ = ["SubgraphRunner", "setup"]
