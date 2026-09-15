"""Unit tests for the ``delegate.compose`` node (ADR-0228 D5).

The hand-written :class:`DelegateComposeExecutor` in
:mod:`lca.nodes.delegate.compose` reads a Decision port + a
duck-typed capability_grant and emits a tuple of
:class:`DelegationRequest`. The tests pin the typed-port contract:

1. Single-target fan-out emits exactly one request.
2. Multi-target fan-out emits one request per target, order preserved.
3. Broadcast (``"*"``) emits exactly one request addressed to ``"*"``.
4. Missing ``"delegate"`` capability raises
   :class:`CapabilityGrantExceededError` (C5 monotonicity).
5. ``idempotency_key`` follows the ``"{decision_id}:{delegate_to}"``
   format (C9 retry safety).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any

import pytest

from lca.contracts.mechanisms.composition.composition import (
    CapabilityGrantExceededError,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.delegation import DelegationRequest
from lca.nodes.delegate.compose import (
    DEFAULT_TIMEOUT_MS,
    DELEGATE_CAPABILITY,
    DelegateComposeExecutor,
)

# ── Fixtures ────────────────────────────────────────────────────


@dataclass
class _StubDecision:
    """Minimal Decision stand-in carrying the typed ``delegate_to`` port."""

    decision_id: str = "dec-001"
    delegate_to: list[str] | str = field(default_factory=list)
    action_payload: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""


@dataclass
class _StubGrant:
    """Minimal capability_grant stand-in exposing a ``capabilities`` tuple."""

    capabilities: tuple[str, ...] = ()


def _ctx() -> NodeContext:
    return NodeContext(runtime={}, budget={}, metadata={})


def _grant_with(*capabilities: str) -> _StubGrant:
    return _StubGrant(capabilities=capabilities)


# ── Typed-port contract cases ───────────────────────────────────


@pytest.mark.asyncio
async def test_single_target_emits_one_request() -> None:
    """1 target → exactly 1 DelegationRequest."""
    executor = DelegateComposeExecutor()
    decision = _StubDecision(decision_id="dec-1", delegate_to=["agent_a"])
    grant = _grant_with("delegate")
    out = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": decision, "capability_grant": grant}),
    )
    requests = out.port_values["delegation_request"]
    assert isinstance(requests, tuple)
    assert len(requests) == 1
    assert isinstance(requests[0], DelegationRequest)
    assert requests[0].delegate_to == "agent_a"
    assert requests[0].payload["decision_id"] == "dec-1"
    assert requests[0].timeout_ms == DEFAULT_TIMEOUT_MS


@pytest.mark.asyncio
async def test_multi_target_emits_one_request_per_target_in_order() -> None:
    """N targets → N DelegationRequest, order preserved."""
    executor = DelegateComposeExecutor()
    decision = _StubDecision(
        decision_id="dec-2",
        delegate_to=["agent_a", "agent_b"],
    )
    grant = _grant_with("delegate")
    out = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": decision, "capability_grant": grant}),
    )
    requests = out.port_values["delegation_request"]
    assert isinstance(requests, tuple)
    assert len(requests) == 2
    assert [r.delegate_to for r in requests] == ["agent_a", "agent_b"]
    assert all(isinstance(r, DelegationRequest) for r in requests)


@pytest.mark.asyncio
async def test_broadcast_star_emits_one_request_to_star() -> None:
    """``decision.delegate_to == "*"`` → 1 request addressed to ``"*"``."""
    executor = DelegateComposeExecutor()
    decision = _StubDecision(decision_id="dec-3", delegate_to="*")
    grant = _grant_with("delegate")
    out = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": decision, "capability_grant": grant}),
    )
    requests = out.port_values["delegation_request"]
    assert isinstance(requests, tuple)
    assert len(requests) == 1
    assert requests[0].delegate_to == "*"
    assert requests[0].idempotency_key == "dec-3:*"


@pytest.mark.asyncio
async def test_missing_delegate_capability_raises_capability_grant_exceeded() -> None:
    """C5: grant missing ``"delegate"`` → CapabilityGrantExceededError."""
    executor = DelegateComposeExecutor()
    decision = _StubDecision(decision_id="dec-4", delegate_to=["agent_a"])
    grant = _grant_with("read", "write")  # no "delegate"
    with pytest.raises(CapabilityGrantExceededError) as excinfo:
        await executor.node_execute(
            _ctx(),
            NodeInput(port_values={"decision": decision, "capability_grant": grant}),
        )
    assert excinfo.value.granted == ("read", "write")
    assert excinfo.value.required == (DELEGATE_CAPABILITY,)


@pytest.mark.asyncio
async def test_idempotency_key_format_is_decision_id_colon_target() -> None:
    """C9: idempotency_key == ``{decision_id}:{delegate_to}`` per request."""
    executor = DelegateComposeExecutor()
    decision = _StubDecision(
        decision_id="dec-5",
        delegate_to=["agent_a", "agent_b"],
    )
    grant = _grant_with("delegate")
    out = await executor.node_execute(
        _ctx(),
        NodeInput(port_values={"decision": decision, "capability_grant": grant}),
    )
    requests = out.port_values["delegation_request"]
    assert [r.idempotency_key for r in requests] == [
        "dec-5:agent_a",
        "dec-5:agent_b",
    ]


# ── Plugin carrier contract ─────────────────────────────────────


def test_plugin_module_exposes_setup_carrier_with_composite_key() -> None:
    """``setup.setup()`` registers ``region:delegate::delegate.compose``."""
    module = import_module("lca.nodes.delegate.compose")
    assert hasattr(module, "setup")
    assert hasattr(module.setup, "setup")
    assert callable(module.setup.setup)
