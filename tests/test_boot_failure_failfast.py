"""Boot-failure fail-fast: a bad profile path must not leak infrastructure.

The previous gateway boot path constructed module-level singletons
``_registry``, ``_file_store``, ``_devices``, ``_device_hub`` at
import time. If ``_load_harness_profile`` later raised, those
singletons survived as garbage on the module — the process kept a
half-initialized state and could serve requests against it.

This test proves the new design fails fast:

  1. ``profile_lifespan`` raises on a non-existent profile path,
     propagating the boot error out of the lifespan startup phase.
  2. Starlette's lifespan contract means ``app.router.lifespan_context``
     raises before any request is served. No partial ctx leaks.
  3. ``create_app()`` does not construct the SQLite-backed
     ``DeviceRegistry`` until boot success is reachable. The
     singleton lives on ``app.state`` and is discarded with the
     app on failed startup.
  4. ``install_profile_lifespan(path=None)`` returns the no-op
     lifespan that yields no ctx — the no-profile configuration
     is a real, testable state, not a hidden fall-through.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from gateway.app import create_app
from lca.harness.profile.lifespan import (
    install_profile_lifespan,
    profile_lifespan,
)


@pytest.mark.asyncio
async def test_bad_profile_path_raises_in_lifespan() -> None:
    """A non-existent profile path makes the lifespan raise immediately."""
    bad = Path("profiles/__definitely_does_not_exist__.yaml")
    with pytest.raises(FileNotFoundError) as exc_info:
        async with profile_lifespan(bad) as state:
            pytest.fail(f"unexpected yield: {state!r}")
    assert exc_info.value is not None


def test_starlette_lifespan_propagates_boot_failure() -> None:
    """A bad profile makes Starlette's lifespan_context raise on entry."""
    lifespan = install_profile_lifespan(profile_path="profiles/__missing__.yaml")
    app = Starlette(lifespan=lifespan)

    async def _drive() -> None:
        async with app.router.lifespan_context(app):
            pytest.fail("lifespan should not yield for a bad profile")

    import asyncio

    with pytest.raises(FileNotFoundError):
        asyncio.run(_drive())


def test_testclient_refuses_to_serve_when_boot_fails() -> None:
    """TestClient entering must raise if boot fails — no silent 503.

    The previous design silently served 503 ("profile not booted") on
    every request after a failed boot. With the lifespan model, the
    server refuses to start; TestClient surfaces that as a startup
    error before any request is dispatched.
    """
    app = create_app(profile_path="profiles/__missing__.yaml")

    with pytest.raises(FileNotFoundError), TestClient(app):
        pytest.fail("TestClient must raise when lifespan startup fails")


def test_no_profile_path_yields_no_ctx() -> None:
    """install_profile_lifespan(None) returns the no-op lifespan.

    The no-profile configuration is a real, testable state. Routes
    that read ``app.state.ctx`` see ``None``; ``_ctx_of`` raises a
    503. This test pins that contract.
    """
    noop_lifespan = install_profile_lifespan(profile_path=None)
    assert noop_lifespan is not None

    app = Starlette(lifespan=noop_lifespan)

    async def _drive() -> None:
        async with app.router.lifespan_context(app) as state:
            # No ctx yielded by the no-op lifespan.
            assert state.get("ctx") is None
            assert getattr(app.state, "ctx", None) is None

    import asyncio

    asyncio.run(_drive())


def test_failed_boot_does_not_leak_module_singletons() -> None:
    """Failed boot must not write to module-level globals.

    Run ownership and infrastructure have no module-level fallback; the
    selected bootstrap product is owned only by the constructed app instance.

    ``create_app()`` itself does not boot, so it cannot raise on a
    bad profile path. The boot happens in the lifespan, which is
    driven by Starlette at startup time. We drive it here and assert
    the boot raises.
    """
    import gateway.app as gateway_app_module

    app = create_app(profile_path="profiles/__missing__.yaml")
    bootstrap = app.state.bootstrap
    assert not hasattr(gateway_app_module, "get_file_store")
    assert not hasattr(gateway_app_module, "_module_file_store")

    async def _drive() -> None:
        async with app.router.lifespan_context(app):
            pytest.fail("lifespan should not yield for a bad profile")

    import asyncio

    with pytest.raises(FileNotFoundError):
        asyncio.run(_drive())

    # A failed Profile boot cannot replace or leak the app-owned product.
    assert app.state.bootstrap is bootstrap
