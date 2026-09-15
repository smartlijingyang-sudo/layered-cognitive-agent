"""Tests for region.delegate.await plugin.

Verifies the typed ``delegate.await`` pass-through node: kernel-fed
``DelegationReceipt`` tuples come out unchanged. ADR-0228 §D5.

``delegate.await.block`` lives under a folder named ``await`` (Python
reserved keyword). ``from lca.nodes.delegate.block import …`` is a
syntax error at parse time, so the module is loaded via
``importlib.import_module`` and a small ``AwaitExecutor`` indirection
keeps the test bodies identical to the ``fold`` test style.
"""

from __future__ import annotations

import importlib

from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.graph.delegation import (
    DelegationReceipt,
    DelegationRequest,
)


def _executor() -> object:
    """Return a fresh ``DelegateAwaitExecutor`` for each test.

    The module path contains ``await`` (a reserved keyword), so static
    ``from lca.nodes.delegate.block import …`` is a syntax error.
    The bundle resolver and runtime use ``importlib.import_module``
    dynamically; the tests mirror that.
    """
    module = importlib.import_module("lca.nodes.delegate.block")
    return module.DelegateAwaitExecutor()


def _ctx() -> NodeContext:
    """Minimal NodeContext; await node does not read runtime."""
    return NodeContext(runtime={}, budget={}, metadata={})


def _receipt(
    *,
    delegate_from: str,
    status: str = "ok",
    payload: dict[str, object] | None = None,
    error: str | None = None,
) -> DelegationReceipt:
    """Build a typed receipt for fixture use."""
    return DelegationReceipt(
        delegate_from=delegate_from,
        status=status,
        payload=payload,
        error=error,
    )


def _request(*, delegate_to: str) -> DelegationRequest:
    return DelegationRequest(
        delegate_to=delegate_to,
        payload={"task": f"work for {delegate_to}"},
        timeout_ms=5000,
        idempotency_key=f"key-{delegate_to}",
    )


async def test_two_requests_two_receipts_passes_through() -> None:
    """2 requests + 2 receipts → emit tuple of 2 receipts (verbatim)."""
    receipts = (
        _receipt(delegate_from="agent.a", payload={"answer": "a"}),
        _receipt(delegate_from="agent.b", payload={"answer": "b"}),
    )
    requests = (_request(delegate_to="agent.a"), _request(delegate_to="agent.b"))
    output = await _executor().node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "delegation_request": requests,
                "delegation_receipt": receipts,
            }
        ),
    )
    emitted = output.port_values["delegation_receipt"]
    assert isinstance(emitted, tuple)
    assert emitted == receipts


async def test_one_request_one_receipt_passes_through() -> None:
    """1 request + 1 receipt → emit tuple of 1 receipt."""
    receipt = _receipt(delegate_from="agent.a", payload={"answer": "x"})
    requests = (_request(delegate_to="agent.a"),)
    output = await _executor().node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "delegation_request": requests,
                "delegation_receipt": (receipt,),
            }
        ),
    )
    emitted = output.port_values["delegation_receipt"]
    assert emitted == (receipt,)


async def test_all_ok_receipts_are_passthrough() -> None:
    """Receipts with status='ok' are forwarded verbatim, no filtering."""
    receipts = tuple(
        _receipt(delegate_from=f"agent.{c}", payload={"i": i}) for i, c in enumerate("abc")
    )
    requests = tuple(_request(delegate_to=f"agent.{c}") for c in "abc")
    output = await _executor().node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "delegation_request": requests,
                "delegation_receipt": receipts,
            }
        ),
    )
    emitted = output.port_values["delegation_receipt"]
    assert emitted == receipts
    assert all(r.status == "ok" for r in emitted)


async def test_error_status_receipts_are_not_dropped() -> None:
    """Receipts with status='error' must reach downstream fold unchanged."""
    receipts = (
        _receipt(delegate_from="agent.a", payload={"answer": "a"}),
        _receipt(
            delegate_from="agent.b",
            status="error",
            error="child crashed",
        ),
        _receipt(delegate_from="agent.c", status="timeout", error="timeout"),
    )
    requests = tuple(_request(delegate_to=f"agent.{c}") for c in "abc")
    output = await _executor().node_execute(
        _ctx(),
        NodeInput(
            port_values={
                "delegation_request": requests,
                "delegation_receipt": receipts,
            }
        ),
    )
    emitted = output.port_values["delegation_receipt"]
    assert emitted == receipts
    statuses = tuple(r.status for r in emitted)
    assert statuses == ("ok", "error", "timeout")


async def test_idempotent_on_repeated_invocation() -> None:
    """C9: same input twice → identical output (repeat run)."""
    receipts = (
        _receipt(delegate_from="agent.a", payload={"v": 1}),
        _receipt(delegate_from="agent.b", payload={"v": 2}),
    )
    requests = (_request(delegate_to="agent.a"), _request(delegate_to="agent.b"))
    node_input = NodeInput(
        port_values={
            "delegation_request": requests,
            "delegation_receipt": receipts,
        }
    )
    out1 = await _executor().node_execute(_ctx(), node_input)
    out2 = await _executor().node_execute(_ctx(), node_input)
    assert out1.port_values["delegation_receipt"] == out2.port_values["delegation_receipt"]

    out3 = await _executor().node_execute(_ctx(), node_input)
    assert out3.port_values["delegation_receipt"] == out1.port_values["delegation_receipt"]
