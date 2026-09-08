"""think sub-graph wiring + adapter + node tests.

Covers:
  - think.yaml loads + compiles without validation errors
  - agent_loop.yaml (with think as a sub_spec host) loads + compiles
  - LcaThinkParseProvider turns an LLMResponse artifact into a Decision
    artifact (heuristic; default parser)
  - LcaThinkGateProvider enforces a Decision via DecisionGate (identity
    gate by default; fixture_gate_name for tests)
  - The full sub-graph runs via agent_lab's runner

Fixtures use NullPerceiveHub + identity gate + heuristic parser; this
test does not depend on a live LCA runtime or LLM API.
"""

from __future__ import annotations

import sys
from pathlib import Path

from agent_lab.graph.compile import compile as compile_spec
from agent_lab.graphs import load_registry
from agent_lab.primitives.artifact import Artifact, ArtifactKind

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_think_subgraph_loads_and_compiles() -> None:
    specs = load_registry("perceive", "think", "agent_loop", "mv_assemble", "effect_dispatch")
    assert "think" in specs
    spec = specs["think"]
    assert {n.id for n in spec.nodes} == {"flatten", "llm", "parse", "gate_enforce"}
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "think"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("flatten") < flat.index("llm")
    assert flat.index("llm") < flat.index("parse")
    assert flat.index("parse") < flat.index("gate_enforce")


def test_agent_loop_compiles_with_think_sub_spec() -> None:
    specs = load_registry("perceive", "think", "agent_loop", "mv_assemble", "effect_dispatch")
    agent_loop = specs["agent_loop"]
    # think node now declares in_assembled_manifest + perceive_out as ins
    think_node = agent_loop.node("think")
    assert "in_assembled_manifest" in think_node.ins
    assert "perceive_out" in think_node.ins
    assert "decision_out" in think_node.outs
    assert "think_signal" in think_node.outs
    # The three previous local workers (flatten_manifest / call_llm_node /
    # parse_decision) must have moved into think.yaml.
    local_ids = {n.id for n in agent_loop.nodes}
    assert "flatten_manifest" not in local_ids
    assert "call_llm_node" not in local_ids
    assert "parse_decision" not in local_ids
    # Sub-spec mount exists
    think_links = [link for link in agent_loop.sub_specs if link.node_id == "think"]
    assert len(think_links) == 1
    link = think_links[0]
    assert link.sub_spec_id == "think"
    assert link.input_map == {
        "in_assembled_manifest": "in_assembled_manifest",
        "perceive_out": "perceive_out",
    }
    assert link.output_map == {
        "enforced_decision": "decision_out",
        "think_signal": "think_signal",
    }
    compile_spec(agent_loop, sub_registry=specs)


# ---------------------------------------------------------------------------
# (2) parse provider
# ---------------------------------------------------------------------------


def test_lca_think_parse_provider_default() -> None:
    """Default heuristic turns text → Decision(action_type='respond')."""
    from agent_lab.adapters.lca_think import LcaThinkParseProvider

    provider = LcaThinkParseProvider.from_node_config({})
    response_artifact = Artifact(
        kind=ArtifactKind.MESSAGE,
        content={"text": "hello world", "tool_calls": []},
    )
    out = provider.parse(response_artifact)
    assert "decision" in out
    decision = out["decision"]
    assert decision.kind == ArtifactKind.FACT
    assert decision.schema_ref == "decision.v1"
    assert decision.content["action_type"] == "respond"
    assert decision.content["response_text"] == "hello world"
    assert decision.content["decision_id"]


def test_lca_think_parse_provider_with_tool_call() -> None:
    """Tool calls → action_type='call_tool'."""
    from agent_lab.adapters.lca_think import LcaThinkParseProvider

    provider = LcaThinkParseProvider.from_node_config({})
    response_artifact = Artifact(
        kind=ArtifactKind.MESSAGE,
        content={
            "text": "",
            "tool_calls": [
                {"id": "tc_1", "name": "bash", "args": {"command": "ls"}},
            ],
        },
    )
    out = provider.parse(response_artifact)
    decision = out["decision"]
    assert decision.content["action_type"] == "call_tool"
    assert decision.content["tool_calls"][0]["name"] == "bash"
    assert decision.content["tool_calls"][0]["arguments"] == {"command": "ls"}


def test_lca_think_parse_provider_with_fixture_parser() -> None:
    """fixture_parser_name overrides the default heuristic."""
    from agent_lab.adapters.lca_think import (
        LcaThinkParseProvider,
        register_fixture_parser,
        unregister_fixture_parser,
    )

    name = "test-think-parse-fixture"

    async def _custom(response):  # type: ignore[no-untyped-def]
        from lca.contracts.models.core.execution.decision import Decision

        return Decision(
            decision_id="dec_custom",
            action_type="refuse",
            rationale="fixture refused",
            confidence=0.5,
        )

    register_fixture_parser(name, _custom)
    try:
        provider = LcaThinkParseProvider.from_node_config(
            {"provider_config": {"fixture_parser_name": name}}
        )
        response_artifact = Artifact(kind=ArtifactKind.MESSAGE, content={"text": "anything"})
        out = provider.parse(response_artifact)
        assert out["decision"].content["decision_id"] == "dec_custom"
        assert out["decision"].content["action_type"] == "refuse"
    finally:
        unregister_fixture_parser(name)


# ---------------------------------------------------------------------------
# (3) gate provider
# ---------------------------------------------------------------------------


def test_lca_think_gate_provider_identity() -> None:
    """Without fixture / factory, the gate is an identity pass-through."""
    from agent_lab.adapters.lca_think import LcaThinkGateProvider

    provider = LcaThinkGateProvider.from_node_config({})
    decision_artifact = Artifact(
        kind=ArtifactKind.FACT,
        content={
            "decision_id": "dec_in",
            "action_type": "respond",
            "rationale": "in",
            "confidence": 0.9,
            "tool_calls": [],
        },
    )
    out = provider.enforce(decision_artifact=decision_artifact)
    assert "enforced_decision" in out
    assert "think_signal" in out
    enforced = out["enforced_decision"]
    assert enforced.content["decision_id"] == "dec_in"
    assert enforced.content["action_type"] == "respond"
    signal = out["think_signal"]
    assert signal.content["decision_id"] == "dec_in"
    assert signal.schema_ref == "think.signal.v1"


def test_lca_think_gate_provider_with_fixture() -> None:
    """A fixture gate that rewrites the Decision is honored end-to-end."""
    from agent_lab.adapters.lca_think import (
        LcaThinkGateProvider,
        register_fixture_gate,
        unregister_fixture_gate,
    )

    name = "test-think-gate-fixture"

    class _RewriteGate:
        async def enforce(self, state, decision):  # type: ignore[no-untyped-def]
            from lca.contracts.models.core.execution.decision import Decision

            return Decision(
                decision_id="dec_rewritten",
                action_type="refuse",
                rationale=f"gate rewrote {decision.decision_id}",
                confidence=0.1,
            )

    register_fixture_gate(name, _RewriteGate())
    try:
        provider = LcaThinkGateProvider.from_node_config(
            {"provider_config": {"fixture_gate_name": name}}
        )
        decision_artifact = Artifact(
            kind=ArtifactKind.FACT,
            content={
                "decision_id": "dec_in",
                "action_type": "respond",
                "rationale": "",
                "confidence": 1.0,
                "tool_calls": [],
            },
        )
        out = provider.enforce(decision_artifact=decision_artifact)
        enforced = out["enforced_decision"]
        assert enforced.content["decision_id"] == "dec_rewritten"
        assert enforced.content["action_type"] == "refuse"
        assert out["think_signal"].content["decision_id"] == "dec_rewritten"
    finally:
        unregister_fixture_gate(name)


def test_lca_think_gate_provider_resolves_factory_ref() -> None:
    """``module:Class`` factory form resolves a real LCA gate class."""
    from agent_lab.adapters.lca_think import LcaThinkGateProvider

    # ChainedDecisionGate is the standard LCA DecisionGate composite.
    provider = LcaThinkGateProvider.from_node_config(
        {
            "provider_config": {
                "gate_factory": {
                    "ref": "lca.cognition.brain.decision_gates.chained.chained:ChainedDecisionGate",
                    "kwargs": {},
                }
            }
        }
    )
    from lca.cognition.brain.decision_gates.chained.chained import (
        ChainedDecisionGate,
    )

    assert isinstance(provider._gate, ChainedDecisionGate)


# ---------------------------------------------------------------------------
# (4) runner integration
# ---------------------------------------------------------------------------


def test_think_subgraph_runs_via_runner() -> None:
    """The think sub-graph runs end-to-end through agent_lab's runner."""
    from agent_lab.runtime.runner import run as run_graph

    specs = load_registry("perceive", "think", "agent_loop", "mv_assemble", "effect_dispatch")
    think_spec = specs["think"]
    # The default config points call_llm at OpenAICompatAdapter which would
    # need an LLM_API_KEY. For the run path we swap in a no-op LLMAdapter.
    for n in think_spec.nodes:
        if n.id == "llm":
            n.config["provider_config"] = {
                "adapter_factory": {
                    "ref": "tests.agent_lab.fixtures.llm_stub:StubLlmAdapter",
                    "kwargs": {},
                }
            }

    initial = {
        # Manifest carrying the message list (assemble_messages reads
        # `messages` from the manifest content).
        "in_assembled_manifest": Artifact(
            kind=ArtifactKind.MANIFEST,
            content={
                "messages": [{"role": "user", "content": "hi"}],
                "digest": "x",
            },
            schema_ref="context.manifest.v1",
        ),
        "perceive_out": Artifact(
            kind=ArtifactKind.FACT,
            content={"perceived": True},
            schema_ref="perceive.signal.v1",
        ),
    }
    trace = run_graph(think_spec, initial=initial, sub_registry=specs)
    assert "enforced_decision" in trace.final_artifacts, (
        f"think sub-graph must emit enforced_decision; got {sorted(trace.final_artifacts)}"
    )
    decision = trace.final_artifacts["enforced_decision"]
    assert decision.kind == ArtifactKind.FACT
    assert decision.content["action_type"] in {"respond", "call_tool", "refuse"}
    assert "think_signal" in trace.final_artifacts
