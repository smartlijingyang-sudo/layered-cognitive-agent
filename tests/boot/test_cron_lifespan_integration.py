"""Test Starlette lifespan integration with CronDaemonService (Task 3)."""

import tempfile
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from lca_kernel.boot.lifespan import make_lifespan


class _FakeCtx:
    def __init__(self, workspace: str, lock_dir: str):
        self.workspace = workspace
        self.lock_dir = lock_dir


@pytest.mark.asyncio
async def test_lifespan_starts_and_stops_cron_daemon():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        ctx = _FakeCtx(workspace=str(p / "ws"), lock_dir=str(p / "locks"))

        async def homepage(request):
            return PlainTextResponse("ok")

        app = Starlette(
            routes=[Route("/", homepage)],
        )
        app.router.lifespan_context = make_lifespan(ctx)

        # Simulate Starlette lifespan startup & shutdown
        async with app.router.lifespan_context(app) as state:
            assert state["ctx"] is ctx
            cron_daemon = getattr(app.state, "cron_daemon", None)
            assert cron_daemon is not None
            assert cron_daemon.is_running is True

        # After shutdown
        assert cron_daemon.is_running is False
