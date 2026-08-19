"""Anonymous User ID package for DSH (DeepSeek Harness).

================================================================================
PACKAGE PURPOSE
================================================================================
Provides a persistent, per-harness-home anonymous user identifier (UUID v4) used
by telemetry and feedback systems. The id is:
  - Persistent across process restarts (stored in ``$DSH_HOME/.anonymous-user-id``)
  - Scoped to the harness home directory (different homes get different ids)
  - Never derived from hostname, IP, or other identifying sources
  - Best-effort: works even if the home directory is read-only

This package is a 1:1 port of upstream ``identity/anonymous-user-id`` from
deepseek-harness, following the same behavioral semantics and error handling.

================================================================================
PUBLIC API
================================================================================
The package exports:
  - ``getOrCreateAnonymousUserId(options)``: Main entry point. Returns the
    anonymous user id, creating one on first use.
  - ``AnonymousUserId``: Type alias for the id (a UUID v4 string).
  - ``AnonymousUserIdOptions``: Configuration dataclass for customization.
  - ``ANONYMOUS_USER_ID_FILE_NAME``: The filename used for persistence.

For the invariant companion (DSH DI framework integration):
  - ``apply(ctx)``: Registers the invariant companion with the DI framework.
  - ``name``, ``inject``, ``PACKAGE_NAME``: Companion metadata.

================================================================================
USAGE EXAMPLE
================================================================================
```python
from lca.packages.identity.anonymous_user_id import getOrCreateAnonymousUserId

# Get or create the anonymous user id (uses $DSH_HOME or ~/.dsh)
user_id = getOrCreateAnonymousUserId()
print(f"Anonymous user id: {user_id}")

# With custom options
from lca.packages.identity.anonymous_user_id import AnonymousUserIdOptions
options = AnonymousUserIdOptions(
    env={"DSH_HOME": "/custom/path"},
    random_uuid=lambda: "deterministic-uuid-for-testing"
)
user_id = getOrCreateAnonymousUserId(options)
```

================================================================================
UPSTREAM ALIGNMENT
================================================================================
This package maintains 1:1 behavioral parity with upstream TypeScript:
  - Same file format (bare UUID line, no JSON wrapper)
  - Same memoization semantics (process-lifetime cache)
  - Same concurrent-launch handling (exclusive-create with reread)
  - Same best-effort error handling (read-only homes still work)
  - Same UUID validation (RFC 4122 format)
"""

from __future__ import annotations

# Re-export the public API from index.py
from .index import (
    ANONYMOUS_USER_ID_FILE_NAME,
    AnonymousUserId,
    AnonymousUserIdOptions,
    getOrCreateAnonymousUserId,
)

# Re-export the invariant companion API
from .invariant import (
    PACKAGE_NAME,
    apply,
    inject,
    name,
)

__all__ = [
    # Main API
    "ANONYMOUS_USER_ID_FILE_NAME",
    "AnonymousUserId",
    "AnonymousUserIdOptions",
    "getOrCreateAnonymousUserId",
    # Invariant companion API
    "PACKAGE_NAME",
    "apply",
    "inject",
    "name",
]
