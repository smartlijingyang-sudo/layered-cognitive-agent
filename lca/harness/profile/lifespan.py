"""Starlette lifespan wrapper around ``boot_profile`` (ADR-0062+).

The server startup lifecycle is the single legal place to boot a harness
plugin tree. This module turns the async ``boot_profile`` primitive into
a Starlette lifespan context manager, so the server framework owns
startup → run → shutdown semantics and the plugin tree never leaks
across processes or races during boot.

Public API
----------
- :func:`profile_lifespan` — async context manager that boots ``boot_profile``
  on enter and ``await ctx.dispose()`` on exit. Yields ``{"ctx": <Context>}``
  for the lifespan protocol.
- :func:`noop_lifespan` — empty lifespan for the no-profile case; emits no
  boot, exposes no ctx, lets routes see ``app.state.ctx is None``.
- :func:`install_profile_lifespan` — wires the lifespan onto a Starlette
  app in one call. Used by :func:`gateway.app.create_app`.

Why a dedicated module
----------------------
The previous gateway boot path lived in :mod:`gateway.app` and ran boot
synchronously inside ``create_app`` by spinning up an isolated event loop
(``asyncio.new_event_loop`` + ``run_until_complete``). That workaround
broke the framework's startup contract: any async primitive (Event, Lock,
Queue) created during boot ended up bound to the throwaway loop and died
when ``loop.close()`` ran, only to be reused from uvicorn's main loop.

Moving boot into the Starlette lifespan means boot runs on the same loop
that serves requests — one event loop for the whole process, no detached
primitives, no leak on shutdown.

Boot failure contract
---------------------
If ``boot_profile`` raises, the lifespan startup raises. ``create_app``
then refuses to install routes against an unbooted app. No
module-level infrastructure is constructed until after a successful
boot, so a failed startup leaves the process in a clean state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

import structlog

from lca.layer0_infra.file_store import FileStore

_log = structlog.get_logger("lca.harness.profile.lifespan")


class _LifespanApp(Protocol):
    """Minimal Starlette app surface needed by the lifespan wrappers."""

    router: Any
    state: Any


@asynccontextmanager
async def profile_lifespan(
    profile_path: str | Path,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Boot ``boot_profile`` on enter, ``ctx.dispose()`` on exit.

    Yields ``{"ctx": <Context>}`` per Starlette's lifespan protocol.
    Boot failure propagates as a startup error — there is no recovery
    path inside the lifespan. The server framework handles the failure
    by refusing to start.
    """
    profile_path = Path(profile_path)
    _log.info("harness_profile_boot_starting", profile=str(profile_path))
    ctx = await boot_profile(profile_path, bootstrap_file_store=bootstrap_file_store)
    try:
        from lca.harness.profile.boot_products import resolved_profile_from_scope

        resolved = resolved_profile_from_scope(ctx)
        plugin_count = (
            0 if resolved is None else sum(1 for plugin in resolved.plugins if not plugin.disabled)
        )
        _log.info(
            "harness_profile_boot_ready",
            profile=str(profile_path),
            plugin_count=plugin_count,
        )
        yield {"ctx": ctx}
    finally:
        _log.info("harness_profile_boot_disposing", profile=str(profile_path))
        await ctx.dispose()


@asynccontextmanager
async def starlette_profile_lifespan(
    app: _LifespanApp,
    profile_path: str | Path,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Starlette-aware wrapper: boot profile, install ctx on app.state.

    This is the lifespan that ``install_profile_lifespan`` returns for
    the gateway: it sets ``app.state.ctx`` so request handlers and the
    session spine can resolve the booted plugin tree on every call.

    Tests that drive the lifespan via ``app.router.lifespan_context(app)``
    see the same effect — the handler runs only after ``app.state.ctx``
    has been populated by this wrapper.
    """
    async with profile_lifespan(profile_path, bootstrap_file_store=bootstrap_file_store) as state:
        app.state.ctx = state["ctx"]
        # Bind the boot-time BoundObservability (with evidence_store / evidence_policy
        # capability seams from lca-evidence-store-seam) to app.state so the
        # /runs/{id}/evidence/{ref} endpoint can resolve it. ADR-0065 §四 L5.
        from lca.contracts.mechanisms.capability import require_capability
        from lca.layer0_infra.observability import BoundObservability

        bound: BoundObservability | None = None
        try:
            cand = require_capability(state["ctx"], "observability")
            if isinstance(cand, BoundObservability):
                bound = cand
        except Exception:
            bound = None
        app.state.bound_observability = bound
        try:
            yield state
        finally:
            with suppress(AttributeError):
                del app.state.ctx
            with suppress(AttributeError):
                del app.state.bound_observability


@asynccontextmanager
async def noop_lifespan(_app: _LifespanApp) -> AsyncIterator[dict[str, Any]]:
    """Empty lifespan for the no-profile configuration.

    Routes that read ``app.state.ctx`` will see ``None``; they are
    expected to surface a 503 in that case (``gateway.runs.query_endpoints._ctx_of``).
    """
    yield {}


def install_profile_lifespan(
    profile_path: str | Path | None,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Callable[[_LifespanApp], Any]:
    """Return the lifespan callable Starlette should install.

    Pass the result as the ``lifespan=`` argument to ``Starlette(...)``.
    The returned callable accepts the Starlette app as its sole argument
    per the lifespan protocol, so it is plug-compatible with the framework.
    The ``app`` argument is required at lifespan invocation time (by
    Starlette's protocol); it is not needed at install time.

    The returned lifespan writes ``app.state.ctx`` so the gateway's
    request handlers can read the booted ctx on the first try.
    """
    if profile_path is None:
        return noop_lifespan
    profile_path = Path(profile_path)
    return _make_profile_lifespan(profile_path, bootstrap_file_store=bootstrap_file_store)


def _make_profile_lifespan(
    profile_path: Path,
    *,
    bootstrap_file_store: FileStore | None = None,
) -> Callable[[_LifespanApp], Any]:
    """Closure factory: bind ``profile_path`` so the lifespan is reusable."""

    @asynccontextmanager
    async def _bound_lifespan(app: _LifespanApp) -> AsyncIterator[dict[str, Any]]:
        async with starlette_profile_lifespan(
            app,
            profile_path,
            bootstrap_file_store=bootstrap_file_store,
        ) as state:
            yield state

    _bound_lifespan.__name__ = f"profile_lifespan[{profile_path.name}]"
    return _bound_lifespan


# Local import to keep this module importable from sync contexts without
# pulling cordis / the whole harness boot chain until the lifespan is
# actually entered. ``boot_profile`` is the single existing async boot
# primitive (ADR-0061 / ADR-0062).
from lca.harness.profile.boot import boot_profile  # noqa: E402

__all__ = [
    "install_profile_lifespan",
    "noop_lifespan",
    "profile_lifespan",
    "starlette_profile_lifespan",
]
