"""Boot-once invariant: two ``create_app`` calls boot independent kernel contexts.

The kernel lifespan runs on Starlette's ``@asynccontextmanager`` lifespan;
each app gets its own cordis Context and its own disposal. This file proves:

  1. Each ``create_app()`` call boots its own context — no shared cache.
  2. Driving the lifespan on app1 does not affect app2.
  3. Library-level ``ensure_default_ctx()`` still caches so library
     callers that build ``Agent(...)`` without an explicit scope see
     one boot per process.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from gateway.app import create_app


async def _drive_lifespan(app: Any, hold: asyncio.Event | None = None) -> None:
    """Drive one Starlette lifespan to completion.

    Mirrors the test idiom ``async with app.router.lifespan_context(app)``.
    If ``hold`` is provided, the body waits on it before exiting — used
    to keep two lifespans alive in parallel.
    """
    async with app.router.lifespan_context(app) as state:
        assert state["ctx"] is not None
        assert app.state.ctx is state["ctx"]
        if hold is not None:
            await hold.wait()


@pytest.mark.asyncio
async def test_two_create_app_calls_boot_independently() -> None:
    """Two apps in one process each boot their own kernel context."""
    app1 = create_app()
    app2 = create_app()
    assert getattr(app1.state, "ctx", None) is None
    assert getattr(app2.state, "ctx", None) is None

    hold = asyncio.Event()
    t1 = asyncio.create_task(_drive_lifespan(app1, hold=hold))
    t2 = asyncio.create_task(_drive_lifespan(app2, hold=hold))
    await asyncio.sleep(0.05)
    hold.set()
    await t1
    await t2
    assert app1.state.ctx is not None
    assert app2.state.ctx is not None
    assert app1.state.ctx is not app2.state.ctx


@pytest.mark.asyncio
async def test_dispose_one_app_does_not_affect_other() -> None:
    """Disposing app1's ctx does not affect app2's booted state."""
    app1 = create_app()
    app2 = create_app()

    async with app2.router.lifespan_context(app2) as state2:
        ctx2 = state2["ctx"]
        async with app1.router.lifespan_context(app1) as state1:
            ctx1 = state1["ctx"]
            assert ctx1 is not ctx2
        # After app1 disposed, app2 is still alive.
        assert app2.state.ctx is ctx2


@pytest.mark.asyncio
async def test_ensure_default_ctx_caches_across_calls() -> None:
    """Library-level default ctx caches so Agent(...) sees one boot."""
    from lca.application.api import ensure_default_ctx

    ctx1 = await ensure_default_ctx()
    ctx2 = await ensure_default_ctx()
    assert ctx1 is ctx2, "ensure_default_ctx must cache; only one boot per process"


@pytest.mark.asyncio
async def test_lifespan_attaches_ctx_to_app_state() -> None:
    """Driving the lifespan populates ``app.state.ctx``."""
    app = create_app()
    async with app.router.lifespan_context(app) as state:
        assert state["ctx"] is not None
        assert app.state.ctx is state["ctx"]
