"""Doctor test fixtures — override the parent autouse K3 boot.

The doctor passes under test here are pure, deterministic projections
of plugin-contract / profile data; they do NOT need the live cordis
Context. The session-scoped ``_boot_default_ctx_session`` autouse
fixture in ``tests/harness/conftest.py`` boots the full K3 kernel —
useful for harness-level integration tests but redundant (and currently
broken in the worktree because of a missing observability module)
for doctor unit tests.

Per I-HPC-7 the doctor must not boot K3, write journal, or perform I/O.
We enforce that by overriding the autouse fixture with a no-op of the
same name, scoped to this subtree only. Other harness tests continue
to use the original fixture via pytest's fixture resolution rules.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(scope="session", autouse=True)
async def _boot_default_ctx_session() -> Any:
    """No-op override — doctor unit tests do not need the live cordis Context."""
    return None
