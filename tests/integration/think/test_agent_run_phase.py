"""End-to-end: agent.run.phase graph (ADR-0220 §11 P8).

Verifies the top-level phase graph:

  - parses cleanly from ``bundles/agent/run_phase.yaml``
  - has 7 nodes + 6 edges (6 phase + loop.back)
  - every sub_spec_ref points to a loadable bundle
  - drives end-to-end through NodeGraphDriver with a stub SubgraphRunner
    that emits pre-canned typed PhaseOutputs per binding_edge

Compatibility shim (ADR §11 P8 delete-when): old
``bundles/declarative-phase-graph.yaml`` stays in place. Production
profiles still drive ``think.yaml`` until a profile swap lands;
P10 deletes the compat path.

This test asserts the bundle shape + an end-to-end drive, but does
not depend on the production interpreter being upgraded to drive
``agent.run.phase`` as the top-level graph (that's part of the
P8 deliverable but lives behind the runtime entry point — not
exercised in this e2e).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.atoms.enums.enums import ActionType, ReflectionVerdict
from lca.contracts.harness.act.effect_receipt import (
    EffectOutcome,
    EffectReceipt,
)
from lca.contracts.models.cognition.boundary import (
    MemoryReceipt,
    StopPayload,
)
from lca.contracts.models.core.execution.decision import (
    Decision,
    Observation,
    Reflection,
)
from lca.contracts.models.core.perceive.perception import (
    ContextItem,
    ContextManifest,
)
from lca.contracts.models.core.policy.stop import StopDecision, StopReason
from lca.contracts.models.core.state.state import AgentState, Budget
from lca.contracts.protocols.declarative.declarative_1.bundle_graph import (
    BundleGraphNode,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    ExecutionOutcome,
)
from lca.contracts.protocols.declarative.declarative_1.declarative_graph import (
    SubgraphReference,
)
from lca.framework.subgraph.plugins.channel import (
    InMemoryPhaseOutputChannel,
    PhaseOutput,
)
from lca.framework.subgraph.plugins.node_graph_driver import NodeGraphDriver
from lca.harness.declarative.compile.subgraph_resolver import (
    _load_bundle_graph_spec,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
RUN_PHASE_BUNDLE = "bundles/agent/run_phase.yaml"


def _state() -> AgentState:
    return AgentState(trace_id="t", task="ping", budget=Budget())


# Per-binding-edge stub outputs. Each sub_spec_ref node carries
# ``binding_edge: <outer_node_id>`` matching its node id; the stub
# SubgraphRunner returns one of these typed PhaseOutputs.
_STUB_OUTPUTS: dict[str, PhaseOutput] = {
    "perceive.turn": PhaseOutput(
        observation=Observation(
            observation_id="obs_perceive",
            success=True,
            payload=ContextManifest(
                items=(
                    ContextItem(
                        kind="memory",
                        payload="stub",
                        provenance="perceive",
                    ),
                )
            ),
        )
    ),
    "reason.turn": PhaseOutput(
        decision=Decision(
            decision_id="dec_reason",
            action_type=ActionType.RESPOND.value,
            rationale="stub",
            confidence=1.0,
            response_text="ok",
        )
    ),
    "act.turn": PhaseOutput(
        response=None,
        observation=Observation(
            observation_id="obs_act",
            success=True,
            payload=None,
        ),
    ),
    "reflect.turn": PhaseOutput(
        reflection=Reflection(
            reflection_id="refl_stub",
            verdict=ReflectionVerdict.ON_TRACK,
            lesson="stub",
        )
    ),
    "remember.turn": PhaseOutput(
        decision=None,
        observation=None,
        reflection=None,
        response=None,
    ),
    "stop.decide": PhaseOutput(
        decision=Decision(
            decision_id="dec_stop",
            action_type=ActionType.RESPOND.value,
            rationale="stub",
            confidence=1.0,
        ),
        observation=Observation(observation_id="obs_stop", success=True, payload=None),
        reflection=Reflection(reflection_id="refl_stop", verdict=ReflectionVerdict.ON_TRACK),
    ),
    "loop.back": PhaseOutput(
        decision=None,
        observation=None,
        reflection=None,
        response=None,
    ),
}


@dataclass
class _RunPhaseSubRunner:
    """Stub: emits the per-binding-edge typed PhaseOutput.

    Records each ``binding_edge`` it sees so the test can assert the
    outer driver visited all 6 phase nodes + the ``loop.back`` inline.
    """

    calls: list[str] = field(default_factory=list)

    async def run(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        channel: InMemoryPhaseOutputChannel,
    ) -> tuple[AgentState, PhaseOutput]:
        self.calls.append(ref.binding_edge)
        output = _STUB_OUTPUTS.get(ref.binding_edge)
        if output is None:
            return outer_state, PhaseOutput()
        channel.publish(
            producer_node=ref.binding_edge,
            phase="agent",
            output=output,
        )
        return outer_state, output


@dataclass
class _StaticScope:
    def resolve(self, capability: str) -> Any:
        return None

    def resolve_capability(self, capability: str) -> Any:
        return None

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        del factory, region
        return None


class TestRunPhaseBundleTopology:
    """ADR §3.4 + §11 P8 acceptance: bundle structure invariants."""

    def test_bundle_yaml_resolves_to_seven_node_six_edge_graph(self) -> None:
        spec = _load_bundle_graph_spec(RUN_PHASE_BUNDLE)
        assert spec.id == "agent.run.phase"
        assert spec.region == "agent"
        assert len(spec.nodes) == 7
        assert len(spec.edges) == 6

    def test_six_phase_nodes_are_sub_spec_ref_delegates(self) -> None:
        """The 6 phase nodes (perceive / reason / act / reflect /
        remember / stop) all use sub_spec_ref to delegate to a
        agent.<phase>.turn graph. Only ``loop.back`` is inline.
        """
        spec = _load_bundle_graph_spec(RUN_PHASE_BUNDLE)
        phase_ids = {
            "perceive.turn",
            "reason.turn",
            "act.turn",
            "reflect.turn",
            "remember.turn",
            "stop.decide",
        }
        phase_nodes = [n for n in spec.nodes if n.id in phase_ids]
        assert len(phase_nodes) == 6
        for node in phase_nodes:
            assert isinstance(node, BundleGraphNode)
            assert node.sub_spec_ref is not None, (
                f"ADR-0220 §3.4 violated: agent.run.phase node {node.id!r} missing sub_spec_ref."
            )
            assert node.sub_spec_ref.plan_ref.startswith("bundles/agent/"), node
            assert node.sub_spec_ref.binding_edge == node.id

    def test_loop_back_is_inline_passthrough(self) -> None:
        """``loop.back`` is the only inline node — a passthrough typed
        StopPayload projection that lets the driver check ``should_stop``.
        """
        spec = _load_bundle_graph_spec(RUN_PHASE_BUNDLE)
        loop_node = next(n for n in spec.nodes if n.id == "loop.back")
        assert loop_node.sub_spec_ref is None

    def test_topological_order_matches_adr_3_4(self) -> None:
        """Six phase nodes in order perceive → reason → act → reflect →
        remember → stop, then loop.back as the terminator."""
        spec = _load_bundle_graph_spec(RUN_PHASE_BUNDLE)
        node_ids = {n.id for n in spec.nodes}
        assert node_ids == {
            "perceive.turn",
            "reason.turn",
            "act.turn",
            "reflect.turn",
            "remember.turn",
            "stop.decide",
            "loop.back",
        }
        incoming: dict[str, set[str]] = {nid: set() for nid in node_ids}
        for edge in spec.edges:
            incoming[edge.target].add(edge.source)

        assert incoming["reason.turn"] == {"perceive.turn"}
        assert incoming["act.turn"] == {"reason.turn"}
        assert incoming["reflect.turn"] == {"act.turn"}
        assert incoming["remember.turn"] == {"reflect.turn"}
        assert incoming["stop.decide"] == {"remember.turn"}
        assert incoming["loop.back"] == {"stop.decide"}
        assert incoming["perceive.turn"] == set()

    def test_all_six_phase_sub_spec_ref_plan_refs_resolve(self) -> None:
        """Each phase's sub_spec_ref.plan_ref points to a loadable bundle."""
        spec = _load_bundle_graph_spec(RUN_PHASE_BUNDLE)
        for node in spec.nodes:
            if node.sub_spec_ref is None:
                continue
            inner = _load_bundle_graph_spec(node.sub_spec_ref.plan_ref)
            assert inner.nodes, f"{node.sub_spec_ref.plan_ref} has no nodes"


class TestRunPhaseE2E:
    """End-to-end drive: agent.run.phase walks all 7 nodes."""

    @pytest.mark.asyncio
    async def test_run_phase_drives_through_seven_nodes(self) -> None:
        spec = _load_bundle_graph_spec(RUN_PHASE_BUNDLE)
        driver = NodeGraphDriver(
            spec=spec,
            plan_ref=RUN_PHASE_BUNDLE,
            scope=_StaticScope(),
            sub_runner=_RunPhaseSubRunner(),
            channel_factory=InMemoryPhaseOutputChannel,
        )

        sub_runner = _RunPhaseSubRunner()
        channel = InMemoryPhaseOutputChannel()
        driver = NodeGraphDriver(
            spec=spec,
            plan_ref=RUN_PHASE_BUNDLE,
            scope=_StaticScope(),
            sub_runner=sub_runner,
            channel_factory=InMemoryPhaseOutputChannel,
        )

        result = await driver.run(
            outer_state=_state(),
            channel=channel,
            artifacts={},
            outer_input=None,
        )

        assert result.output.outcome_kind is not ExecutionOutcome.FAILED
        assert result.output.error is None

        # All 6 phase nodes delegated through sub_runner (sub_spec_ref)
        # in topological order. ``loop.back`` is inline — the driver
        # calls it directly without going through sub_runner.
        assert sub_runner.calls == [
            "perceive.turn",
            "reason.turn",
            "act.turn",
            "reflect.turn",
            "remember.turn",
            "stop.decide",
        ], f"sub_runner visited out of order: {sub_runner.calls}"


# silence unused-import warning for typed DTOs imported for stub wiring
_ = (EffectOutcome, EffectReceipt, MemoryReceipt, StopPayload, StopDecision, StopReason)
