"""Test cron daemon lifecycle via the webserver plugin setup path (RA-088).

The daemon's start/stop composition lives in the webserver plugin's named
step ``start_cron_daemon``; ``lca_kernel.boot.lifespan.make_lifespan`` is a
pure Starlette-lifespan protocol impl that only *stops* a mounted daemon at
shutdown.  The old ``_FakeCtx`` semantics (explicit workspace / lock_dir
drive the daemon) are preserved as explicit parameters of the named step —
no getattr duck-reads on ctx.
"""

import tempfile
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from lca.plugins.transport.webserver.server.server import start_cron_daemon
from lca_kernel.boot.lifespan import make_lifespan


@pytest.mark.asyncio
async def test_plugin_setup_path_starts_and_stops_cron_daemon():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)

        async def homepage(request):
            return PlainTextResponse("ok")

        app = Starlette(routes=[Route("/", homepage)])

        # Plugin setup path: the named step starts the daemon and the
        # caller mounts it on app.state (mirrors server.setup() step 3e).
        cron_daemon = await start_cron_daemon(
            app, lock_dir=p / "locks", workspace_path=str(p / "ws")
        )
        assert cron_daemon is not None
        app.state.cron_daemon = cron_daemon
        assert cron_daemon.is_running is True

        # The lifespan protocol only disposes at shutdown.
        app.router.lifespan_context = make_lifespan(object())
        async with app.router.lifespan_context(app) as state:
            assert state["ctx"] is not None
            assert getattr(app.state, "cron_daemon", None) is cron_daemon

        # After shutdown
        assert cron_daemon.is_running is False


@pytest.mark.asyncio
async def test_lifespan_alone_does_not_construct_cron():
    """make_lifespan is a pure protocol impl: startup mounts ctx only."""
    app = Starlette(routes=[])
    ctx = object()
    app.router.lifespan_context = make_lifespan(ctx)

    async with app.router.lifespan_context(app) as state:
        assert state["ctx"] is ctx
        assert getattr(app.state, "cron_daemon", None) is None

    assert app.state.ctx is None
