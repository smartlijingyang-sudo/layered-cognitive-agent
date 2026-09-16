"""Sandbox pool seam — PR-3 (G-22, ADR-0232).

Public surface re-exports the bounded-concurrency pool.  Body code
imports ``SandboxPool`` from here so a future migration to a
cross-worker pool can swap the implementation behind the same symbol.
"""

from lca.cognition.body.sandbox.pool import (
    PooledSandboxCall,
    PooledSandboxResult,
    SandboxPool,
    default_max_concurrency,
)

__all__ = [
    "PooledSandboxCall",
    "PooledSandboxResult",
    "SandboxPool",
    "default_max_concurrency",
]
