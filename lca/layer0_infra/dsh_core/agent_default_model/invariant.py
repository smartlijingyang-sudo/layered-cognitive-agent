"""1:1 port of ``@deepseek-ai/dsh-agent-default-model/invariant``.

Package-owned invariant companion for the default Agent model selection.

The service owns no independent event relationship: settings registration
already validates every mutable value before ``current_selection()`` can
observe it.  The empty installer keeps that absence explicit in composed
invariant sets.
"""

from __future__ import annotations

from collections.abc import Callable

PACKAGE_NAME: str = "@deepseek-ai/dsh-agent-default-model"

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------

name: str = "agent-default-model-invariant"
"""Cordis companion plugin name."""

inject: tuple[str, ...] = ("invariants",)
"""Services required before the companion can register."""

# ---------------------------------------------------------------------------
# Installer / registration
# ---------------------------------------------------------------------------


def _install(ctx: object, fail: Callable[[str], None]) -> None:
    """No runtime invariant: settings validation owns the only mutable-value relationship."""


def apply(ctx: object) -> Callable[[], None]:
    """Register the intentionally empty invariant contribution.

    Returns:
        The installed registration's disposer after setup succeeds.
    """
    ctx.invariants.register(PACKAGE_NAME, _install)  # type: ignore[attr-defined]
    return lambda: None
