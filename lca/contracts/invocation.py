"""Compat re-export — use ``lca.contracts.run_context.RunContext``.

# DEPRECATED: remove after one release cycle.
"""

from __future__ import annotations

from lca.contracts.run_context import RunContext

# Transitional alias — remove after one release cycle.
InvocationContext = RunContext

__all__ = ["InvocationContext", "RunContext"]
