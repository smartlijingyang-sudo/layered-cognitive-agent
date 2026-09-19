"""Tests for ADR-0244 PR-3 Task 8: Tiered Zero-Cost Gate (Fast-path No-op).

Verifies that for normal text responses (no tool call, no error, observation is None):
1. ReflectScoreExecutor completes in < 5ms without invoking brain.reflect or LLM;
2. ReflectAdmitRecoveryExecutor detects observation=None as NOT a failure (_is_failure=False), avoiding spurious admit_recovery loops;
3. RememberWriteExecutor determines No-op, mints NO envelope, calls NO gateway, completes in < 2ms with envelope=None and memory_receipt=None.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from lca.contracts.atoms.enums.enums import ActionType
from lca.contracts.models.core.execution.decision import Decision
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.nodes.reflect.admit_recovery.admit_recovery import (
    ReflectAdmitRecoveryExecutor,
    _is_failure,
)
from lca.nodes.reflect.score.score import ReflectScoreExecutor
from lca.nodes.remember.write.write import RememberWriteExecutor


class TestFastPathScoreZeroCost:
    @pytest.mark.asyncio
    async def test_score_fast_path_when_observation_none(self) -> None:
        mock_brain = MagicMock()
        mock_brain.reflect = AsyncMock()

        executor = ReflectScoreExecutor()
        context = NodeContext(
            runtime={"brain": mock_brain},
            metadata={},
            budget=None,
        )
        input_data = NodeInput(port_values={"observation": None})

        t0 = time.perf_counter()
        output = await executor.node_execute(context, input_data)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Must NOT call brain / LLM critic
        mock_brain.reflect.assert_not_called()
        # Fast path timing guard: < 5ms
        assert elapsed_ms < 5.0, f"Score fast-path exceeded 5ms: {elapsed_ms:.2f}ms"

        assert output.port_values["reflection"] is None
        assert output.port_values["routing"].action_type == ActionType.RESPOND


class TestFastPathAdmitRecovery:
    def test_is_failure_none_observation_is_false(self) -> None:
        """observation=None on a clean respond turn is NOT a failure."""
        assert _is_failure(None) is False

    @pytest.mark.asyncio
    async def test_admit_recovery_no_hint_on_none_observation(self) -> None:
        executor = ReflectAdmitRecoveryExecutor()
        context = NodeContext(runtime={}, metadata={}, budget=None)
        input_data = NodeInput(port_values={"observation": None, "reflection": None})

        t0 = time.perf_counter()
        output = await executor.node_execute(context, input_data)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert elapsed_ms < 2.0
        # next_hint must NOT be admit_recovery
        assert output.port_values["routing"].next_hint is None


class TestFastPathRememberWriteZeroCost:
    @pytest.mark.asyncio
    async def test_remember_write_fast_path_noop(self) -> None:
        mock_gateway = MagicMock()
        mock_gateway.dispatch = AsyncMock()

        executor = RememberWriteExecutor()
        context = NodeContext(
            runtime={"effect_gateway": mock_gateway},
            metadata={"plan_ref": "test-plan", "node_id": "test-node"},
            budget=None,
        )
        decision = Decision(
            decision_id="dec-clean-respond",
            action_type="respond",
            response_text="Clean reply",
            rationale="No tools needed",
            confidence=1.0,
        )
        input_data = NodeInput(
            port_values={
                "decision": decision,
                "observation": None,
                "reflection": None,
            }
        )

        t0 = time.perf_counter()
        output = await executor.node_execute(context, input_data)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        mock_gateway.dispatch.assert_not_called()
        assert elapsed_ms < 2.0, f"Write fast-path exceeded 2ms: {elapsed_ms:.2f}ms"

        assert output.port_values["envelope"] is None
        assert output.port_values.get("memory_receipt") is None
        assert output.port_values["routing"].action_type == ActionType.RESPOND
