"""Gateway can inject a preferred Sandbox (connected host)."""

from __future__ import annotations

from lca.layer0_infra.sandbox.factory import resolve_sandbox, set_sandbox_resolver


class _Host:
    name = "host"


def test_override_preferred_then_cleared() -> None:
    host = _Host()
    set_sandbox_resolver(lambda: host)  # type: ignore[arg-type,return-value]
    try:
        assert resolve_sandbox() is host
    finally:
        set_sandbox_resolver(None)
    # After clear, we only assert the override is gone — Onlyboxes may or may not exist.
    found = resolve_sandbox()
    assert found is not host
