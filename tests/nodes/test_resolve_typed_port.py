"""Tests for the RA-130 ``required`` flag on ``resolve_typed_port_or_runtime``.

Covers the new ``required=False`` (fail-soft) branch alongside the unchanged
``required=True`` (fail-loud, default) branch: port wins over runtime, runtime
fallback, and the empty case.
"""

from typing import Any

import pytest

from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.nodes._resolve import resolve_typed_port_or_runtime

_STATE = PortName("state")


def _ctx(runtime: Any) -> NodeContext:
    return NodeContext(runtime=runtime, budget={}, metadata={})


def test_ra130_port_value_wins_over_runtime() -> None:
    """Declared port beats the runtime carrier even when both are present."""
    resolved = resolve_typed_port_or_runtime(
        _STATE,
        input=NodeInput(port_values={_STATE: "port-state"}),
        context=_ctx({"state": "runtime-state"}),
        node="shortcut.try",
        required=False,
    )
    assert resolved == "port-state"


def test_ra130_runtime_fallback_when_port_missing() -> None:
    """Missing port falls back to the runtime carrier."""
    resolved = resolve_typed_port_or_runtime(
        _STATE,
        input=NodeInput(port_values={}),
        context=_ctx({"state": "runtime-state"}),
        node="shortcut.try",
        required=False,
    )
    assert resolved == "runtime-state"


def test_ra130_fail_soft_returns_none_when_both_missing() -> None:
    """required=False: empty port + empty carrier returns None."""
    resolved = resolve_typed_port_or_runtime(
        _STATE,
        input=NodeInput(port_values={}),
        context=_ctx({}),
        node="shortcut.try",
        required=False,
    )
    assert resolved is None


def test_ra130_fail_loud_default_raises_naming_node() -> None:
    """required=True (default): empty port + empty carrier raises TypeError."""
    with pytest.raises(TypeError) as excinfo:
        resolve_typed_port_or_runtime(
            _STATE,
            input=NodeInput(port_values={}),
            context=_ctx({}),
            node="shortcut.try",
        )
    assert "shortcut.try" in str(excinfo.value)
    assert "'state' port must be supplied" in str(excinfo.value)
