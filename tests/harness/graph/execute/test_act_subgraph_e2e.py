"""End-to-end: ``bundles/act.yaml`` subgraph driver test (ADR-0217 §3.3, PR-3 sibling).

Loads the real ``bundles/act.yaml`` + nested ``bundles/concept/effect_execute.yaml``
and runs the :class:`NodeGraphDriver` through all five act nodes
(validate → authorize → envelope → dispatch → observe) against the real
executors + a stub ``EffectGateway``. Verifies:

1. yaml loads cleanly through :func:`_load_bundle_graph_spec`.
2. driver walks all 5 act nodes in spec order (validate → authorize →
   envelope → dispatch → observe), dispatch delegating to the inner
   ``effect_execute`` subgraph via ``sub_spec_ref``.
3. nested effect_execute subgraph runs once (its single ``effect.execute``
   node calls the stub EffectGateway).
4. typed ``Decision`` → ``CommandEnvelope`` → ``EffectReceipt`` flows
   through the channel: the terminal ``PhaseOutput`` carries the
   ``receipt`` (effect_execute writes ``receipt``; act.observe is a
   passthrough).
5. observe node records an ``effect.observed`` RunFact via the journal
   capability (stub journal captures the fact).

This test pins the contract that the act subgraph's node-level
``sub_spec_ref`` on ``act.dispatch`` correctly hands control to the
nested subgraph framework and that the typed boundary DTOs survive the
driver's port-projection cycle (ADR-0220 §3.3 + §4.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

import pytest

from lca.contracts.harness.act.effect_receipt import (
    EffectOutcome,
    EffectReceipt,
)
from lca.contracts.models.core.execution.decision import (
    Decision,
    TaskProgress,
    ToolCall,
)
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.act.command.envelope import RunFact
from lca.framework.subgraph.plugins.channel import (
    InMemoryPhaseOutputChannel,
    PhaseOutput,
)
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver
from lca.harness.declarative.compile.subgraph_resolver import (
    BundleSubgraphResolver,
    _load_bundle_graph_spec,
)
from lca.plugins.concept.act_subgraph.authorize import ActAuthorizeExecutor
from lca.plugins.concept.act_subgraph.envelope import ActEnvelopeExecutor
from lca.plugins.concept.act_subgraph.observe import ActObserveExecutor
from lca.plugins.concept.act_subgraph.validate import ActValidateExecutor
from lca.plugins.concept.effect_execute.execute import EffectExecuteExecutor

OUTER_BUNDLE = "bundles/act.yaml"
INNER_BUNDLE = "bundles/concept/effect_execute.yaml"


def _state() -> AgentState:
    return AgentState(trace_id="trace:act-subgraph-e2e", task="test", budget=Budget())


def _decision(*, tool_name: str = "echo") -> Decision:
    """Build a USE_TOOL Decision that the act subgraph will accept."""
    return Decision(
        decision_id="dec-act-e2e",
        action_type="use_tool",
        rationale="act subgraph e2e",
        confidence=1.0,
        tool_calls=[
            ToolCall(
                call_id="call-act-e2e-1",
                tool_name=tool_name,
                arguments={"message": "hello"},
            )
        ],
        task_progress=TaskProgress(),
    )


@dataclass
class _StubJournal:
    """Records every fact passed to ``commit_fact``."""

    facts: list[RunFact] = field(default_factory=list)

    def commit_fact(self, fact: RunFact, *, plan_ref: str, node_ref: str) -> None:
        del plan_ref, node_ref
        self.facts.append(fact)


@dataclass
class _StubEffectGateway:
    """Minimal EffectDispatcher surface used by ``effect.execute``.

    The act.envelope node mints a CommandEnvelope with provider="effect.body";
    the gateway is allowed to ignore that and return whatever the test
    asserts against. It must accept (envelope, policy) and return a
    dict-shaped receipt (consumed by ``effect_execute.execute._dispatch``)
    or any object — the real plugin only reads ``output.get(...)``.
    """

    calls: list[tuple[str, str]] = field(default_factory=list)

    async def execute(self, envelope: Any, policy: Any) -> dict[str, Any]:
        del policy
        # Record the provider so the test can assert tool dispatch happened.
        self.calls.append((envelope.provider, envelope.idempotency_key))
        return {
            "invocation_id": "inv-act-e2e-1",
            "idempotency_key": envelope.idempotency_key,
            "result": {"echo": "hello"},
            "output_ref": "echo://hello",
        }


@dataclass
class _StubScope:
    """SubgraphRuntime seam: composite-key for the 5 act factories +
    ``effect_gateway`` + ``journal`` capabilities.
    """

    executors: dict[tuple[str, str], Any]
    effect_gateway: _StubEffectGateway
    journal: _StubJournal

    def resolve(self, capability: str) -> Any:
        if capability == "effect_gateway":
            return self.effect_gateway
        if capability == "journal":
            return self.journal
        return None

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        key = (region, factory)
        ex = self.executors.get(key)
        if ex is None:
            raise LookupError(f"no stub executor for {region}::{factory}")
        return ex


def _build_scope() -> _StubScope:
    executors: dict[tuple[str, str], Any] = {
        ("concept", "act.validate"): ActValidateExecutor(),
        ("concept", "act.authorize"): ActAuthorizeExecutor(),
        ("concept", "act.envelope"): ActEnvelopeExecutor(),
        # act.dispatch carries sub_spec_ref → driver never invokes its
        # factory; we still register a sentinel so any accidental lookup
        # fails fast with a clear error.
        ("concept", "act.dispatch.ref"): _SentinelExecutor(),
        ("concept", "act.observe"): ActObserveExecutor(),
        ("concept", "effect.execute"): EffectExecuteExecutor(),
    }
    return _StubScope(
        executors=executors,
        effect_gateway=_StubEffectGateway(),
        journal=_StubJournal(),
    )


@dataclass
class _SentinelExecutor:
    """Executor for ``act.dispatch`` — should never be invoked.

    The act.dispatch node in ``bundles/act.yaml`` carries a ``sub_spec_ref``
    pointing at ``bundles/concept/effect_execute.yaml``. Per ADR-0219 §10.11
    the driver delegates to SubgraphRunner and never calls the factory.
    If this sentinel is reached, the test should fail loudly.
    """

    semantic_name: str = "act.dispatch.ref"
    region: str = "concept"
    declared_inputs: tuple[str, ...] = ()
    declared_outputs: tuple[str, ...] = ()

    async def node_execute(self, ctx: Any, node_input: Any) -> Any:
        raise AssertionError(
            "act.dispatch factory was invoked but its node carries "
            "sub_spec_ref; the driver should have delegated to the "
            "nested effect_execute subgraph instead"
        )


def _build_driver(scope: _StubScope) -> NodeGraphDriver:
    """Resolve the outer act bundle and build a driver pointed at it."""
    spec = _load_bundle_graph_spec(OUTER_BUNDLE)
    resolver = BundleSubgraphResolver()
    return NodeGraphDriver(
        spec=spec,
        plan_ref=OUTER_BUNDLE,
        scope=scope,
        sub_runner=_build_sub_runner(scope, resolver),
        channel_factory=InMemoryPhaseOutputChannel,
    )


def _build_sub_runner(
    scope: _StubScope, resolver: BundleSubgraphResolver
) -> Any:
    """Construct a SubgraphRunner that reuses the same scope and resolver."""
    from lca.framework.subgraph.plugins.runner import SubgraphRunner

    return SubgraphRunner(
        resolver=resolver,
        runtime=scope,
    )


class TestActSubgraphE2E:
    """End-to-end run of the act subgraph spec via the production driver."""

    def test_yaml_resolves_via_resolver(self) -> None:
        """Step 1:outer act.yaml loads through the production resolver."""
        resolver = BundleSubgraphResolver()
        # Both inner and outer are v2 BundleGraphSpec → resolver handles
        # them via the v2 path; we only assert the outer here.
        outer = resolver.resolve(OUTER_BUNDLE)
        assert outer is not None

    def test_yaml_has_five_nodes_and_four_edges(self) -> None:
        """Step 1 cont'd:outer act.yaml is 5 nodes + 4 edges; entry=validate.

        act.yaml shape:
          validate → authorize → envelope → dispatch → observe
          4 edges (5 nodes, last is terminal via implicit fan-in).
        """
        spec = _load_bundle_graph_spec(OUTER_BUNDLE)
        assert len(spec.nodes) == 5
        assert len(spec.edges) == 4
        ids = {n.id for n in spec.nodes}
        assert ids == {
            "act.validate",
            "act.authorize",
            "act.envelope",
            "act.dispatch",
            "act.observe",
        }
        # act.dispatch is a typed sub_spec_ref delegate node — the factory
        # field is metadata only (ADR-0220 P10) so its real entry point
        # is the inner subgraph's effect.execute.
        dispatch_node = next(n for n in spec.nodes if n.id == "act.dispatch")
        assert dispatch_node.sub_spec_ref is not None
        assert dispatch_node.sub_spec_ref.plan_ref == INNER_BUNDLE

    def test_inner_bundle_has_one_node(self) -> None:
        """Step 1 cont'd:inner effect_execute.yaml is 1 node, 0 edges."""
        spec = _load_bundle_graph_spec(INNER_BUNDLE)
        assert len(spec.nodes) == 1
        assert {n.id for n in spec.nodes} == {"effect.execute"}

    @pytest.mark.asyncio
    async def test_driver_walks_all_five_act_nodes_in_order(self) -> None:
        """Step 2:driver walks validate → authorize → envelope → dispatch → observe.

        act.dispatch carries sub_spec_ref, so the driver delegates to the
        SubgraphRunner and the inner effect.execute shows up as a single
        ``PhaseVisit(node_id="act.dispatch", result_kind="subgraph")``.
        The visit list therefore carries 5 act node ids in order, with
        the dispatch one tagged ``subgraph``.
        """
        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        result = await driver.run(
            outer_state=state,
            channel=channel,
            artifacts={},
            outer_input={"decision": _decision()},
        )

        node_ids = [v.node_id for v in result.visits]
        assert node_ids == [
            "act.validate",
            "act.authorize",
            "act.envelope",
            "act.dispatch",
            "act.observe",
        ]
        # The dispatch visit is the inner-subgraph delegation.
        dispatch_visit = next(v for v in result.visits if v.node_id == "act.dispatch")
        assert dispatch_visit.result_kind == "subgraph"

    @pytest.mark.asyncio
    async def test_inner_effect_execute_invokes_gateway_once(self) -> None:
        """Step 3:the inner effect_execute subgraph calls the gateway once.

        The act.envelope node mints a CommandEnvelope with
        ``provider="effect.body"``; the stub gateway records the call.
        """
        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        await driver.run(
            outer_state=state,
            channel=channel,
            artifacts={},
            outer_input={"decision": _decision()},
        )

        # Exactly one effect dispatch happened — no retries, no fan-out.
        assert len(scope.effect_gateway.calls) == 1
        provider, idempotency_key = scope.effect_gateway.calls[0]
        # ``act.envelope`` mints the envelope with ``provider="effect.body"``;
        # that is the dispatcher's contract, not the receipt's ``provider``
        # field (which is derived from ``envelope.metadata["operation"]``).
        assert provider == "effect.body"
        # Idempotency key encodes (plan_ref, node_ref, decision_id) so it
        # is stable across re-runs of the same decision.
        assert "dec-act-e2e" in idempotency_key
        assert "act.envelope" in idempotency_key

    @pytest.mark.asyncio
    async def test_terminal_phase_output_carries_receipt(self) -> None:
        """Step 4:the receipt produced by inner effect_execute reaches the
        channel ``PhaseOutput`` (same-named passthrough, ADR-0217 §3.3.3).

        The inner terminal port ``receipt`` flows out through the nested
        driver's close-out projection → outer PortRegistry → final
        PhaseOutput.receipt. act.observe is a typed passthrough so the
        outer driver sees the receipt unchanged.
        """
        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        result = await driver.run(
            outer_state=state,
            channel=channel,
            artifacts={},
            outer_input={"decision": _decision()},
        )

        # The driver publishes the terminal PhaseOutput on the channel.
        snapshot = channel.snapshot()
        assert len(snapshot) == 1
        output = next(iter(snapshot.values()))
        assert isinstance(output, PhaseOutput)
        # receipt flows through unchanged.
        assert isinstance(output.receipt, EffectReceipt)
        assert output.receipt.outcome is EffectOutcome.SUCCEEDED
        assert output.receipt.invocation_id == "inv-act-e2e-1"
        # ``receipt.provider`` is derived from the envelope's
        # ``metadata["operation"]`` (set by ``act.envelope`` to
        # ``"body.act"``), not from the dispatcher's envelope provider
        # (``"effect.body"``). Both are part of the typed boundary.
        assert output.receipt.provider == "body.act"
        # The driver's returned InterpretationResult.output is the same
        # terminal PhaseOutput (one typed envelope end-to-end).
        assert result.output is output

    @pytest.mark.asyncio
    async def test_observe_records_effect_observed_run_fact(self) -> None:
        """Step 5:act.observe writes an ``effect.observed`` RunFact to the
        journal capability (ADR-0220 §3.3 observation surface).

        The stub journal captures the fact so reflect/remember can pick
        it up downstream. The fact_id encodes (plan_ref, node_id,
        invocation_id) so it is uniquely traceable.
        """
        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        await driver.run(
            outer_state=state,
            channel=channel,
            artifacts={},
            outer_input={"decision": _decision()},
        )

        assert len(scope.journal.facts) == 1
        fact = scope.journal.facts[0]
        assert fact.kind == "effect.observed"
        assert fact.payload["outcome"] == EffectOutcome.SUCCEEDED.value
        assert fact.payload["provider"] == "body.act"
        assert fact.payload["invocation_id"] == "inv-act-e2e-1"
        # fact_id encodes the trace keys
        assert "act.observe" in fact.fact_id
        assert "inv-act-e2e-1" in fact.fact_id

    @pytest.mark.asyncio
    async def test_authorization_rejects_unsafe_tool_name(self) -> None:
        """Boundary 1:act.authorize refuses ``self_destruct`` tools.

        Validates the safety-boundary check inside the act subgraph.
        The validate node should still accept the decision shape, but
        authorize raises and the driver surfaces it as a FAILED
        InterpretationResult (no re-raise — the driver's fail-loud
        path is the typed FAILED outcome).
        """
        from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
            ExecutionOutcome,
        )

        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        bad_decision = _decision(tool_name="self_destruct_xyz")
        result = await driver.run(
            outer_state=state,
            channel=channel,
            artifacts={},
            outer_input={"decision": bad_decision},
        )
        # Driver surfaces the inner ValueError as a typed FAILED outcome.
        assert result.outcome is not None
        assert result.outcome.kind is ExecutionOutcome.FAILED
        # The visits stop at act.authorize — dispatch / observe never
        # ran because the chain was short-circuited by the rejection.
        visited_ids = [v.node_id for v in result.visits]
        assert "act.validate" in visited_ids
        # terminal_node is the node whose execution raised (authorize).
        assert result.terminal_node == "act.authorize"
        assert "act.dispatch" not in visited_ids
        assert "act.observe" not in visited_ids
        # No effect was dispatched — the rejection stopped the chain.
        assert scope.effect_gateway.calls == []

    @pytest.mark.asyncio
    async def test_authorization_rejects_missing_state_on_budget(self) -> None:
        """Boundary 2:act.authorize accepts ``state=None`` (no budget check).

        The outer drive may not always provide AgentState; authorize's
        guard allows None and skips the budget dimension entirely. The
        full chain runs.
        """
        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        # outer_input omits state → port_context returns None for state,
        # authorize's ``state is not None`` guard passes.
        with (
            patch(
                "lca.framework.subgraph.plugins.node_graph_driver.emit_for_node",
                autospec=True,
            ),
        ):
            result = await driver.run(
                outer_state=state,
                channel=channel,
                artifacts={},
                outer_input={"decision": _decision()},
            )
        # Full chain ran — receipt flowed.
        assert isinstance(result.output.receipt, EffectReceipt)

    @pytest.mark.asyncio
    async def test_node_emits_fire_in_spec_declared_order(self) -> None:
        """Step 6:act subgraph emits 6 spine EPs in the order declared by
        ``bundles/act.yaml``.

        Per node config:
          - act.validate: enter=[phase.tool.call.start], exit=[]
          - act.authorize: enter=[think.gate.start], exit=[]
          - act.envelope: enter=[], exit=[]
          - act.dispatch: enter=[body.tool.execute.start], exit=[body.tool.execute.end]
          - act.observe: enter=[], exit=[phase.tool.call.end, phase.act.fold.end]

        Total: 6 EPs. Failure-path tagging is verified separately.
        """
        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        with patch(
            "lca.framework.subgraph.plugins.node_graph_driver.emit_for_node",
            autospec=True,
        ) as emit:
            await driver.run(
                outer_state=state,
                channel=channel,
                artifacts={},
                outer_input={"decision": _decision()},
            )

        ep_calls = [call.args[0] for call in emit.call_args_list]
        assert ep_calls == [
            "phase.tool.call.start",  # act.validate enter
            "think.gate.start",  # act.authorize enter
            "body.tool.execute.start",  # act.dispatch enter
            "body.tool.execute.end",  # act.dispatch exit
            "phase.tool.call.end",  # act.observe exit (1/2)
            "phase.act.fold.end",  # act.observe exit (2/2)
        ]
        # act.envelope has no emits — confirm it is absent.
        assert "act.envelope" not in [
            call.kwargs.get("node_id", "") for call in emit.call_args_list
        ]

    @pytest.mark.asyncio
    async def test_failure_path_tags_end_emits_with_outcome_failure(self) -> None:
        """Step 6 cont'd:on act.authorize rejection, the driver does not
        fire end EPs (authorize has no exit emits and the chain ends in
        a FAILED ``InterpretationResult``).

        This is the boundary where the observation surface terminates:
        the inner subgraph never runs, so no act.dispatch / act.observe
        end EPs fire. The ``act.validate`` enter EP already fired
        (before authorize was even reached), so observation captures
        the start-of-chain only.
        """
        from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
            ExecutionOutcome,
        )

        scope = _build_scope()
        driver = _build_driver(scope)
        channel = InMemoryPhaseOutputChannel()
        state = _state()

        with patch(
            "lca.framework.subgraph.plugins.node_graph_driver.emit_for_node",
            autospec=True,
        ) as emit:
            result = await driver.run(
                outer_state=state,
                channel=channel,
                artifacts={},
                outer_input={"decision": _decision(tool_name="self_destruct_xyz")},
            )

        assert result.outcome is not None
        assert result.outcome.kind is ExecutionOutcome.FAILED
        # Only validate's enter EP fired; authorize's enter EP fired too
        # (the dispatcher fires emits before the executor, and authorize's
        # raise aborts after enter). No end EPs fire because the chain
        # short-circuits at authorize.
        ep_ids = [call.args[0] for call in emit.call_args_list]
        assert ep_ids == [
            "phase.tool.call.start",  # validate enter
            "think.gate.start",  # authorize enter (before raise)
        ]
