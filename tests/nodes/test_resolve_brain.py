"""Tests for the RA-129 ``resolve_runtime_brain`` seam (``lca/nodes/_resolve.py``).

Covers both ``required`` branches of the converged two-shape ``brain`` probe:
fail-loud and fail-soft (the default — every current brain consumer treats
``None`` as absent). Mirrors the RA-123 seam-test shape.
"""

from typing import Any

import pytest

from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext
from lca.nodes._resolve import resolve_runtime_brain


class _AttributeRuntime:
    """Attribute-style runtime carrier exposing ``brain`` as an attribute."""

    def __init__(self, brain: Any) -> None:
        self.brain = brain


def _ctx(runtime: Any) -> NodeContext:
    return NodeContext(runtime=runtime, budget={}, metadata={})


def test_ra129_attribute_carrier_resolves_brain() -> None:
    """Attribute-shaped carrier resolves via getattr (think.gate path)."""
    sentinel = object()
    resolved = resolve_runtime_brain(context=_ctx(_AttributeRuntime(sentinel)), node="think.gate")
    assert resolved is sentinel


def test_ra129_mapping_carrier_resolves_brain_via_get() -> None:
    """Mapping-shaped carrier resolves via ``.get`` (runtime is typed Mapping)."""
    sentinel = object()
    resolved = resolve_runtime_brain(context=_ctx({"brain": sentinel}), node="think.gate")
    assert resolved is sentinel


def test_ra129_fail_loud_missing_brain_raises_naming_node() -> None:
    """required=True: missing brain raises TypeError naming the node."""
    with pytest.raises(TypeError) as excinfo:
        resolve_runtime_brain(context=_ctx({}), node="think.gate", required=True)
    assert "think.gate" in str(excinfo.value)
    assert "'brain' must be supplied via context.runtime" in str(excinfo.value)


def test_ra129_fail_soft_missing_brain_returns_none() -> None:
    """required=False (default): missing brain returns None."""
    resolved = resolve_runtime_brain(context=_ctx({}), node="think.gate")
    assert resolved is None


def test_ra129_runtime_none_fail_loud_raises() -> None:
    """runtime is None + required=True raises (same as a missing brain)."""
    with pytest.raises(TypeError) as excinfo:
        resolve_runtime_brain(context=_ctx(None), node="think.gate", required=True)
    assert "'brain' must be supplied via context.runtime" in str(excinfo.value)


def test_ra129_runtime_none_fail_soft_returns_none() -> None:
    """runtime is None + required=False returns None."""
    resolved = resolve_runtime_brain(context=_ctx(None), node="think.gate")
    assert resolved is None
