"""Harness conftest — pre-boot the default library ctx once per session.

Tests that drive the gateway use their own Starlette app + lifespan.
Tests that exercise the library API (``Agent(...)``, ``Team(...)``,
``ensure_default_ctx()``, ``get_or_create_default_ctx()``) share the
process-level default ctx holder. We boot it once at session start
on whatever event loop pytest-asyncio creates for the session.

The previous implementation booted on a side thread to dodge an
"asyncio.run inside a running loop" error. That hack is gone; we use
the same loop the tests run on, so the ctx and the tests share
asyncio primitives.
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.layer4_app.api import ensure_default_ctx


@pytest.fixture(scope="session", autouse=True)
async def _boot_default_ctx_session() -> Any:
    """Boot the default cordis Context exactly once for the session.

    Subsequent ``ensure_default_ctx()`` calls return the cached ctx
    immediately; ``get_or_create_default_ctx()`` also returns it
    (cache-warm path). Tests that build their own Starlette app
    use their own lifespan and ignore this ctx.
    """
    return await ensure_default_ctx()
