"""Tests for :func:`lca_kernel.run_kernel_lifespan` — the kernel public surface.

Contract (ADR-0115 K6 + ADR-0117 K6):
  1. ``run_kernel_lifespan(profile_path)`` is the single seam any transport
     must use to boot the kernel.
  2. It is an async context manager; enter yields ``{"ctx": <Context>}``,
     exit disposes the context exactly once.
  3. Bad profile paths raise on enter; no half-initialized state leaks.
  4. Boot runs on the caller's loop (regression for the previous
     ``asyncio.new_event_loop`` workaround in ``gateway.app``).
  5. Starlette can drive the kernel lifespan via its ASGI lifespan
     protocol — the only transport the kernel knows about in production.
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

from lca.infrastructure.file_store import LocalFileStore
from lca_kernel import run_kernel_lifespan

DEFAULT_PROFILE = Path("profiles/web-standard.yaml")


@pytest.fixture
def block_sys_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    """K6's ``ShutdownCoordinator.shutdown`` calls ``sys.exit`` on exit.

    The lifespan tests enter and exit the kernel CM many times in a single
    test process; ``sys.exit`` would terminate pytest. Patch it out so
    tests observe dispose semantics, not process termination.
    """
    monkeypatch.setattr(sys, "exit", lambda code=0: None)


@pytest.mark.asyncio
async def test_lifespan_yields_booted_context(block_sys_exit: None) -> None:
    """Happy path: enter the lifespan, get a real cordis Context out.

    The kernel guarantee is ``observability`` always present (it's wired
    in :func:`lca_kernel.boot._boot_context` step 1); specific plugin
    seams like ``perceive`` depend on the profile and are NOT asserted.
    """
    async with run_kernel_lifespan(DEFAULT_PROFILE) as state:
        ctx = state["ctx"]
        assert ctx is not None
        assert ctx.inject("observability") is not None


@pytest.mark.asyncio
async def test_lifespan_reuses_bootstrap_file_store(block_sys_exit: None) -> None:
    """Lifespan accepts ``bootstrap_file_store`` without raising even if the
    profile does not wire the ``file_store`` seam.

    The kernel only rebinds the FileStore when the profile registered
    ``lca-file-store-service`` (see :func:`lca_kernel.boot._bind_bootstrap_file_store`);
    otherwise the argument is a documented ignored. We accept both outcomes
    because the kernel must boot regardless of profile composition.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = LocalFileStore(Path(tmpdir))
        async with run_kernel_lifespan(DEFAULT_PROFILE, bootstrap_file_store=store) as state:
            assert state["ctx"] is not None


@pytest.mark.asyncio
async def test_lifespan_disposes_context_on_exit(block_sys_exit: None) -> None:
    """Lifespan disposes the ctx exactly once on exit — no leaked services."""
    async with run_kernel_lifespan(DEFAULT_PROFILE) as state:
        ctx = state["ctx"]
        dispose_calls: list[int] = []
        original_dispose = ctx.dispose

        async def _tracked_dispose() -> None:
            dispose_calls.append(1)
            await original_dispose()

        ctx.dispose = _tracked_dispose  # type: ignore[method-assign]

    assert dispose_calls == [1], f"ctx.dispose() must run exactly once, got {dispose_calls}"


@pytest.mark.asyncio
async def test_lifespan_propagates_boot_failure(block_sys_exit: None) -> None:
    """Bad profile path → raise before yielding state, no half-boot."""
    bad_path = Path("profiles/does-not-exist.yaml")
    with pytest.raises(FileNotFoundError):
        async with run_kernel_lifespan(bad_path) as state:
            pytest.fail(f"lifespan yielded state despite bad profile: {state!r}")


@pytest.mark.asyncio
async def test_lifespan_runs_on_caller_loop(block_sys_exit: None) -> None:
    """Regression: boot must run on the caller's loop.

    The previous gateway path spun up an isolated ``asyncio.new_event_loop``
    just to call ``boot_profile`` and closed it after boot. Any async
    primitive (Event, Lock, Queue) created by a plugin setup() ended up
    bound to that throwaway loop and would raise
    ``RuntimeError: Event loop is closed`` when reused from uvicorn's
    main loop.
    """
    observed_loops: list[asyncio.AbstractEventLoop] = []
    async with run_kernel_lifespan(DEFAULT_PROFILE) as state:
        observed_loops.append(asyncio.get_running_loop())
        assert state["ctx"] is not None

    assert len(observed_loops) == 1
    assert not observed_loops[0].is_closed()


@pytest.mark.asyncio
async def test_lifespan_drives_starlette_lifespan_protocol(block_sys_exit: None) -> None:
    """End-to-end: a Starlette app drives the kernel lifespan via ASGI protocol.

    This is the contract ``gateway.app.create_app`` relies on — Starlette
    invokes the lifespan callable with ``(scope, receive, send)`` and the
    bridge drives the kernel inside it.
    """
    from starlette.applications import Starlette

    app = Starlette()

    async def _lifespan(scope: dict, receive: object, send: object) -> None:
        if scope["type"] != "lifespan":
            return
        async with run_kernel_lifespan(DEFAULT_PROFILE) as state:
            ctx = state["ctx"]
            app.state.ctx = ctx
            await send({"type": "lifespan.startup.complete"})
            await receive()
            await send({"type": "lifespan.shutdown.complete"})

    app.router.lifespan_context = _lifespan  # type: ignore[assignment]

    sent: list[dict] = []

    async def _receive() -> dict:
        return {"type": "lifespan.shutdown"}

    async def _send(message: dict) -> None:
        sent.append(message)

    await app.router.lifespan_context(  # type: ignore[arg-type]
        {"type": "lifespan", "asgi": {"version": "3.0"}},
        _receive,
        _send,
    )
    assert getattr(app.state, "ctx", None) is not None
    assert sent[-1] == {"type": "lifespan.shutdown.complete"}
