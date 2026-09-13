"""Compile-unit fixtures — override parent harness K3 autouse boot.

``tests/harness/conftest.py`` boots ``ensure_default_ctx()`` once per
session. That path requires ``LLM_API_KEY`` (credentials plugin fail-loud).
These compile tests only pin ``wrap_instrument`` markers and GraphAssembler
unreachability — pure unit surface, no cordis Context.

Override the session autouse fixture with a no-op so the focused suite is
green without a real (or stub) API key. Other harness tests keep the
original boot via pytest fixture resolution.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(scope="session", autouse=True)
async def _boot_default_ctx_session() -> Any:
    """No-op — declarative compile unit tests do not need live K3 Context."""
    return None
