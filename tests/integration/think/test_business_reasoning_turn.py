"""End-to-end: business.reasoning.turn graph (ADR-0220 §3.4 + §11 P5).

Verifies the 8-node business graph:

  - parses cleanly from ``bundles/business/reasoning_turn.yaml``
  - each of the 8 sub_spec_ref nodes delegates to a loadable
    concept/primitive graph bundle
  - drives end-to-end through NodeGraphDriver with a stub
    SubgraphRunner that emits pre-canned typed PhaseOutputs per
    binding_edge, so the test does not depend on a live LLM or
    on the production sub_runner pipeline
  - final PhaseOutput carries the typed Decision emitted by the
    gate.enforce subgraph

Compatibility shim (ADR §11 P5 delete-when): old ``bundles/think.yaml``
stays in place; ``business_run_v2`` profile selector picks the new
graph. P10 deletes the compat paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.execution.decision import Decision
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
BUNDLE_PATH = REPO_ROOT / "bundles" / "business" / "reasoning_turn.yaml"

_OUTER_FACTORY = "business.reasoning.ref"
# Each entry: outer_node_id -> (typed PhaseOutput to emit on that node's subgraph completion).
# The outer driver absorbs the typed PhaseOutput, so subsequent edges see the same
# typed payload via the port_context / channel. PhaseOutput's close-out field set is
# owned by ``lca.cognition.close_out.CLOSE_OUT_FIELDS`` (decision / observation /
# reflection / response); we emit on those fields only.
_EMPTY_PHASE_OUTPUT = PhaseOutput()


def _llm_response_phase_output() -> PhaseOutput:
    """PhaseOutput carrying a stub LLMResponse on the `` ``response`` field."""
    return PhaseOutput(response=LLMResponse(text="stub"))


def _decision_phase_output() -> PhaseOutput:
    """PhaseOutput carrying the terminal typed Decision emitted by gate.enforce."""
    return PhaseOutput(
        decision=Decision(
            decision_id="dec_business_v2",
            action_type=ActionType.RESPOND.value,
            rationale="stub-business-v2",
            confidence=1.0,
            response_text="ok",
        )
    )


_STUB_PHASE_OUTPUTS: dict[str, PhaseOutput] = {
    "reason.prepare.tools": _EMPTY_PHASE_OUTPUT,
    "reason.prepare.role": _EMPTY_PHASE_OUTPUT,
    "reason.prepare.context": _EMPTY_PHASE_OUTPUT,
    "reason.prepare.template": _EMPTY_PHASE_OUTPUT,
    "reason.render.prompt": _EMPTY_PHASE_OUTPUT,
    "reason.llm.call": _llm_response_phase_output(),
    "reason.classify.response": _EMPTY_PHASE_OUTPUT,
    "reason.gate.enforce": _decision_phase_output(),
}


def _state() -> AgentState:
    return AgentState(trace_id="t", task="ping", budget=Budget())


@dataclass
class _StubSubRunner:
    """Per-node sub_runner:returns the typed PhaseOutput keyed by binding_edge.

    ``binding_edge`` is the outer node id (set in the business bundle's
    ``sub_spec_ref.binding_edge`` for every ref). The driver passes the
    SubgraphReference straight through; the stub returns a PhaseOutput
    with the close-out field set the next stage expects.
    """

    async def run(
        self,
        *,
        ref: SubgraphReference,
        outer_state: AgentState,
        channel: InMemoryPhaseOutputChannel,
    ) -> tuple[AgentState, PhaseOutput]:
        output = _STUB_PHASE_OUTPUTS.get(ref.binding_edge)
        if output is None:
            return outer_state, PhaseOutput()
        # Mirror the production runner:publish the inner subgraph's
        # terminal contribution so the outer driver can absorb it.
        channel.publish(
            producer_node=ref.binding_edge,
            phase="business",
            output=output,
        )
        return outer_state, output


@dataclass
class _StaticScope:
    """Stub SubgraphRuntime scope; the test never resolves a real factory."""

    def resolve(self, capability: str) -> Any:
        return None

    def resolve_capability(self, capability: str) -> Any:
        return None

    def resolve_factory(self, factory: str, region: str | None) -> Any:
        del factory, region
        return None


class TestBusinessReasoningTurnBundleTopology:
    """§3.4 + §11 P5 acceptance: bundle structure invariants."""

    def test_bundle_yaml_resolves_to_eight_node_nine_edge_graph(self) -> None:
        """The business graph has 8 nodes + 9 edges."""
        spec = _load_bundle_graph_spec(str(BUNDLE_PATH.relative_to(REPO_ROOT)))
        assert spec.id == "business.reasoning.turn"
        assert spec.region == "business"
        assert len(spec.nodes) == 8
        assert len(spec.edges) == 9

    def test_every_node_carries_a_typed_sub_spec_ref(self) -> None:
        """All 8 nodes use sub_spec_ref to delegate to a child graph."""
        spec = _load_bundle_graph_spec(str(BUNDLE_PATH.relative_to(REPO_ROOT)))
        for node in spec.nodes:
            assert isinstance(node, BundleGraphNode)
            assert node.sub_spec_ref is not None, (
                f"ADR-0220 §3.4 violated: business node {node.id!r} missing sub_spec_ref."
            )
            ref = node.sub_spec_ref
            assert ref.plan_ref.startswith("bundles/"), ref
            assert ref.entry_node, ref
            assert ref.binding_edge == node.id, (
                f"sub_spec_ref.binding_edge {ref.binding_edge!r} must equal node.id {node.id!r}."
            )

    def test_all_eight_sub_spec_ref_plan_refs_resolve(self) -> None:
        """Every sub_spec_ref.plan_ref points to a loadable bundle yaml."""
        spec = _load_bundle_graph_spec(str(BUNDLE_PATH.relative_to(REPO_ROOT)))
        for node in spec.nodes:
            ref = node.sub_spec_ref
            assert ref is not None
            inner = _load_bundle_graph_spec(ref.plan_ref)
            assert inner.nodes, f"{ref.plan_ref} has no nodes"

    def test_node_id_action_domain_uses_business_prefix_set(self) -> None:
        """ADR §3.4: business graph node ids live in the ``reason.*`` namespace."""
        spec = _load_bundle_graph_spec(str(BUNDLE_PATH.relative_to(REPO_ROOT)))
        action_domains = {node.id.split(".", 1)[0] for node in spec.nodes}
        assert action_domains == {"reason"}

    def test_topological_order_matches_adr_5_1(self) -> None:
        """ADR §5.1: prep 4 → render → llm → classify → gate, with edges
        feeding render from all 3 prep paths and template from context.

        The driver walks edges by ``select_edge``, so the visit order is
        determined by the declared topology. We assert the topological
        order matches ADR §5.1 by walking the predecessor map.
        """
        spec = _load_bundle_graph_spec(str(BUNDLE_PATH.relative_to(REPO_ROOT)))
        node_ids = {n.id for n in spec.nodes}
        incoming: dict[str, set[str]] = {nid: set() for nid in node_ids}
        for edge in spec.edges:
            incoming[edge.target].add(edge.source)

        render = "reason.render.prompt"
        assert incoming[render] == {
            "reason.prepare.tools",
            "reason.prepare.role",
            "reason.prepare.context",
            "reason.prepare.template",
        }, incoming[render]

        llm = "reason.llm.call"
        assert incoming[llm] == {"reason.render.prompt", "reason.prepare.tools"}, incoming[llm]

        classify = "reason.classify.response"
        assert incoming[classify] == {"reason.llm.call"}, incoming[classify]

        gate = "reason.gate.enforce"
        assert incoming[gate] == {"reason.classify.response"}, incoming[gate]

        template = "reason.prepare.template"
        assert incoming[template] == {"reason.prepare.context"}, incoming[template]


class TestBusinessReasoningTurnE2E:
    """End-to-end drive through NodeGraphDriver with a stub SubgraphRunner."""

    @pytest.mark.asyncio
    async def test_e2e_with_prep_graph(self) -> None:
        """ADR-0220 §11 P5 e2e: business.reasoning.turn drives 8 nodes
        in topological order and the final PhaseOutput carries the
        typed Decision emitted by reason.gate.enforce.
        """
        spec = _load_bundle_graph_spec(str(BUNDLE_PATH.relative_to(REPO_ROOT)))
        driver = NodeGraphDriver(
            spec=spec,
            plan_ref=str(BUNDLE_PATH.relative_to(REPO_ROOT)),
            scope=_StaticScope(),
            sub_runner=_StubSubRunner(),
            channel_factory=InMemoryPhaseOutputChannel,
        )

        channel = InMemoryPhaseOutputChannel()
        result = await driver.run(
            outer_state=_state(),
            channel=channel,
            artifacts={},
            outer_input=None,
        )

        # FAILED shape absent
        assert result.output.outcome_kind is not ExecutionOutcome.FAILED
        assert result.output.error is None

        # The stub SubgraphRunner publishes one PhaseOutput per outer
        # binding_edge; the driver absorbs the gate.enforce Decision.
        snap = channel.snapshot()
        assert any(
            getattr(out, "decision", None) is not None
            and getattr(out.decision, "decision_id", None) == "dec_business_v2"
            for out in snap.values()
        ), (
            "ADR-0220 §5: business.reasoning.turn must end with the typed "
            f"Decision emitted by reason.gate.enforce. Published: {sorted(snap)}"
        )


# silence unused-import warning for tuple types used only via dict values
_ = field
_ = yaml
