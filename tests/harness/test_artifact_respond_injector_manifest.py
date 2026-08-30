"""ArtifactRespondInjector v3 — manifest-driven reads + DecisionGate inheritance.

PR6.D.4: gate no longer performs live workspace reads via ``get_run_workspace()``;
it pulls the authoritative artifact list from the typed
``PerceiveState.current_manifest`` (workspace_artifacts kind).

PR4.C.3: every workspace gate MUST explicitly inherit ``DecisionGate`` —
structural isinstance check enforced by ``check_protocol_impl.py``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.perception import ContextItem, ContextManifest
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols import DecisionGate
from lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector import (
    ArtifactRespondInjector,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
INJECTOR_PATH = (
    REPO_ROOT
    / "lca"
    / "layer1_cognitive"
    / "brain"
    / "decision_gates"
    / "artifact_respond_injector.py"
)


def _make_decision(
    *,
    action_type: str = ActionType.RESPOND.value,
    response_text: str = "ok",
) -> Decision:
    return Decision(
        decision_id="d1",
        action_type=action_type,
        rationale="test",
        confidence=1.0,
        response_text=response_text,
    )


def _make_state() -> AgentState:
    return AgentState(trace_id="t1", task="x", budget=Budget(max_steps=5), step=0)


def _make_manifest(payload: list[dict] | None) -> ContextManifest:
    if payload is None:
        return ContextManifest(items=())
    return ContextManifest(
        items=(
            ContextItem(
                kind="workspace_artifacts",
                payload=payload,
                provenance="workspace_artifacts_sensor",
            ),
        )
    )


def _seed_manifest(state: AgentState, payload: list[dict]) -> None:
    """Write a synthetic ContextManifest into PerceiveState slots."""
    from lca.contracts.models.core.perceive_state import PerceiveState

    view = PerceiveState.from_agent_state(state)
    view.current_manifest = _make_manifest(payload)
    view.commit(state)


class TestArtifactRespondInjectorManifest:
    def test_inherits_decision_gate(self) -> None:
        """PR4.C.3: every workspace gate must inherit ``DecisionGate``."""
        assert issubclass(ArtifactRespondInjector, DecisionGate), (
            "ArtifactRespondInjector must explicitly subclass DecisionGate"
        )

    async def test_reads_from_manifest_workspace_artifacts_item(self) -> None:
        gate = ArtifactRespondInjector()
        state = _make_state()
        _seed_manifest(
            state,
            [
                {
                    "path": "report.png",
                    "url": "/files/file_aaa",
                    "mime": "image/png",
                    "size": 1024,
                }
            ],
        )
        decision = _make_decision(response_text="see ![r](report.png)")
        out = await gate.enforce(state, decision)
        text = out.response_text or ""
        assert "/files/file_aaa" in text
        assert "report.png" not in text or "[📥 report.png]" in text

    async def test_falls_back_to_passthrough_when_no_manifest_item(self) -> None:
        gate = ArtifactRespondInjector()
        state = _make_state()
        # No manifest written — PerceiveState.current_manifest is None.
        decision = _make_decision(response_text="plain text")
        out = await gate.enforce(state, decision)
        # Pass-through: decision unchanged.
        assert out is decision
        assert out.response_text == "plain text"

    async def test_falls_back_to_passthrough_when_manifest_has_no_artifact_item(
        self,
    ) -> None:
        gate = ArtifactRespondInjector()
        state = _make_state()
        # Manifest exists but no workspace_artifacts item (e.g. only clock).
        _seed_manifest(state, [])  # empty payload
        decision = _make_decision(response_text="plain text")
        out = await gate.enforce(state, decision)
        assert out.response_text == "plain text"

    async def test_non_respond_action_is_passthrough(self) -> None:
        gate = ArtifactRespondInjector()
        state = _make_state()
        _seed_manifest(state, [{"path": "x", "url": "/files/file_x", "mime": "*", "size": 0}])
        decision = _make_decision(action_type=ActionType.USE_TOOL.value, response_text=None)
        out = await gate.enforce(state, decision)
        assert out is decision

    def test_does_not_call_get_run_workspace(self) -> None:
        """Static AST check: the gate MUST NOT call ``get_run_workspace``."""
        source = INJECTOR_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        offenders: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "get_run_workspace":
                    offenders.append(f"{INJECTOR_PATH.relative_to(REPO_ROOT)}:{node.lineno}")
                if isinstance(func, ast.Attribute) and func.attr == "get_run_workspace":
                    offenders.append(f"{INJECTOR_PATH.relative_to(REPO_ROOT)}:{node.lineno}")
        assert not offenders, (
            f"ArtifactRespondInjector must NOT call get_run_workspace(); offenders: {offenders}"
        )


@pytest.mark.parametrize("artifact_payload", [None, []])
async def test_artifact_payload_edge_cases(artifact_payload: list | None) -> None:
    """Manifest present but payload missing/empty → pass-through."""
    gate = ArtifactRespondInjector()
    state = _make_state()
    if artifact_payload is not None:
        _seed_manifest(state, artifact_payload)
    decision = _make_decision(response_text="hi")
    out = await gate.enforce(state, decision)
    assert out.response_text == "hi"
