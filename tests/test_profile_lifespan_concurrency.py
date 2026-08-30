"""Boot-once invariant: gateway create_app + lifespan must not double-boot.

The previous gateway boot path ran boot inside ``create_app`` and used
module-level globals as a cache. Tests that called ``create_app``
twice in one process saw the second call short-circuit on the cached
ctx; a boot race could corrupt the cache.

The new design moves boot into the Starlette lifespan. Two
``create_app()`` calls in the same process produce two independent
apps, each with its own lifespan. This test proves:

  1. Each app's lifespan boots independently — no shared cache.
  2. Both boots produce a valid cordis Context with services mounted.
  3. Driving the lifespan on each app does not cross-pollute state:
     disposing app1's ctx does not affect app2's ctx.
  4. The library-level ``ensure_default_ctx()`` still caches so
     library callers that build ``Agent(...)`` without an explicit
     scope see one boot across the process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from gateway.app import create_app
from lca.harness.profile.lifespan import install_profile_lifespan

if TYPE_CHECKING:
    from starlette.applications import Starlette


@pytest.mark.asyncio
async def test_two_create_app_calls_boot_independently() -> None:
    """Two apps in one process boot their own ctx; no shared state."""
    app1 = create_app()
    app2 = create_app()

    # No boot has happened yet — both apps have ctx=None on state.
    assert getattr(app1.state, "ctx", None) is None
    assert getattr(app2.state, "ctx", None) is None

    # Drive each lifespan separately. Each must produce its own ctx.
    async with app1.router.lifespan_context(app1) as state1:
        ctx1 = state1["ctx"]
        assert ctx1 is not None
        # Mid-flight: only app1's ctx is set.
        assert app1.state.ctx is ctx1
        assert getattr(app2.state, "ctx", None) is None

        async with app2.router.lifespan_context(app2) as state2:
            ctx2 = state2["ctx"]
            assert ctx2 is not None
            # Both apps booted independently.
            assert app1.state.ctx is ctx1
            assert app2.state.ctx is ctx2
            assert ctx1 is not ctx2  # independent cordis Contexts

            # Both have the perceive service mounted — the boot worked
            # for each one independently.
            assert ctx1.inject("perceive") is not None
            assert ctx2.inject("perceive") is not None


@pytest.mark.asyncio
async def test_dispose_one_app_does_not_affect_other() -> None:
    """Each app's lifecycle is independent: dispose of one, the other survives."""
    app1 = create_app()
    app2 = create_app()

    async with app2.router.lifespan_context(app2) as state2:
        ctx2 = state2["ctx"]
        # While app2 is alive, enter and exit app1's lifespan.
        async with app1.router.lifespan_context(app1) as state1:
            ctx1 = state1["ctx"]
            assert ctx1 is not ctx2
        # After app1's lifespan exits, app2 is still alive.
        assert app2.state.ctx is ctx2
        assert ctx2.inject("perceive") is not None


def test_two_testclients_each_boot_separately() -> None:
    """Two TestClient sessions in one process each see their own boot.

    This mirrors the most common test pattern (multiple fixtures,
    multiple apps) and proves there is no module-level cross-pollution.
    """
    app1 = create_app()
    app2 = create_app()
    seen_ctx: list[object] = []

    # Drive the lifespans explicitly to capture the ctx objects.
    async def _record(app: Starlette) -> None:
        async with app.router.lifespan_context(app) as state:
            seen_ctx.append(state["ctx"])

    import asyncio

    asyncio.run(_record(app1))
    asyncio.run(_record(app2))

    assert len(seen_ctx) == 2
    assert seen_ctx[0] is not seen_ctx[1]


@pytest.mark.asyncio
async def test_ensure_default_ctx_caches_across_calls() -> None:
    """Library-level default ctx caches so Agent(...) sees one boot."""
    from lca.layer4_app.api import ensure_default_ctx

    ctx1 = await ensure_default_ctx()
    ctx2 = await ensure_default_ctx()
    assert ctx1 is ctx2, "ensure_default_ctx must cache; only one boot per process"


def test_install_profile_lifespan_path_attaches_ctx_to_app_state() -> None:
    """install_profile_lifespan's output, when Starlette drives it,
    exposes the booted ctx on app.state.ctx on the first try.
    """
    from starlette.applications import Starlette

    lifespan = install_profile_lifespan(profile_path="profiles/web-standard.yaml")
    app = Starlette(lifespan=lifespan)

    async def _go() -> None:
        async with app.router.lifespan_context(app) as state:
            assert state["ctx"] is not None
            assert app.state.ctx is state["ctx"]

    import asyncio

    asyncio.run(_go())
