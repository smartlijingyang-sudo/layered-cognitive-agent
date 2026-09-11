"""SubgraphRunner — outer-facing seam for one subgraph execution (ADR-0219 §6).

Single-purpose module: each call to :meth:`SubgraphRunner.run` resolves
one :class:`SubgraphReference` through the injected resolver/runtime,
guards cycle + depth per run, delegates the inner node loop to
:class:`NodeGraphDriver`, and returns ``(state, PhaseOutput)``.

Out of scope:
- any outer-interpreter / fold logic;
- the inner node loop (driver's job);
- mutable outer state (returns updated state).

Composition is wired in :func:`setup`. The framework self-assembles the
default resolver (``default_subgraph_resolver``) — profiles no longer
need a dedicated ``lca-subgraph-resolver`` plugin to provide it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from lca.cognition.close_out import CognitiveCloseOut
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
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
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
    ObserverFn,
)
from lca.framework.subgraph.plugins.plan_lift import lift_subgraph_reference_to_v2
from lca.framework.subgraph.plugins.runtime import (
    PluginContextBackedRuntime,
    SubgraphRuntime,
)
from lca.harness.declarative.compile.subgraph_resolver import (
    default_subgraph_resolver,
)
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
        observers: tuple[ObserverFn, ...] = (),
        channel_factory: Callable[[], PhaseOutputChannel] | None = None,
        close_out: CognitiveCloseOut | None = None,
    ) -> None:
        self._resolver = resolver
        self._runtime = runtime
        self._max_depth = max_subgraph_depth
        # ADR-0219 §10.11 item (4): observer port on the runner. Cordis
        # boot may pass observers=() and rely on bind_cordis_seams to
        # populate; Default factory passes the Session.append closure.
        self._observers = observers
        # ADR-0219 §10.11 item (1): inner driver recursion needs both a
        # SubgraphRunner and a fresh PhaseOutputChannel per inner run.
        # Both are populated by SubgraphRunner itself — never by an
        # external caller — so the seam stays at the runner surface.
        self._channel_factory = channel_factory
        # ADR-0219 §10.11.5: the runner owns the default close-out
        # implementation. Callers may inject a different one (tests,
        # alternative policies) via this seam.
        self._close_out: CognitiveCloseOut = close_out or CognitiveCloseOut()
        self._recursion_stack: set[str] = set()

    async def run(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        channel: PhaseOutputChannel,
        outer_input: Mapping[str, Any] | None = None,
    ) -> tuple[AgentState, PhaseOutput]:
        """Execute ``ref``'s subgraph and return ``(state, output)``.

        Cycle and depth guards fire *before* any inner execution; the
        stack is unwound on both success and failure. The driver
        publishes the terminal ``PhaseOutput`` on ``channel`` before
        this method returns; we additionally return it so the caller
        can ``absorb`` or forward without a second channel read.

        On the FAILED path (ADR-0219 §10.11 item 3) we additionally
        populate ``output.outcome_kind`` and ``output.error`` so the
        outer interpreter can see the failure shape without an extra
        envelope.
        """
        if ref.plan_ref in self._recursion_stack:
            raise SubgraphCycleError(ref.plan_ref)
        if len(self._recursion_stack) >= self._max_depth:
            raise SubgraphDepthExceededError(
                len(self._recursion_stack),
                self._max_depth,
            )
        self._recursion_stack.add(ref.plan_ref)
        try:
            sub_plan_obj = self._resolver.resolve(ref.plan_ref)  # type: ignore[union-attr]
            spec = lift_subgraph_reference_to_v2(ref, sub_plan_obj)
            driver = NodeGraphDriver(
                spec=spec,
                plan_ref=ref.plan_ref,
                scope=self._runtime,
                observers=self._observers,
                sub_runner=self,
                channel_factory=self._channel_factory,
                close_out=self._close_out,
            )
            sub_result = await driver.run(
                outer_state=outer_state,
                channel=channel,
                artifacts={},
                outer_input=outer_input,
            )
            output = sub_result.output
            if (
                sub_result.outcome is not None
                and sub_result.outcome.kind is ExecutionOutcome.FAILED
            ):
                # ADR-0219 §10.11: FAILED outcome → typed failure shape on
                # output. The derived string comes from the driver's stop
                # reason when available; otherwise we use a literal so the
                # outer fold always has something to surface.
                stop = sub_result.outcome.stop
                derived_error = (
                    stop.reason.value
                    if stop is not None and getattr(stop, "reason", None) is not None
                    else "inner subgraph failed"
                )
                output = output.model_copy(
                    update={
                        "outcome_kind": ExecutionOutcome.FAILED,
                        "error": derived_error,
                    }
                )
            return sub_result.state, output
        finally:
            self._recursion_stack.discard(ref.plan_ref)


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
    provides=("subgraph_runner", "phase_output_channel_factory"),
    requires=(),
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
        reads=("plugin.serve",),
        emits=("subgraph.executed",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Wire SubgraphRunner from Cordis-injected capabilities and provide it.

    The inner subgraph's capability scope is sourced from this same
    ``ctx``: the runner constructs a :class:`PluginContextBackedRuntime`
    that resolves every ``runtime.<capability>`` read inside a node
    through ``ctx.require(capability)``. There is no separate
    ``subgraph_runtime`` capability key; the framework never invents
    objects of its own — capability bindings live entirely in the
    PluginContext.

    The declared ``requires=`` keys are checked at boot by Cordis
    (per ADR-0110); a profile that fails to provide any of them raises
    :class:`cordis.fiber.ValidationError` before this ``setup`` runs.

    ADR-0219 §10.11 item (4): the observer port is config-driven when
    Cordis provides a ``subgraph_observers`` tuple; otherwise we fall
    back to ``()`` (no observer wiring). The Default factory binds the
    ``Session.append`` observer at construction-time and constructs
    the runner directly with ``observers=...``.
    """
    resolver = default_subgraph_resolver()
    runtime = PluginContextBackedRuntime(ctx=ctx)
    observers: tuple[ObserverFn, ...] = ()
    if hasattr(ctx, "require"):
        try:
            observers = tuple(ctx.require("subgraph_observers"))
        except Exception:
            observers = ()
    # Phase output channel is a framework-owned seam; provide the
    # default in-memory implementation so a profile that wants a
    # different channel (e.g. journal-backed) can override via its
    # own plugin without touching the runner.
    from lca.framework.subgraph.plugins.channel import (
        InMemoryPhaseOutputChannel,
    )

    channel_factory = InMemoryPhaseOutputChannel
    runner = SubgraphRunner(
        resolver=resolver,
        runtime=runtime,
        observers=observers,
        channel_factory=channel_factory,
    )
    ctx.provide("subgraph_runner", runner)
    ctx.provide("phase_output_channel_factory", channel_factory)


__all__ = ["SubgraphRunner", "setup"]
