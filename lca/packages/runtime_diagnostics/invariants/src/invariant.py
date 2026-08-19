"""Package-owned invariant companion for the invariants package.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``runtime-diagnostics/invariants/src/invariant.ts`` from deepseek-harness.

This module provides the invariant companion for the invariants package itself.
It follows the same pattern as other packages - a no-op installer that registers
with the invariant registry.

================================================================================
KEY BEHAVIORS
================================================================================
1. NO-OP INSTALLER: The invariants package has no runtime invariants to check.
   Registration ownership and child lifecycle are the service's mutation boundary
   itself, so observing them would only duplicate the implementation.

2. REGISTRATION: The companion registers itself with the invariant registry
   under the package name ``@deepseek-ai/dsh-invariants``.

3. METADATA: Exports standard companion metadata (name, inject, apply) for
   integration with the Cordis plugin system.

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- No async operations needed (installer is synchronous)
- Context parameter is unused but included for API compatibility
- Returns a no-op dispose function for consistency

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/runtime-diagnostics/invariants/test_invariant.py`` exercise:
  - Companion metadata exports
  - Apply function registration
  - Dispose function behavior
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PACKAGE_NAME = "@deepseek-ai/dsh-invariants"


# ---------------------------------------------------------------------------
# Public: name
# ---------------------------------------------------------------------------
# Companion name for plugin registration
name = "invariants-invariant"


# ---------------------------------------------------------------------------
# Public: inject
# ---------------------------------------------------------------------------
# List of services this companion depends on
inject = ["invariants"]


# ---------------------------------------------------------------------------
# Internal: _install
# ---------------------------------------------------------------------------
# No-op installer function. The invariants package has no runtime invariants
# to check - registration ownership is the service's mutation boundary itself.
def _install(ctx: Any, fail: Callable[[str], None]) -> None:
    """Install the invariants package's invariant checks.

    This is a no-op because the invariants package has no runtime invariants
    to check. Registration ownership and child lifecycle are the service's
    mutation boundary itself.

    Args:
        ctx: Child context (unused).
        fail: Failure reporter (unused).
    """
    pass


# ---------------------------------------------------------------------------
# Public: apply
# ---------------------------------------------------------------------------
# Apply function that registers this companion with the invariant registry.
# Returns a dispose function that can be called to unregister.
def apply(ctx: Any) -> Callable[[], None]:
    """Register this package's invariant companion.

    Args:
        ctx: Context carrying the invariant service.

    Returns:
        A disposer function that unregisters the companion.
    """
    # Get the invariant registry from the context
    registry = ctx.invariants

    # Register with the no-op installer
    return registry.register(PACKAGE_NAME, _install)


__all__ = [
    "apply",
    "inject",
    "name",
]
