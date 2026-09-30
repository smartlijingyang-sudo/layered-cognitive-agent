"""Shared seam contract for sandbox adapters.

Both ``LocalSandboxAdapter`` and ``OnlyboxesSandboxAdapter`` implement the
``Sandbox`` protocol from ``lca.contracts.protocols``. The local adapter used
to omit the base class, so the factory's ``resolve_sandbox() -> Sandbox | None``
had a statically-uncheckable seam. These tests lock both adapters to the same
contract surface.
"""

from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest

from lca.contracts.protocols import Sandbox
from lca.infrastructure.sandbox.local.adapter import LocalSandboxAdapter
from lca.infrastructure.sandbox.onlyboxes.adapter import OnlyboxesSandboxAdapter

_PROTOCOL_METHODS = (
    "write_files",
    "run",
    "create_session",
    "run_in_session",
    "destroy_session",
    "run_terminal",
)


@pytest.mark.parametrize(
    "adapter_cls",
    [LocalSandboxAdapter, OnlyboxesSandboxAdapter],
)
def test_adapter_declares_sandbox_protocol(adapter_cls: type) -> None:
    assert issubclass(adapter_cls, Sandbox)


def test_local_adapter_imports_protocol() -> None:
    import lca.infrastructure.sandbox.local.adapter as local

    source = inspect.getsource(local)
    assert "class LocalSandboxAdapter(Sandbox)" in source


@pytest.mark.parametrize(
    "adapter_cls",
    [LocalSandboxAdapter, OnlyboxesSandboxAdapter],
)
def test_adapter_exposes_all_protocol_methods(adapter_cls: type) -> None:
    for name in _PROTOCOL_METHODS:
        assert callable(getattr(adapter_cls, name, None)), f"{adapter_cls.__name__} missing {name}"


@pytest.mark.parametrize(
    "adapter_cls",
    [LocalSandboxAdapter, OnlyboxesSandboxAdapter],
)
def test_write_files_signature_matches_protocol(adapter_cls: type) -> None:
    impl_hints = get_type_hints(adapter_cls.write_files)
    # The protocol's own annotations (returns SandboxResult) must be satisfiable.
    assert "return" in impl_hints
    assert "SandboxResult" in str(impl_hints["return"])
    # Both accept files/base_dir/session_id/timeout_s.
    sig = inspect.signature(adapter_cls.write_files)
    assert "files" in sig.parameters
    assert "base_dir" in sig.parameters
    assert "session_id" in sig.parameters
    assert "timeout_s" in sig.parameters


@pytest.mark.parametrize(
    "adapter_cls",
    [LocalSandboxAdapter, OnlyboxesSandboxAdapter],
)
def test_run_signature_matches_protocol(adapter_cls: type) -> None:
    sig = inspect.signature(adapter_cls.run)
    assert "code" in sig.parameters
    assert "language" in sig.parameters
    assert "timeout_s" in sig.parameters


def test_factory_resolve_sandbox_returns_typed_sandbox() -> None:
    """The factory's return annotation must reference the shared Sandbox protocol."""
    import lca.infrastructure.sandbox.factory.factory as factory

    hints = get_type_hints(factory.resolve_sandbox)
    assert hints["return"] == Sandbox | None


def test_no_local_adapter_without_base_class() -> None:
    """Regression guard: the local adapter must keep the explicit base class."""
    assert LocalSandboxAdapter.__mro__[1] is Sandbox
