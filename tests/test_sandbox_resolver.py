"""Sandbox override is for real Sandboxes, not Host."""

from __future__ import annotations

from lca.infrastructure.sandbox.factory import resolve_sandbox, set_sandbox_resolver
from tests.support.inline_sandbox import InlineSandbox


def test_override_preferred_then_cleared() -> None:
    sandbox = InlineSandbox()
    set_sandbox_resolver(lambda: sandbox)
    try:
        assert resolve_sandbox() is sandbox
    finally:
        set_sandbox_resolver(None)
    found = resolve_sandbox()
    assert found is not sandbox
