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

import importlib.util
from collections.abc import Awaitable, Callable
from pathlib import Path

import pytest

from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.decision import Decision, Observation, Turn
from lca.contracts.models.core.state import AgentState
from lca.contracts.models.team.role_team import ToolPermissionManifest
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry
from lca.layer1_cognitive.transport_registry_factory import build_transport_registry
from lca.plugins.providers.gate_chain_composer import DefaultGateChainComposer

REPO_ROOT = Path(__file__).resolve().parents[2]
SEALER_PATH = (
    REPO_ROOT / "lca" / "layer1_cognitive" / "brain" / "decision_gates" / "office_works_sealer.py"
)


def _is_deprecated(module) -> bool:
    """Detect ``__deprecated__`` / ``__removed__`` markers on the module."""
    return bool(getattr(module, "__deprecated__", False) or getattr(module, "__removed__", False))


def _build_body_for_finalize(seal_office_works_fn: Callable[[], Awaitable[None]]) -> SimpleBody:
    """Construct the Body with the same explicit authority rule as production."""
    return SimpleBody(
        tool_registry=SimpleToolRegistry(),
        safe_executor=SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[])),
        transport_registry=build_transport_registry(),
        action_registry=ActionRegistry(),
        seal_office_works_fn=seal_office_works_fn,
    )


class TestOfficeWorksSealerMigration:
    def test_sealer_no_longer_in_composed_gate_chain(self) -> None:
        """The composer-owned default chain MUST NOT include the sealer."""
        from lca.layer1_cognitive.brain.decision_gates import (
            build_workspace_agent_gate_with_composer,
        )

        gate = build_workspace_agent_gate_with_composer(DefaultGateChainComposer())
        underlying = getattr(gate, "_gates", None)
        assert underlying is not None, "expected ChainedDecisionGate to expose _gates"
        gate_names = [type(g).__name__ for g in underlying]
        assert "OfficeWorksSealer" not in gate_names, (
            f"OfficeWorksSealer migrated to SimpleBody.finalize; "
            f"must not be in default chain. Got: {gate_names}"
        )

    def test_legacy_builder_fails_instead_of_bypassing_composer_seam(self) -> None:
        """Legacy callers receive a migration error instead of a hidden default chain."""
        from lca.layer1_cognitive.brain.decision_gates import build_workspace_agent_gate

        with pytest.raises(RuntimeError, match="no longer constructs a default Gate chain"):
            build_workspace_agent_gate()

    def test_brain_factory_requires_explicit_strategy_collaborators(self) -> None:
        """Layer 1 cannot select strategies or retain a configuration-only seam."""
        from typing import Any, cast

        from lca.layer1_cognitive.brain.default_factory import SimpleBrainFactory
        from lca.layer1_cognitive.brain.reasoner import PromptReasoner

        # The calls intentionally omit or add constructor arguments. Cast only
        # this inspection target so static checking does not reject the very
        # malformed calls whose runtime errors the architecture test pins down.
        unchecked_factory = cast("Any", SimpleBrainFactory)

        with pytest.raises(TypeError, match="agent_gate_factory"):
            unchecked_factory()

        with pytest.raises(TypeError, match="critic_factory"):
            unchecked_factory(
                agent_gate_factory=lambda: None,
                classifier=None,
                reasoner_cls=PromptReasoner,
            )

        with pytest.raises(TypeError, match="reasoner_cls"):
            unchecked_factory(
                agent_gate_factory=lambda: None,
                classifier=None,
                critic_factory=lambda: None,
            )

        with pytest.raises(TypeError, match="unexpected keyword argument 'synthesizer_factory'"):
            unchecked_factory(
                agent_gate_factory=lambda: None,
                classifier=None,
                critic_factory=lambda: None,
                reasoner_cls=PromptReasoner,
                synthesizer_factory=lambda: None,
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
        calls: list[int] = []

        async def seal_fn() -> None:
            calls.append(1)

        body = _build_body_for_finalize(seal_fn)
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
        calls: list[int] = []

        async def seal_fn() -> None:
            calls.append(1)

        body = _build_body_for_finalize(seal_fn)
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
        assert not calls, "SimpleBody.finalize must NOT seal on use_tool (non-terminal action)"
