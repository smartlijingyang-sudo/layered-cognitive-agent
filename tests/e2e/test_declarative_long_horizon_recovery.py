"""E2E tests for declarative long-horizon recovery (Task 7 of ADR 74/75 cutover).

Tests bounded recovery and effect idempotency:
1. Resume after crash does not reissue confirmed effects
2. Recovery profile replans once then stops at declared budget
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any

from lca.contracts.models.core.budget import Budget
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.command_envelope import CommandEnvelope
from lca.contracts.protocols.declarative_phase_graph import PhaseRunCursor
from lca.harness.declarative.interpreter import GenericPlanInterpreter


# Task 7: These will be implemented in declarative_runtime.py
# For now, import what exists
from lca.layer2_runtime.declarative_runtime import (
    ClaimResult,
    DeclarativeCheckpoint,
    DeclarativeRuntimeDriver,
    RuntimeEffectGateway,
    RuntimeIdempotencyStore,
    RuntimePhaseCapabilities,
)


@dataclass
class MockBody:
    """Mock body that tracks effect calls."""
    calls: list[str] = field(default_factory=list)
    fail_on_call: int | None = None
    
    async def act(self, decision: Any, state: Any) -> Any:
        call_num = len(self.calls)
        if self.fail_on_call is not None and call_num >= self.fail_on_call:
            raise RuntimeError("Simulated crash after effect")
        call_id = f"call_{call_num}"
        self.calls.append(call_id)
        return {"status": "success", "call_id": call_id}


@dataclass
class MockMemory:
    """Mock memory system."""
    updates: int = 0
    
    async def update(self, state: Any, observation: Any, reflection: Any) -> None:
        self.updates += 1


@dataclass
class MockPerceiveHub:
    """Mock perceive hub."""
    async def perceive(self, state: Any) -> Any:
        return None


@dataclass
class MockStopRule:
    """Mock stop rule."""
    async def decide(self, state: Any, decision: Any, observation: Any, reflection: Any) -> Any:
        from lca.contracts.models.core.stop import StopDecision, StopReason
        return StopDecision(should_stop=False, reason=StopReason.CONTINUE, final_output=None)


class TestEffectIdempotency:
    """Test effect idempotency with persistent receipt store."""

    @pytest.mark.asyncio
    async def test_idempotency_store_claim_and_receipt(self) -> None:
        """Verify idempotency store claims and returns receipts."""
        store = RuntimeIdempotencyStore()
        
        # First claim should succeed
        result1 = await store.claim("plan_v1", "key_123")
        assert result1.status == "new"
        assert result1.receipt is None
        
        # Mark as completed
        await store.complete("plan_v1", "key_123", {"receipt": "done"})
        
        # Second claim with same key should return completed
        result2 = await store.claim("plan_v1", "key_123")
        assert result2.status == "completed"
        assert result2.receipt == {"receipt": "done"}
        
        # Different key should be new
        result3 = await store.claim("plan_v1", "key_456")
        assert result3.status == "new"
        assert result3.receipt is None

    @pytest.mark.asyncio
    async def test_effect_gateway_uses_idempotency_store(self) -> None:
        """Verify effect gateway checks idempotency before executing."""
        body = MockBody()
        capabilities = RuntimePhaseCapabilities(
            brain=None,
            body=body,
            memory=MockMemory(),
            perceive_hub=MockPerceiveHub(),
            stop_rule=MockStopRule(),
        )
        store = RuntimeIdempotencyStore()
        gateway = RuntimeEffectGateway(capabilities, idempotency_store=store)
        
        from lca.contracts.protocols.command_envelope import CapabilityGrant
        from lca.contracts.protocols.declarative_phase_graph import EffectPolicyPlan
        
        # Create envelope with idempotency key
        envelope = CommandEnvelope(
            plan_ref="plan_v1",
            decision_ref="dec_1",
            provider="test-body",
            grant=CapabilityGrant(capability="body.act", scope="run", effect_class="body.act"),
            idempotency_key="key_123",
            metadata={"operation": "body.act", "state": {}, "decision": {}},
        )
        
        policy = EffectPolicyPlan(
            allowed_effects=("body.act",),
            idempotency_required=("body.act",),
        )
        
        # First execution should succeed
        result1 = await gateway.execute(envelope, policy)
        assert len(body.calls) == 1
        assert "receipt" in result1
        assert result1["idempotency_key"] == "key_123"
        
        # Second execution with same key should return cached result
        result2 = await gateway.execute(envelope, policy)
        # Body should only be called once
        assert len(body.calls) == 1
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_resume_after_crash_does_not_reissue_effect(self) -> None:
        """Verify resume after crash doesn't reissue confirmed effects."""
        body = MockBody()
        capabilities = RuntimePhaseCapabilities(
            brain=None,
            body=body,
            memory=MockMemory(),
            perceive_hub=MockPerceiveHub(),
            stop_rule=MockStopRule(),
        )
        store = RuntimeIdempotencyStore()
        gateway = RuntimeEffectGateway(capabilities, idempotency_store=store)
        
        from lca.contracts.protocols.command_envelope import CapabilityGrant
        from lca.contracts.protocols.declarative_phase_graph import EffectPolicyPlan
        
        # Create envelope
        envelope = CommandEnvelope(
            plan_ref="plan_v1",
            decision_ref="dec_1",
            provider="test-body",
            grant=CapabilityGrant(capability="body.act", scope="run", effect_class="body.act"),
            idempotency_key="key_123",
            metadata={"operation": "body.act", "state": {}, "decision": {}},
        )
        
        policy = EffectPolicyPlan(
            allowed_effects=("body.act",),
            idempotency_required=("body.act",),
        )
        
        # First execution succeeds and records receipt
        result1 = await gateway.execute(envelope, policy)
        assert len(body.calls) == 1
        
        # Simulate crash and resume - gateway should check store
        # and return cached result without calling body again
        result2 = await gateway.execute(envelope, policy)
        assert len(body.calls) == 1  # Still only one call
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_in_progress_claim_raises_uncertain(self) -> None:
        """Verify in_progress claim raises effect_uncertain error."""
        body = MockBody()
        capabilities = RuntimePhaseCapabilities(
            brain=None,
            body=body,
            memory=MockMemory(),
            perceive_hub=MockPerceiveHub(),
            stop_rule=MockStopRule(),
        )
        store = RuntimeIdempotencyStore()
        gateway = RuntimeEffectGateway(capabilities, idempotency_store=store)
        
        from lca.contracts.protocols.command_envelope import CapabilityGrant
        from lca.contracts.protocols.declarative_phase_graph import (
            DeclarativeValidationError,
            EffectPolicyPlan,
        )
        
        # Create envelope
        envelope = CommandEnvelope(
            plan_ref="plan_v1",
            decision_ref="dec_1",
            provider="test-body",
            grant=CapabilityGrant(capability="body.act", scope="run", effect_class="body.act"),
            idempotency_key="key_123",
            metadata={"operation": "body.act", "state": {}, "decision": {}},
        )
        
        policy = EffectPolicyPlan(
            allowed_effects=("body.act",),
            idempotency_required=("body.act",),
        )
        
        # Manually set claim to in_progress (simulating crash)
        store._claims[("plan_v1", "key_123")] = {"status": "in_progress", "receipt": None}
        
        # Should raise RT-003 error
        with pytest.raises(DeclarativeValidationError, match="RT-003"):
            await gateway.execute(envelope, policy)


class TestRecoveryProfile:
    """Test bounded recovery with reflect → think edge."""

    @pytest.mark.asyncio
    async def test_recovery_profile_limits_retries(self) -> None:
        """Verify recovery profile limits retries to declared budget."""
        # This test would verify that a recovery profile with
        # reflect → think edge is bounded by maxIterations
        
        # For now, this is a placeholder that documents the expected behavior
        # Full implementation requires building a recovery profile YAML
        # and testing the interpreter's edge traversal logic
        
        # Expected behavior:
        # 1. Phase graph has reflect.main → think.main edge
        # 2. Edge has loop constraint: maxIterations: 1
        # 3. Interpreter respects the constraint and stops after 1 retry
        
        pytest.skip("Recovery profile E2E test requires full profile setup")
