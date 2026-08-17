"""1:1 port of ``@deepseek-ai/dsh-agent-tool-presentation/invariant``.

Package-owned invariant companion for ``@deepseek-ai/dsh-agent-tool-presentation``.

No runtime invariant: this package makes exactly one scoped call into
``ctx.tools`` and owns no event or snapshot of its own; the relation it
establishes — which presentation one agent's assembly uses — is the tool
registry's to hold, and ``dsh-tools`` observes it there.
"""

from __future__ import annotations

from collections.abc import Callable

PACKAGE_NAME: str = "@deepseek-ai/dsh-agent-tool-presentation"

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------

name: str = "tool-presentation-invariant"
"""Cordis companion plugin name."""

inject: tuple[str, ...] = ("invariants",)
"""Service required before the companion can reserve package ownership."""

# ---------------------------------------------------------------------------
# Installer / registration
# ---------------------------------------------------------------------------


def _install(ctx: object, fail: Callable[[str], None]) -> None:
    """No runtime invariant (see module docstring)."""


def apply(ctx: object) -> Callable[[], None]:
    """Register this package's invariant companion.

    Returns:
        The installed registration's disposer after setup succeeds.
    """
    ctx.invariants.register(PACKAGE_NAME, _install)  # type: ignore[attr-defined]
    return lambda: None
