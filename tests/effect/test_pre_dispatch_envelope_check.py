"""Tests for phase.concept.effect.pre_dispatch_envelope_check (PR-2 / ADR-0234).

Verifies the 4-gate atomic envelope check extracted from
``PipelineSafeExecutor.execute`` into a typed-port graph node.

4 闸 (envelope-shape / permission / grant / budget) must run as one
atomic check; happy path returns all 4 verdict_refs; any failed gate
raises so the outer edge predicate routes to ``terminal.commit`` (fail-loud).
Safe-boundary is NOT an envelope-time verdict: it is enforced at dispatch
time by ControlSlot.ACT_SAFE_BOUNDARY plugins (RA-115).

Per AGENTS.md §3 C13, the node exposes typed-port ``(envelope, tool) →
(envelope, verdict_refs)`` and must not write the envelope or mutate state.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.team.role.team import ToolPermissionManifest
from lca.contracts.protocols.act.command.envelope import (
    BudgetReservation,
    CapabilityGrant,
    CommandEnvelope,
    mint_envelope,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.nodes.effect.pre_dispatch_envelope_check import (
    _ALL_REF_ORDER,
    EffectPreDispatchEnvelopeCheckExecutor,
)


@dataclass
class _StubTool:
    """Stand-in for Tool protocol; only ``name`` is read by the gate node."""

    name: str = "read_file"


def _ctx() -> NodeContext:
    return NodeContext(
        runtime={},
        budget={},
        metadata={"plan_ref": "plan-xyz", "node_id": "effect.pre_dispatch.envelope_check"},
    )


def _envelope_for_tool(tool_name: str) -> CommandEnvelope:
    return mint_envelope(
        plan_ref="plan-xyz",
        scope_ref="turn-1",
        decision=new_id("dec"),
        provider="effect.body",
        grant=CapabilityGrant(capability=tool_name, scope="turn", effect_class="tools"),
        budget_reservation=BudgetReservation(tool_calls=1),
        idempotency_key=f"dec:{tool_name}",
        metadata={
            "effect_class": "tools",
            "operation": "body.act",
            "tool_name": tool_name,
        },
    )


@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_all_gates_pass() -> None:
    """Happy path — all 4 gates emit verdict_refs; envelope passes through.

    RA-115 pin: emitted verdict_refs must equal exactly the gates
    execute() runs. The explicit 4-tuple below fails if a future change
    adds an unearned verdict (e.g. re-introducing safe-boundary:valid
    without a gate that establishes it).
    """
    tool = _StubTool(name="read_file")
    envelope = _envelope_for_tool("read_file")
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=["read_file"]),
    )

    out = await node.execute(
        _ctx(),
        NodeInput(port_values={"envelope": envelope, "tool": tool}),
    )

    assert isinstance(out, NodeOutput)
    assert out.port_values["envelope"] == envelope
    verdict_refs = out.port_values["verdict_refs"]
    assert isinstance(verdict_refs, tuple)
    assert verdict_refs == _ALL_REF_ORDER
    assert _ALL_REF_ORDER == (
        "effect.pre_dispatch.envelope-shape:valid",
        "effect.pre_dispatch.permission:allow",
        "effect.pre_dispatch.grant:valid",
        "effect.pre_dispatch.budget:valid",
    )
    assert not any("safe-boundary" in v for v in verdict_refs)


@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_permission_denied_raises() -> None:
    """Permission gate failure — raises ValueError; verdict_refs not emitted."""
    tool = _StubTool(name="rm_rf_root")  # not in allowed_tools
    envelope = _envelope_for_tool("rm_rf_root")
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=["read_file"]),
    )

    with pytest.raises(ValueError, match="permission"):
        await node.execute(
            _ctx(),
            NodeInput(port_values={"envelope": envelope, "tool": tool}),
        )


@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_grant_mismatch_raises() -> None:
    """Grant gate failure — envelope.grant.effect_class != 'tools'.

    The node derives tool identity from ``envelope.grant.capability``
    (single typed-port contract); grant.effect_class must equal
    ``"tools"`` so the envelope is recognized as a tool dispatch.
    """
    tool = _StubTool(name="read_file")
    envelope = mint_envelope(
        plan_ref="plan-xyz",
        scope_ref="turn-1",
        decision=new_id("dec"),
        provider="effect.body",
        grant=CapabilityGrant(
            capability="read_file", scope="turn", effect_class="non_tool"
        ),  # effect_class wrong → grant gate fails
        budget_reservation=BudgetReservation(tool_calls=1),
        idempotency_key="dec:read_file",
        metadata={"effect_class": "tools", "operation": "body.act"},
    )
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=["read_file"]),
    )

    with pytest.raises(ValueError, match="grant"):
        await node.execute(
            _ctx(),
            NodeInput(port_values={"envelope": envelope, "tool": tool}),
        )


@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_envelope_shape_incomplete_raises() -> None:
    """Envelope-shape gate failure — provider is empty.

    ``mint_envelope`` validates all of plan_ref/scope_ref/provider, so
    the only way to exercise the node's envelope-shape gate is to
    construct a ``CommandEnvelope`` directly with a missing field.
    """
    tool = _StubTool(name="read_file")
    # Bypass mint_envelope (which rejects empty provider) to reach the
    # node-level envelope-shape gate.
    envelope = CommandEnvelope(
        plan_ref="plan-xyz",
        scope_ref="turn-1",
        decision_ref="dec-empty-provider",
        provider="",  # empty → envelope-shape gate fails
        grant=CapabilityGrant(capability="read_file", scope="turn", effect_class="tools"),
        budget_reservation=BudgetReservation(tool_calls=1),
        idempotency_key="dec:read_file",
        metadata={"effect_class": "tools", "operation": "body.act"},
    )
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=["read_file"]),
    )

    with pytest.raises(ValueError, match="envelope-shape"):
        await node.execute(
            _ctx(),
            NodeInput(port_values={"envelope": envelope, "tool": tool}),
        )


@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_batch_envelopes_all_pass() -> None:
    """Batch envelopes: all envelopes pass 4 gates atomically, outputting envelope, envelopes and verdict_refs."""
    env1 = _envelope_for_tool("list_role_cards")
    env2 = _envelope_for_tool("read_file")
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=["list_role_cards", "read_file"]),
    )

    out = await node.execute(
        _ctx(),
        NodeInput(port_values={"envelopes": [env1, env2]}),
    )

    assert isinstance(out, NodeOutput)
    assert out.port_values["envelope"] == env1
    assert tuple(out.port_values["envelopes"]) == (env1, env2)
    assert out.port_values["verdict_refs"] == (
        "effect.pre_dispatch.envelope-shape:valid",
        "effect.pre_dispatch.permission:allow",
        "effect.pre_dispatch.grant:valid",
        "effect.pre_dispatch.budget:valid",
    )


@pytest.mark.asyncio
async def test_pre_dispatch_envelope_check_batch_envelopes_one_denied_raises_atomically() -> None:
    """Batch envelopes: if 1 of the envelopes fails permission, fails loud atomically."""
    env1 = _envelope_for_tool("list_role_cards")
    env2 = _envelope_for_tool("rm_rf_root")
    node = EffectPreDispatchEnvelopeCheckExecutor(
        permission_manifest=ToolPermissionManifest(allowed_tools=["list_role_cards"]),
    )

    with pytest.raises(ValueError, match="permission denied"):
        await node.execute(
            _ctx(),
            NodeInput(port_values={"envelopes": [env1, env2]}),
        )
