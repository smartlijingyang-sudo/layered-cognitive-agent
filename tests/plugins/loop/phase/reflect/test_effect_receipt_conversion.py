"""Regression test for EffectReceipt → Observation conversion in reflect.score.

ADR-0220 separates the act-world receipt from the reflect-world observation.
The reflect phase must convert EffectReceipt to Observation before passing
to downstream reflection primitives that expect Observation.success.
"""

from __future__ import annotations

import pytest

from lca.contracts.atoms.enums.enums import ReflectionVerdict
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.harness.act.effect_receipt import EffectOutcome, EffectReceipt
from lca.contracts.models.core.execution.decision import Observation, Reflection
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.plugins.loop.phase.reflect.score.plugin import (
    ReflectScoreExecutor,
    _normalize_observation,
)


class TestEffectReceiptConversion:
    """EffectReceipt must be converted to Observation at the reflect boundary."""

    def test_normalize_converts_failed_receipt(self) -> None:
        """Failed EffectReceipt becomes Observation with success=False."""
        receipt = EffectReceipt(
            invocation_id="inv_1",
            outcome=EffectOutcome.FAILED,
            idempotency_key="key_1",
            provider="body.act",
            error_code="UnregisteredActionError",
            retryable=True,
        )

        observation = _normalize_observation(receipt)

        assert isinstance(observation, Observation)
        assert observation.success is False
        assert observation.error == "UnregisteredActionError"
        assert observation.extra["effect_receipt_error_code"] == "UnregisteredActionError"

    def test_normalize_converts_succeeded_receipt(self) -> None:
        """Succeeded EffectReceipt becomes Observation with success=True."""
        receipt = EffectReceipt(
            invocation_id="inv_2",
            outcome=EffectOutcome.SUCCEEDED,
            idempotency_key="key_2",
            provider="body.act",
            output_ref="output_ref_123",
        )

        observation = _normalize_observation(receipt)

        assert isinstance(observation, Observation)
        assert observation.success is True
        assert observation.error is None

    def test_normalize_passes_through_observation(self) -> None:
        """Observation passes through unchanged."""
        observation = Observation(
            observation_id="obs_1",
            success=True,
            payload={"result": "ok"},
        )

        result = _normalize_observation(observation)

        assert result is observation

    def test_normalize_passes_through_none(self) -> None:
        """None passes through unchanged."""
        result = _normalize_observation(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_score_executor_handles_effect_receipt(self) -> None:
        """ReflectScoreExecutor converts EffectReceipt before calling brain."""
        from lca.contracts.models.core.execution.decision import Decision

        receipt = EffectReceipt(
            invocation_id="inv_test",
            outcome=EffectOutcome.FAILED,
            idempotency_key="key_test",
            provider="body.act",
            error_code="TestError",
        )

        captured_observation = None

        class MockBrain:
            async def think(self, state) -> Decision:
                raise NotImplementedError

            async def reflect(self, state, observation) -> Reflection:
                nonlocal captured_observation
                captured_observation = observation
                return Reflection(
                    reflection_id=new_id("refl"),
                    verdict=ReflectionVerdict.ON_TRACK,
                    lesson=None,
                )

        executor = ReflectScoreExecutor()
        context = NodeContext(
            runtime={"brain": MockBrain(), "agent_state": None},
            metadata={},
            budget=None,
        )
        input_data = NodeInput(port_values={"observation": receipt})

        output = await executor.node_execute(context, input_data)

        assert captured_observation is not None
        assert isinstance(captured_observation, Observation)
        assert captured_observation.success is False
        assert output.port_values["reflection"] is not None


class TestAdmitRecoveryIsFailure:
    """admit_recovery._is_failure must handle EffectReceipt."""

    def test_failed_receipt_is_failure(self) -> None:
        from lca.plugins.loop.phase.reflect.admit_recovery.plugin import _is_failure

        receipt = EffectReceipt(
            invocation_id="inv_1",
            outcome=EffectOutcome.FAILED,
            idempotency_key="key_1",
            provider="body.act",
            error_code="TestError",
        )
        assert _is_failure(receipt) is True

    def test_succeeded_receipt_is_not_failure(self) -> None:
        from lca.plugins.loop.phase.reflect.admit_recovery.plugin import _is_failure

        receipt = EffectReceipt(
            invocation_id="inv_2",
            outcome=EffectOutcome.SUCCEEDED,
            idempotency_key="key_2",
            provider="body.act",
        )
        assert _is_failure(receipt) is False

    def test_unknown_receipt_is_failure(self) -> None:
        from lca.plugins.loop.phase.reflect.admit_recovery.plugin import _is_failure

        receipt = EffectReceipt(
            invocation_id="inv_3",
            outcome=EffectOutcome.UNKNOWN,
            idempotency_key="key_3",
            provider="body.act",
        )
        assert _is_failure(receipt) is True
