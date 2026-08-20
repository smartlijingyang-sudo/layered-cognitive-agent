"""OfficeWorksSealer migration tests (PR6.D.5).

The sealer was a workspace-plane ``DecisionGate`` that flushed office
artifacts on respond.  Per v3 §9.2 the side-effect point moved to
``SimpleBody.finalize`` (which calls ``seal_office_works`` when RESPOND /
STOP / ASK_HUMAN is chosen).  This file pins down the migration:

- ``OfficeWorksSealer`` MUST NOT be wired into the default
  ``build_workspace_agent_gate`` chain anymore.
- ``SimpleBody.finalize`` MUST still call the seal function (configurable
  via constructor injection).
- ``OfficeWorksSealer`` is either removed or deprecated — the file should
  either not exist, or carry a ``__deprecated__`` marker.
"""

from __future__ import annotations

import importlib
from pathlib import Path

from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.decision import Decision, Observation, Turn
from lca.contracts.models.core.state import AgentState

REPO_ROOT = Path(__file__).resolve().parents[2]
SEALER_PATH = (
    REPO_ROOT
    / "lca"
    / "layer1_cognitive"
    / "brain"
    / "decision_gates"
    / "office_works_sealer.py"
)


def _is_deprecated(module) -> bool:
    """Detect ``__deprecated__`` / ``__removed__`` markers on the module."""
    return bool(
        getattr(module, "__deprecated__", False)
        or getattr(module, "__removed__", False)
    )


class TestOfficeWorksSealerMigration:
    def test_sealer_no_longer_in_decision_gates_chain(self) -> None:
        """The default chain MUST NOT include the sealer."""
        from lca.layer1_cognitive.brain.decision_gates import (
            build_workspace_agent_gate,
        )

        gate = build_workspace_agent_gate()
        underlying = getattr(gate, "_gates", None)
        assert underlying is not None, "expected ChainedDecisionGate to expose _gates"
        gate_names = [type(g).__name__ for g in underlying]
        assert "OfficeWorksSealer" not in gate_names, (
            f"OfficeWorksSealer migrated to SimpleBody.finalize; "
            f"must not be in default chain. Got: {gate_names}"
        )

    def test_office_works_sealer_class_removed_or_deprecated(self) -> None:
        """The class must be removed OR the module marked deprecated."""
        if not SEALER_PATH.exists():
            return  # acceptable: file removed outright
        spec = importlib.util.spec_from_file_location(
            "lca.layer1_cognitive.brain.decision_gates.office_works_sealer",
            SEALER_PATH,
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert _is_deprecated(module), (
            "office_works_sealer.py must be deleted or carry "
            "__deprecated__ = True module marker (PR6.D.5)"
        )

    async def test_simple_body_finalize_seals(self) -> None:
        """``SimpleBody.finalize`` MUST call the injected sealer on RESPOND."""
        from lca.layer1_cognitive.body.simple_body import SimpleBody

        calls: list[int] = []

        async def seal_fn() -> None:
            calls.append(1)

        body = SimpleBody(seal_office_works_fn=seal_fn)
        state = AgentState(
            trace_id="t",
            task="x",
            budget=Budget(max_steps=10),
            step=0,
            history=[
                Turn(
                    decision=Decision(
                        decision_id="d",
                        action_type="respond",
                        rationale="",
                        confidence=1.0,
                        response_text="ok",
                    ),
                    observation=Observation(
                        observation_id="o",
                        success=True,
                        payload=None,
                    ),
                )
            ],
        )
        await body.finalize(state.history[-1].observation, state)
        assert calls, "SimpleBody.finalize must invoke seal_office_works_fn on RESPOND"

    async def test_simple_body_finalize_skips_on_non_terminal(self) -> None:
        """``SimpleBody.finalize`` MUST NOT seal on non-terminal actions."""
        from lca.layer1_cognitive.body.simple_body import SimpleBody

        calls: list[int] = []

        async def seal_fn() -> None:
            calls.append(1)

        body = SimpleBody(seal_office_works_fn=seal_fn)
        state = AgentState(
            trace_id="t",
            task="x",
            budget=Budget(max_steps=10),
            step=0,
            history=[
                Turn(
                    decision=Decision(
                        decision_id="d",
                        action_type="use_tool",
                        rationale="",
                        confidence=1.0,
                    ),
                    observation=Observation(
                        observation_id="o",
                        success=True,
                        payload=None,
                    ),
                )
            ],
        )
        await body.finalize(state.history[-1].observation, state)
        assert not calls, (
            "SimpleBody.finalize must NOT seal on use_tool (non-terminal action)"
        )
