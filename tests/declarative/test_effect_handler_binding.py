from __future__ import annotations

import pytest

from lca.contracts.protocols.command_envelope import CapabilityGrant, CommandEnvelope
from lca.contracts.protocols.declarative_phase_graph import EffectPolicyPlan
from lca.layer2_runtime.declarative_runtime import RuntimeEffectGateway, RuntimePhaseCapabilities


class _Handler:
    def __init__(self) -> None:
        self.received: list[tuple[CommandEnvelope, RuntimePhaseCapabilities]] = []

    async def execute(
        self,
        envelope: CommandEnvelope,
        capabilities: RuntimePhaseCapabilities,
    ) -> object:
        self.received.append((envelope, capabilities))
        return {"receipt": "handler-called"}


@pytest.mark.asyncio
async def test_effect_gateway_dispatches_to_bound_handler_by_granted_capability() -> None:
    handler = _Handler()
    gateway = RuntimeEffectGateway(
        RuntimePhaseCapabilities(
            brain=None, body=None, memory=None, perceive_hub=None, stop_rule=None
        ),
        effect_handlers={"body.act": handler},
    )
    envelope = CommandEnvelope(
        plan_ref="plan:test",
        scope_ref="act.main",
        decision_ref="decision:test",
        provider="effect.body",
        grant=CapabilityGrant(capability="body.act", scope="run", effect_class="tools"),
        idempotency_key="effect:test",
        metadata={"effect_class": "tools"},
    )
    policy = EffectPolicyPlan(
        gateway_capability="effect.gateway",
        allowed_effects=("tools",),
        approval_required=(),
        idempotency_required=("tools",),
    )

    receipt = await gateway.execute(envelope, policy)

    assert receipt == {"receipt": "handler-called"}
    assert handler.received[0][0] == envelope
    assert handler.received[0][1].body is None
