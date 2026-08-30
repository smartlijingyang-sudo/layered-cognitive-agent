"""Round 87 regression: ``SimpleBody`` no longer carries a no-op helper whose
only purpose was to point readers at the real emitter.

The historical ``_maybe_record_action_degraded`` was a no-op stub that
delegated to ``lca.layer2_runtime.event_emission._derive_action_degraded`` via
the ``POST_ACT`` hook. The stub's docstring (and the call from ``act``) added
zero behavior; they were documentation masquerading as code.

After R87:
- The stub is removed.
- The active seam (``_propagate_degradation``) now carries the documentation
  pointing at the real emitter.
- ``act`` still surfaces the degradation marker on the observation so the
  hook can derive ``ActionDegraded`` without the body knowing about it.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums import ActionType
from lca.contracts.atoms.semantic_keys import OBS_DEGRADED_FROM
from lca.contracts.models.core.decision import Decision
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.models.team.role_team import ToolPermissionManifest
from lca.infrastructure.transport.transport_registry import TransportRegistry
from lca.layer1_cognitive.body.action_registry import ActionRegistry
from lca.layer1_cognitive.body.safe_executor import SimpleSafeExecutor
from lca.layer1_cognitive.body.simple_body import SimpleBody
from lca.layer1_cognitive.body.tool_registry import SimpleToolRegistry


def _state() -> AgentState:
    return AgentState(trace_id="t", task="task", budget=Budget())


def _body() -> SimpleBody:
    return SimpleBody(
        SimpleToolRegistry(),
        SimpleSafeExecutor(ToolPermissionManifest(allowed_tools=[])),
        TransportRegistry(),
        ActionRegistry(),
    )


class TestSimpleBodySurface:
    def test_no_op_helper_is_removed(self) -> None:
        """The misleading no-op must not exist on the public surface."""
        assert not hasattr(_body(), "_maybe_record_action_degraded"), (
            "_maybe_record_action_degraded was a no-op stub that only pointed "
            "readers at the real emitter (event_emission). It has been removed."
        )

    def test_propagate_degradation_is_still_present(self) -> None:
        """The active seam (marker propagation) must remain."""
        assert hasattr(SimpleBody, "_propagate_degradation")

    @pytest.mark.asyncio
    async def test_act_still_surfaces_degradation_marker(self) -> None:
        """``act`` still calls ``_propagate_degradation``; behavior unchanged."""
        body = _body()
        decision = Decision(
            decision_id="d",
            action_type=ActionType.RESPOND.value,
            rationale="fallback",
            confidence=0.5,
            response_text="ok",
            degraded_from="use_tool",
        )

        class _RespondHandler:
            async def execute(self, _decision: Decision, _state: AgentState):
                from lca.contracts.atoms.enums import MemoryRecordKind
                from lca.contracts.atoms.ids import new_id
                from lca.contracts.atoms.semantic_keys import OBS_RESULT_KIND
                from lca.contracts.models.core.decision import Observation

                return Observation(
                    observation_id=new_id("obs"),
                    success=True,
                    payload="ok",
                    extra={OBS_RESULT_KIND: MemoryRecordKind.RESPONSE},
                )

        body.action_registry.register(ActionType.RESPOND.value, _RespondHandler())
        observation = await body.act(decision, _state())
        assert observation.degraded_from == "use_tool"
        assert observation.extra.get(OBS_DEGRADED_FROM) == "use_tool"


class TestPropagateDegradationContract:
    def test_propagation_skipped_when_no_degradation(self) -> None:
        from lca.contracts.atoms.enums import MemoryRecordKind
        from lca.contracts.atoms.ids import new_id
        from lca.contracts.atoms.semantic_keys import OBS_RESULT_KIND
        from lca.contracts.models.core.decision import Observation

        decision = Decision(
            decision_id="d",
            action_type=ActionType.RESPOND.value,
            rationale="",
            confidence=0.5,
            response_text="ok",
        )
        observation = Observation(
            observation_id=new_id("obs"),
            success=True,
            payload="ok",
            extra={OBS_RESULT_KIND: MemoryRecordKind.RESPONSE},
        )
        result = SimpleBody._propagate_degradation(decision, observation)
        assert result is observation
        assert OBS_DEGRADED_FROM not in result.extra
