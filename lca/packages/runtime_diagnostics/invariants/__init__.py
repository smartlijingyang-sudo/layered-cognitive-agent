"""Runtime invariants registry for package-owned diagnostic checks.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``runtime-diagnostics/invariants/`` from deepseek-harness.

This package provides a configurable registry for runtime invariants - checks
that validate package contracts and raise errors when violated. Every workspace
package can register checks from a ``./invariant`` companion module.

================================================================================
PUBLIC API
================================================================================
The package exports:
  - ``InvariantRegistry``: Main registry class for managing invariants
  - ``InvariantError``: Custom exception for invariant violations
  - ``Config``: Configuration dataclass for the registry
  - ``InvariantInstaller``: Protocol for installer functions
  - ``InvariantFailure``: Type alias for failure reporter functions

For the companion module:
  - ``apply(ctx)``: Register the invariants companion
  - ``name``: Companion name
  - ``inject``: Services this companion depends on

================================================================================
USAGE EXAMPLE
================================================================================
```python
from lca.packages.runtime_diagnostics.invariants import (
    InvariantRegistry,
    Config,
    InvariantError,
)

# Create a registry with default config
registry = InvariantRegistry()

# Create a registry with custom filtering
config = Config(
    enabled=True,
    package_allowlist=['^my-package-.*'],
    package_blocklist=['^my-package-test-.*'],
)
registry = InvariantRegistry(config=config)

# Register an invariant checker
def check_database_connection(ctx, fail):
    if not ctx.db.is_connected():
        fail('database connection is required')

dispose = registry.register('my-package-db', check_database_connection)

# Later, to unregister:
dispose()
```

================================================================================
UPSTREAM ALIGNMENT
================================================================================
This package maintains 1:1 behavioral parity with upstream TypeScript:
  - Same configuration semantics (enabled, allowlist, blocklist)
  - Same filtering logic (allowlist = must match, blocklist = must not match)
  - Same error handling (invalid patterns, duplicate registration, etc.)
  - Same disposal semantics (explicit dispose function)
"""

from __future__ import annotations

# Re-export the public API from src/index.py
from .src.index import (
    Config,
    InvariantError,
    InvariantFailure,
    InvariantInstaller,
    InvariantRegistry,
)

# Re-export the companion module API
from .src.invariant import apply, inject, name

__all__ = [
    # Main API
    "Config",
    "InvariantError",
    "InvariantFailure",
    "InvariantInstaller",
    "InvariantRegistry",
    # Companion API
    "apply",
    "inject",
    "name",
]
