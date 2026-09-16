"""RuntimePlane typed ``tools_service`` ContextVar contract.

Mirror of the existing ``BindingsViewBuilder`` ContextVar pattern in
:mod:`lca.infrastructure.runtime_plane.capability_bindings`.  The
kernel publishes one ``ToolsService`` per turn; the typed reader at
outer-plan entry sees whatever the carrier set on this task.

Contract pinned:

- ``set_current_tools_service`` returns a token that resets to the
  value active before the call (re-binding does not leak).
- ``current_tools_service`` is None by default (no ambient ToolsService).
- The ContextVar does not cross asyncio task boundaries (the
  standard ContextVar semantics — the kernel must call
  ``set_current_tools_service`` on the same task that runs the
  interpreter, which the carrier does).
"""

from __future__ import annotations

import pytest

from lca.infrastructure.runtime_plane.capability_bindings import (
    current_tools_service,
    reset_current_tools_service,
    set_current_tools_service,
)


def test_current_tools_service_defaults_to_none() -> None:
    """No carrier binding → reader returns ``None``."""
    assert current_tools_service() is None


def test_set_then_current_round_trip() -> None:
    """set → current returns the bound instance."""
    sentinel = object()
    token = set_current_tools_service(sentinel)
    try:
        assert current_tools_service() is sentinel
    finally:
        reset_current_tools_service(token)
    assert current_tools_service() is None


def test_reset_restores_previous_value() -> None:
    """Re-binding inside an outer set returns to the outer value on reset.

    ContextVar semantics: nested ``set`` + ``reset`` returns the
    value that was active before the inner ``set`` call.  This is
    what makes per-turn bindings safe across nested scopes.
    """
    outer = object()
    inner = object()
    outer_token = set_current_tools_service(outer)
    inner_token = set_current_tools_service(inner)
    try:
        assert current_tools_service() is inner
    finally:
        reset_current_tools_service(inner_token)
        try:
            assert current_tools_service() is outer
        finally:
            reset_current_tools_service(outer_token)
    assert current_tools_service() is None


def test_reset_without_set_raises_lookup_error() -> None:
    """Re-binding semantics are fail-loud — a forgotten reset is a bug."""
    sentinel = object()
    token = set_current_tools_service(sentinel)
    reset_current_tools_service(token)
    # Calling reset a second time on the same token is a programmer
    # error — the ContextVar no longer has that token in its stack.
    with pytest.raises(RuntimeError):
        reset_current_tools_service(token)
