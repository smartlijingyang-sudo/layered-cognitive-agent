"""Harness conftest — boot the default cordis Context once per session.

The harness tests run inside an event loop (via ``asyncio.run`` in
each test). The default cached context boots via ``asyncio.run``
itself, which fails when called inside an already-running loop. To
unblock the harness tests we boot the default profile once at
session start on a side thread, then share the same Context across
all harness tests in the session.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Any

import pytest

_DEFAULT_CTX: Any = None
_BOOT_LOCK = threading.Lock()


def _boot_default_ctx_blocking() -> Any:
    """Boot the default cordis Context on a side loop.

    Returns the cached Context.  Subsequent calls return the same
    Context (the boot is cached process-wide via
    ``lca.layer4_app.api._default_ctx_holder``).
    """
    global _DEFAULT_CTX
    if _DEFAULT_CTX is not None:
        return _DEFAULT_CTX

    with _BOOT_LOCK:
        if _DEFAULT_CTX is not None:
            return _DEFAULT_CTX

        from lca.harness.profile.boot import boot_profile
        from lca.layer4_app.api import set_default_ctx

        ctx: Any = asyncio.run(boot_profile("profiles/web-standard.yaml"))
        set_default_ctx(ctx)
        _DEFAULT_CTX = ctx
        return ctx


@pytest.fixture(scope="session", autouse=True)
def _boot_default_ctx_session() -> Any:
    """Boot the default cordis Context exactly once for the harness."""
    return _boot_default_ctx_blocking()
