"""Diagnostic test for the SA-7 root cause: verify _resolve_model_visible_hook
on a real cordis Context that's been booted with the model_visible publisher.

If this test returns the hook, the wiring is fine.
If it returns None, instrument_llm() degrades to telemetry-only wrapping and
the spine events never get written.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from cordis import Context


@pytest.fixture
def cordis_with_hook() -> Any:
    """cordis Context with events.model_visible.publisher setup() called."""
    from pydantic import BaseModel

    from lca.plugins.events.publishers.model_visible.publisher import (
        setup as mv_setup,
    )

    captured: dict[str, Any] = {}

    class _StubPluginContext:
        def provide(self, key: Any, value: Any, **_kwargs: Any) -> None:
            captured[str(key)] = value

    class _Config(BaseModel):
        model_config = {"extra": "forbid"}

    setup_fn = getattr(mv_setup, "setup", mv_setup)
    asyncio.run(setup_fn(_StubPluginContext(), _Config()))

    ctx = Context()
    ctx.own_bindings.update(captured)
    return ctx


def test_resolve_hook_with_provided_binding(cordis_with_hook: Any) -> None:
    """Resolve hook from a Context where setup() provided it."""
    from lca.plugins.composer.think.brain import _resolve_model_visible_hook

    ctx = cordis_with_hook
    print("\nctx.own_bindings keys:", list(ctx.own_bindings.keys()))
    print("ctx has soft_get attr:", hasattr(ctx, "soft_get"))

    resolved = _resolve_model_visible_hook(ctx)
    print("resolved:", type(resolved).__name__ if resolved else None)
    assert resolved is not None, (
        "model_visible hook was provided on ctx but _resolve_model_visible_hook returned None"
    )


def test_resolve_hook_on_child_scope(cordis_with_hook: Any) -> None:
    """Resolve hook from a child scope; parent provides the binding."""
    from lca.plugins.composer.think.brain import _resolve_model_visible_hook

    child = cordis_with_hook.scope("child").scoped
    print("\nchild.own_bindings:", list(child.own_bindings.keys()))
    print("child.parent.own_bindings:", list(cordis_with_hook.own_bindings.keys()))

    resolved = _resolve_model_visible_hook(child)
    print("resolved on child:", type(resolved).__name__ if resolved else None)
    assert resolved is not None, "child scope failed to walk parent chain"


def test_resolve_hook_with_None() -> None:
    """None ctx → None returned (the test/off-boot path)."""
    from lca.plugins.composer.think.brain import _resolve_model_visible_hook

    assert _resolve_model_visible_hook(None) is None
