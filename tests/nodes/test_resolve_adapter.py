"""Tests for the RA-123 ``resolve_runtime_adapter`` seam (``lca/nodes/_resolve.py``).

Covers both ``required`` branches of the converged two-shape ``adapter``
probe: fail-loud (``think.llm.invoke``) and fail-soft
(``reflect.memory_extract``).
"""

from typing import Any

import pytest

from lca.contracts.protocols.declarative.declarative_1.node_executor import NodeContext
from lca.nodes._resolve import resolve_runtime_adapter


class _AttributeRuntime:
    """Attribute-style runtime carrier exposing ``adapter`` as an attribute."""

    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter


def _ctx(runtime: Any) -> NodeContext:
    return NodeContext(runtime=runtime, budget={}, metadata={})


def test_ra123_attribute_carrier_resolves_adapter() -> None:
    """Attribute-shaped carrier resolves via getattr (think.llm.invoke path)."""
    sentinel = object()
    resolved = resolve_runtime_adapter(context=_ctx(_AttributeRuntime(sentinel)), node="llm.invoke")
    assert resolved is sentinel


def test_ra123_mapping_carrier_resolves_adapter_via_get() -> None:
    """Mapping-shaped carrier resolves via ``.get`` (runtime is typed Mapping)."""
    sentinel = object()
    resolved = resolve_runtime_adapter(context=_ctx({"adapter": sentinel}), node="llm.invoke")
    assert resolved is sentinel


def test_ra123_fail_loud_missing_adapter_raises_naming_node() -> None:
    """required=True (default): missing adapter raises TypeError naming the node."""
    with pytest.raises(TypeError) as excinfo:
        resolve_runtime_adapter(context=_ctx({}), node="llm.invoke")
    assert "llm.invoke" in str(excinfo.value)
    assert "'adapter' must be supplied via context.runtime" in str(excinfo.value)


def test_ra123_fail_soft_missing_adapter_returns_none() -> None:
    """required=False: missing adapter returns None (memory_extract passthrough path)."""
    resolved = resolve_runtime_adapter(
        context=_ctx({}), node="phase.reflect.memory.extract", required=False
    )
    assert resolved is None


def test_ra123_runtime_none_fail_loud_raises() -> None:
    """runtime is None + required=True raises (same as a missing adapter)."""
    with pytest.raises(TypeError) as excinfo:
        resolve_runtime_adapter(context=_ctx(None), node="llm.invoke")
    assert "'adapter' must be supplied via context.runtime" in str(excinfo.value)


def test_ra123_runtime_none_fail_soft_returns_none() -> None:
    """runtime is None + required=False returns None."""
    resolved = resolve_runtime_adapter(
        context=_ctx(None), node="phase.reflect.memory.extract", required=False
    )
    assert resolved is None
