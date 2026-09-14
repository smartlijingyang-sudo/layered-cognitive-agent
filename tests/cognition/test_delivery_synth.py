"""Delivery synthesis and material collection tests (ADR-0196)."""

from __future__ import annotations

from lca.cognition.convergence.delivery_synth import synthesize_delivery_response
from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.cognition.convergence.payload import (
    is_substantive_stdout,
    turn_has_delivery_signal,
)
from lca.cognition.convergence.task_class import resolve_task_class
from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision, Observation, ToolCall, Turn
from lca.contracts.models.core.perceive.perception import ContextItem, ContextManifest
from lca.contracts.models.core.perceive.projection import PerceiveProjection
from lca.contracts.models.core.state.state import AgentState, Budget
from tests.support.session_gate_helpers import append_control_turn, bound_session


def test_substantive_stdout_rejects_import_only() -> None:
    assert not is_substantive_stdout("import matplotlib.pyplot as plt")
    assert is_substantive_stdout("图计划笑话：" + "哈" * 48)


def test_synthesize_includes_producer_stdout() -> None:
    with bound_session("delivery-synth-joke"):
        state = AgentState(
            trace_id="t",
            task="用python写一个图计划的笑话",
            budget=Budget(),
        )
        joke = "为什么程序员分不清万圣节和圣诞节？因为 Oct 31 == Dec 25！" + ("（八进制笑话）" * 4)
        append_control_turn(
            state,
            Turn(
                decision=Decision(
                    decision_id="d0",
                    action_type=ActionType.USE_TOOL,
                    rationale="run",
                    confidence=0.9,
                    tool_calls=[ToolCall(call_id="c0", tool_name="executeCode", arguments={})],
                ),
                observation=Observation(
                    observation_id="o0",
                    success=True,
                    payload={"stdout": joke},
                ),
            ),
        )
        evidence = build_delivery_evidence(state)
        assert evidence.satisfied is True
        text = synthesize_delivery_response(state, evidence)
        assert joke in text


def test_resolve_task_class_prefers_manifest_hint() -> None:
    manifest = ContextManifest(
        digest="d",
        items=(
            ContextItem(
                kind="convergence_task_class",
                payload="visual_artifact",
                provenance="test",
            ),
        ),
    )
    state = AgentState(
        trace_id="t",
        task="用python写一个图计划的笑话",
        budget=Budget(),
        perceive=PerceiveProjection(manifest=manifest, digest="d", step=1),
    )
    assert resolve_task_class(state) == "visual_artifact"


# ---------------------------------------------------------------------------
# list-payload support: tools like listFiles return list-of-strings, not
# stdout-shaped strings.  A non-empty list with at least one non-blank entry
# must count as a delivery signal so convergence gates can stop the loop.
# ---------------------------------------------------------------------------


def test_turn_has_delivery_signal_accepts_non_empty_list_payload() -> None:
    assert turn_has_delivery_signal(
        ["/etc/hostname", "/etc/hosts", "/etc/passwd"],
    )


def test_turn_has_delivery_signal_rejects_empty_list_payload() -> None:
    # Empty list conveys "no items" — the model still has to surface
    # that as a final response, so it is not a delivery signal on its own.
    assert not turn_has_delivery_signal([])


def test_turn_has_delivery_signal_rejects_list_of_blanks() -> None:
    # A list whose items are all blank strings is the same shape as ``[]``
    # for delivery purposes — no meaningful entries to surface.
    assert not turn_has_delivery_signal(["", "   ", "\t"])


def test_turn_has_delivery_signal_dict_with_files_key_is_delivery() -> None:
    # Existing contract: ``payload_files_created`` treats ``files_created``
    # / ``files`` keys as a delivery signal (used by writeFile output
    # where the body is a dict like ``{"files": ["report.md"]}``).
    assert turn_has_delivery_signal({"files": ["a", "b"]})
