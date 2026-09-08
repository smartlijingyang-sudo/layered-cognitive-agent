"""think sub-graph: compile + node unit + runner tests.

Covers expose → reason → classify → guard with LCA classifier semantics
mapped to lab action_type (use_tool → call_tool). No adapter layer.
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


def _classify_node(**config):
    from agent_lab.nodes.think.classify.plugin import ThinkClassify

    node = ThinkClassify.__new__(ThinkClassify)
    node.config = {"from": "response", "to": "decision", **config}
    node.outs = ["decision"]
    return node


def _guard_node(**config):
    from agent_lab.nodes.think.guard.plugin import ThinkGuard

    node = ThinkGuard.__new__(ThinkGuard)
    node.config = {"from": "decision", "to": "enforced_decision", **config}
    node.outs = ["enforced_decision", "think_signal"]
    return node


def _decision_art(**overrides):
    content = {
        "decision_id": "dec_x",
        "action_type": "respond",
        "rationale": "",
        "confidence": 1.0,
        "tool_calls": [],
    }
    content.update(overrides)
    return Artifact(kind=ArtifactKind.FACT, content=content, schema_ref="decision.v1")


# ---------------------------------------------------------------------------
# (1) graph load + compile
# ---------------------------------------------------------------------------


def test_think_subgraph_loads_and_compiles() -> None:
    specs = load_registry("perceive", "think", "agent_loop", "model_eye", "act")
    assert "think" in specs
    spec = specs["think"]
    assert {n.id for n in spec.nodes} == {"expose", "reason", "classify", "guard"}
    bundle = compile_spec(spec, sub_registry=specs)
    assert bundle.spec_id == "think"
    flat = [nid for layer in bundle.layers for nid in layer]
    assert flat.index("expose") < flat.index("reason")
    assert flat.index("reason") < flat.index("classify")
    assert flat.index("classify") < flat.index("guard")


def test_think_expose_peels_committed_messages_and_tools() -> None:
    from agent_lab.nodes.think.expose.plugin import ThinkExpose

    node = ThinkExpose.__new__(ThinkExpose)
    node.config = {"from": "in_assembled_manifest", "to": "messages", "tools_to": "tools"}
    node.outs = ["messages", "tools"]
    messages = [{"role": "user", "content": "hi"}]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "run",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    out = node.execute(
        node,
        {
            "in_assembled_manifest": Artifact(
                kind=ArtifactKind.MANIFEST,
                content={
                    "messages": messages,
                    "tools": tools,
                    "digest": "abc",
                    "committed": True,
                    "schema_version": "context.manifest.v1",
                },
                schema_ref="context.manifest.v1",
            )
        },
    )
    assert out["messages"].kind == ArtifactKind.MESSAGE
    assert out["messages"].content == messages
    assert out["messages"].schema_ref == "openai.messages.v1"
    assert out["tools"].kind == ArtifactKind.FACT
    assert out["tools"].content == tools
    assert out["tools"].schema_ref == "openai.tools.v1"


def test_think_expose_rejects_uncommitted_manifest() -> None:
    from agent_lab.nodes.think.expose.plugin import ThinkExpose

    node = ThinkExpose.__new__(ThinkExpose)
    node.config = {}
    node.outs = ["messages"]
    try:
        node.execute(
            node,
            {
                "in_assembled_manifest": Artifact(
                    kind=ArtifactKind.MANIFEST,
                    content={
                        "messages": [{"role": "user", "content": "hi"}],
                        "digest": "abc",
                        "committed": False,
                    },
                    schema_ref="context.manifest.v1",
                )
            },
        )
        raise AssertionError("expected ValueError for uncommitted manifest")
    except ValueError as exc:
        assert "committed" in str(exc)


def test_think_expose_rejects_missing_messages() -> None:
    from agent_lab.nodes.think.expose.plugin import ThinkExpose

    node = ThinkExpose.__new__(ThinkExpose)
    node.config = {}
    node.outs = ["messages"]
    try:
        node.execute(
            node,
            {
                "in_assembled_manifest": Artifact(
                    kind=ArtifactKind.MANIFEST,
                    content={"digest": "abc", "committed": True},
                    schema_ref="context.manifest.v1",
                )
            },
        )
        raise AssertionError("expected ValueError for missing messages")
    except ValueError as exc:
        assert "messages" in str(exc)


def test_agent_loop_compiles_with_think_sub_spec() -> None:
    specs = load_registry("perceive", "think", "agent_loop", "model_eye", "act")
    agent_loop = specs["agent_loop"]
    think_node = agent_loop.node("think")
    assert "in_assembled_manifest" in think_node.ins
    assert "perceive_out" in think_node.ins
    assert "tools" not in think_node.ins
    assert "in_state" in think_node.ins
    assert "decision_out" in think_node.outs
    assert "think_signal" in think_node.outs
    local_ids = {n.id for n in agent_loop.nodes}
    assert "flatten_manifest" not in local_ids
    assert "call_llm_node" not in local_ids
    assert "parse_decision" not in local_ids
    think_links = [link for link in agent_loop.sub_specs if link.node_id == "think"]
    assert len(think_links) == 1
    link = think_links[0]
    assert link.sub_spec_id == "think"
    assert link.input_map == {
        "in_assembled_manifest": "in_assembled_manifest",
        "perceive_out": "perceive_out",
        "in_state": "in_state",
    }
    assert link.output_map == {
        "enforced_decision": "decision_out",
        "think_signal": "think_signal",
    }
    compile_spec(agent_loop, sub_registry=specs)


# ---------------------------------------------------------------------------
# (2) classify — DefaultDecisionClassifier → lab action_type
# ---------------------------------------------------------------------------


def test_think_classify_response_to_decision() -> None:
    node = _classify_node()
    out = node.execute(
        node,
        {
            "response": Artifact(
                kind=ArtifactKind.MESSAGE,
                content={"text": "hello", "tool_calls": []},
            )
        },
    )
    assert out["decision"].schema_ref == "decision.v1"
    assert out["decision"].content["action_type"] == "respond"
    assert out["decision"].content["response_text"] == "hello"


def test_think_classify_maps_use_tool_to_call_tool() -> None:
    node = _classify_node()
    out = node.execute(
        node,
        {
            "response": Artifact(
                kind=ArtifactKind.MESSAGE,
                content={
                    "text": "",
                    "tool_calls": [
                        {"id": "tc_1", "name": "bash", "arguments": {"command": "ls"}},
                    ],
                },
            )
        },
    )
    assert out["decision"].content["action_type"] == "call_tool"
    assert out["decision"].content["tool_calls"][0]["name"] == "bash"
    assert out["decision"].content["tool_calls"][0]["arguments"] == {"command": "ls"}


def test_think_classify_recovers_leaked_tool_call() -> None:
    node = _classify_node()
    out = node.execute(
        node,
        {
            "response": Artifact(
                kind=ArtifactKind.MESSAGE,
                content={
                    "text": '[Tool call: bash]\n{"command": "ls"}',
                    "tool_calls": [],
                },
            )
        },
    )
    decision = out["decision"].content
    assert decision["action_type"] == "call_tool"
    assert decision["tool_calls"][0]["name"] == "bash"
    assert decision["tool_calls"][0]["arguments"] == {"command": "ls"}


def test_think_classify_delegate_tool() -> None:
    node = _classify_node()
    out = node.execute(
        node,
        {
            "response": Artifact(
                kind=ArtifactKind.MESSAGE,
                content={
                    "text": "",
                    "tool_calls": [
                        {
                            "id": "tc_d",
                            "name": "delegate",
                            "arguments": {
                                "subtask": "research",
                                "target_role": "analyst",
                            },
                        }
                    ],
                },
            )
        },
    )
    decision = out["decision"].content
    assert decision["action_type"] == "delegate"
    assert decision["delegations"]
    assert decision["delegations"][0]["subtask"] == "research"


def test_think_classify_empty_response_is_low_confidence_respond() -> None:
    node = _classify_node()
    out = node.execute(
        node,
        {
            "response": Artifact(
                kind=ArtifactKind.MESSAGE,
                content={"text": "", "tool_calls": []},
            )
        },
    )
    decision = out["decision"].content
    assert decision["action_type"] == "respond"
    assert decision["confidence"] == 0.0
    assert decision["response_text"]


# ---------------------------------------------------------------------------
# (3) guard — fail-loud + explicit null + state
# ---------------------------------------------------------------------------


def test_think_guard_emits_decision_and_signal() -> None:
    node = _guard_node(null_gate=True)
    out = node.execute(node, {"decision": _decision_art(decision_id="dec_x")})
    assert out["enforced_decision"].content["decision_id"] == "dec_x"
    assert out["think_signal"].schema_ref == "think.signal.v1"
    assert out["think_signal"].content["decision_id"] == "dec_x"
    assert out["think_signal"].content.get("gate") == "null"


def test_think_guard_rejects_silent_identity() -> None:
    node = _guard_node()
    try:
        node.execute(node, {"decision": _decision_art()})
        raise AssertionError("expected ValueError for missing gate config")
    except ValueError as exc:
        assert "null_gate" in str(exc) or "gate" in str(exc).lower()


def test_think_guard_rejects_empty_chain() -> None:
    node = _guard_node(
        gate_factory={
            "ref": "lca.cognition.brain.decision_gates.chained.chained:ChainedDecisionGate",
            "kwargs": {},
        }
    )
    try:
        node.execute(node, {"decision": _decision_art()})
        raise AssertionError("expected ValueError for empty gate chain")
    except ValueError as exc:
        assert "empty" in str(exc).lower() or "chain" in str(exc).lower()


def test_think_guard_resolves_factory_with_members() -> None:
    class _PassGate:
        async def enforce(self, state, decision):  # type: ignore[no-untyped-def]
            return decision

    node = _guard_node(
        gate_factory={
            "ref": "lca.cognition.brain.decision_gates.chained.chained:ChainedDecisionGate",
            "kwargs": {},
            "gates": [_PassGate()],
        }
    )
    out = node.execute(node, {"decision": _decision_art(decision_id="dec_m")})
    assert out["enforced_decision"].content["decision_id"] == "dec_m"
    assert out["think_signal"].content.get("gate") == "ChainedDecisionGate"


def test_think_guard_passes_state() -> None:
    from agent_lab.nodes.think.guard.plugin import (
        register_fixture_gate,
        unregister_fixture_gate,
    )

    name = "test-think-gate-sees-state"
    seen: dict[str, object] = {}

    class _CaptureGate:
        async def enforce(self, state, decision):  # type: ignore[no-untyped-def]
            seen["state"] = state
            seen["decision_id"] = decision.decision_id
            return decision

    register_fixture_gate(name, _CaptureGate())
    try:
        node = _guard_node(fixture_gate_name=name)
        node.execute(
            node,
            {
                "decision": _decision_art(decision_id="dec_s"),
                "in_state": Artifact(
                    kind=ArtifactKind.FACT,
                    content={"trace_id": "tr_1", "task": "t", "step": 3},
                    schema_ref="agent_state.v1",
                ),
            },
        )
        assert seen["decision_id"] == "dec_s"
        state = seen["state"]
        assert state is not None
        assert getattr(state, "trace_id", None) == "tr_1"
        assert getattr(state, "step", None) == 3
    finally:
        unregister_fixture_gate(name)


def test_think_guard_fixture_rewrites_decision() -> None:
    from agent_lab.nodes.think.guard.plugin import (
        register_fixture_gate,
        unregister_fixture_gate,
    )

    name = "test-think-gate-rewrite"

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
        node = _guard_node(fixture_gate_name=name)
        out = node.execute(node, {"decision": _decision_art(decision_id="dec_in")})
        assert out["enforced_decision"].content["decision_id"] == "dec_rewritten"
        assert out["enforced_decision"].content["action_type"] == "refuse"
        assert out["think_signal"].content["decision_id"] == "dec_rewritten"
    finally:
        unregister_fixture_gate(name)


# ---------------------------------------------------------------------------
# (4) reason passes tools
# ---------------------------------------------------------------------------


def test_think_reason_passes_tools_to_adapter(monkeypatch) -> None:
    import agent_lab.nodes.think.reason.plugin as reason_mod
    from agent_lab.nodes.think.reason.plugin import ThinkReason

    captured: dict[str, object] = {}

    class _CaptureAdapter:
        def __init__(self, **kwargs):  # type: ignore[no-untyped-def]
            del kwargs

        async def complete(self, prompt: str, **kwargs):  # type: ignore[no-untyped-def]
            captured["prompt"] = prompt
            captured["tools"] = kwargs.get("tools")
            from lca.contracts.models.core.conversation.llm import LLMResponse

            return LLMResponse(text="ok", model="cap", tool_calls=[])

    monkeypatch.setattr(reason_mod, "OpenAICompatAdapter", _CaptureAdapter)

    node = ThinkReason.__new__(ThinkReason)
    node.config = {"from": "messages", "to": "response"}
    node.outs = ["response"]
    tools = [
        {
            "type": "function",
            "function": {
                "name": "bash",
                "description": "run",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    out = node.execute(
        node,
        {
            "messages": Artifact(
                kind=ArtifactKind.MESSAGE,
                content=[{"role": "user", "content": "hi"}],
                schema_ref="openai.messages.v1",
            ),
            "tools": Artifact(
                kind=ArtifactKind.FACT,
                content=tools,
                schema_ref="openai.tools.v1",
            ),
        },
    )
    assert out["response"].content["text"] == "ok"
    passed = captured["tools"]
    assert isinstance(passed, list) and len(passed) == 1
    assert getattr(passed[0], "name") == "bash"
    assert getattr(passed[0], "description") == "run"


# ---------------------------------------------------------------------------
# (5) control think_guard passthrough
# ---------------------------------------------------------------------------


def test_control_think_guard_passthrough_by_default() -> None:
    from agent_lab.nodes.control.think_guard.plugin import ThinkGuardNode

    node = ThinkGuardNode.__new__(ThinkGuardNode)
    node.config = {"to": "out_decision", "provider_config": {"mode": "passthrough"}}
    node.outs = ["out_decision"]
    inbound = _decision_art(decision_id="dec_p")
    out = node.execute(node, {"in_decision": inbound})
    assert out["out_decision"].content["decision_id"] == "dec_p"


# ---------------------------------------------------------------------------
# (6) runner integration
# ---------------------------------------------------------------------------


def test_think_subgraph_runs_via_runner(monkeypatch) -> None:
    import agent_lab.nodes.think.reason.plugin as reason_mod
    from agent_lab.runtime.runner import run as run_graph
    from tests.agent_lab.fixtures.llm_stub import StubLlmAdapter

    monkeypatch.setattr(reason_mod, "OpenAICompatAdapter", StubLlmAdapter)

    specs = load_registry("think")
    think_spec = specs["think"]

    initial = {
        "in_assembled_manifest": Artifact(
            kind=ArtifactKind.MANIFEST,
            content={
                "messages": [{"role": "user", "content": "hi"}],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "bash",
                            "description": "run",
                            "parameters": {"type": "object"},
                        },
                    }
                ],
                "digest": "x",
                "committed": True,
                "schema_version": "context.manifest.v1",
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
    assert decision.content["action_type"] in {
        "respond",
        "call_tool",
        "refuse",
        "delegate",
    }
    assert "think_signal" in trace.final_artifacts
    assert trace.final_artifacts["think_signal"].content.get("gate") == "null"
