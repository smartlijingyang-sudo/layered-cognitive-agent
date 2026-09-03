from __future__ import annotations

import asyncio

import pytest

from lca.contracts.models.core.decision import Observation
from lca.infrastructure.idempotency_store import SqliteIdempotencyStore


@pytest.mark.asyncio
async def test_completed_receipt_survives_store_reconstruction(tmp_path) -> None:
    path = tmp_path / "runtime" / "idempotency.sqlite3"
    first = SqliteIdempotencyStore(path)
    assert (await first.claim("plan-1", "effect-1")).status == "new"

    receipt = {
        "receipt": "body.acted",
        "result": Observation(
            observation_id="obs-1",
            success=True,
            payload={"answer": "ok"},
        ),
        "plan_ref": "plan-1",
        "idempotency_key": "effect-1",
        "operation": "body.act",
    }
    await first.complete("plan-1", "effect-1", receipt)

    second = SqliteIdempotencyStore(path)
    claim = await second.claim("plan-1", "effect-1")
    assert claim.status == "completed"
    assert claim.receipt == receipt
    assert isinstance(claim.receipt["result"], Observation)


@pytest.mark.asyncio
async def test_claim_is_atomic_across_store_instances(tmp_path) -> None:
    path = tmp_path / "idempotency.sqlite3"
    stores = [SqliteIdempotencyStore(path), SqliteIdempotencyStore(path)]

    results = await asyncio.gather(*(store.claim("plan-1", "effect-1") for store in stores))

    assert sorted(result.status for result in results) == ["in_progress", "new"]


@pytest.mark.asyncio
async def test_in_progress_claim_survives_restart_and_fails_closed(tmp_path) -> None:
    path = tmp_path / "idempotency.sqlite3"
    first = SqliteIdempotencyStore(path)
    assert (await first.claim("plan-1", "effect-1")).status == "new"

    restarted = SqliteIdempotencyStore(path)
    claim = await restarted.claim("plan-1", "effect-1")

    assert claim.status == "in_progress"
    assert claim.receipt is None


@pytest.mark.asyncio
async def test_gateway_reuses_receipt_after_runtime_reconstruction(tmp_path) -> None:
    from types import SimpleNamespace

    from lca.contracts.protocols.act.command_envelope import CapabilityGrant, CommandEnvelope
    from lca.contracts.protocols.declarative.declarative_phase_graph import EffectPolicyPlan
    from lca.harness.declarative.execute.dispatch import RegistryEffectDispatcher
    from lca.plugins.act.effect_handlers_provider import (
        InMemoryEffectHandlerRegistry,
        register_default_effect_handlers,
    )
    from lca.runtime.declarative_runtime import RuntimePhaseCapabilities

    class Body:
        calls = 0

        async def act(self, _decision, _state) -> dict[str, str]:
            self.calls += 1
            return {"call": str(self.calls)}

    body = Body()
    capabilities = RuntimePhaseCapabilities({"body": body, "memory": SimpleNamespace()})
    envelope = CommandEnvelope(
        plan_ref="plan-1",
        decision_ref="decision-1",
        provider="test-body",
        grant=CapabilityGrant(capability="body.act", scope="run", effect_class="body.act"),
        idempotency_key="effect-1",
        metadata={"operation": "body.act", "state": {}, "decision": {}},
    )
    policy = EffectPolicyPlan(allowed_effects=("body.act",), idempotency_required=("body.act",))
    path = tmp_path / "idempotency.sqlite3"

    def default_effect_handlers() -> InMemoryEffectHandlerRegistry:
        registry = InMemoryEffectHandlerRegistry()
        register_default_effect_handlers(registry)
        return registry

    first = SqliteIdempotencyStore(path)
    first_gateway = RegistryEffectDispatcher(
        capabilities, default_effect_handlers(), idempotency_store=first
    )
    first_result = await first_gateway.execute(envelope, policy)

    second = SqliteIdempotencyStore(path)
    second_gateway = RegistryEffectDispatcher(
        capabilities, default_effect_handlers(), idempotency_store=second
    )
    second_result = await second_gateway.execute(envelope, policy)

    assert first_result == second_result
    assert body.calls == 1
