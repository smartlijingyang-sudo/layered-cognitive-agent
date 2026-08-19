"""Package-owned invariant companion for the anonymous-user-id package.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``identity/anonymous-user-id/src/invariant.ts`` from deepseek-harness.

In the DSH (DeepSeek Harness) architecture, packages can register "invariant
companions" — startup hooks that validate the package's runtime invariants
(e.g., "this service is initialized", "this config is valid", "this connection
is established"). Companions are registered during the Cordis (DSH's DI framework)
plugin setup phase and can declare dependencies on other services.

================================================================================
WHY THIS COMPANION EXISTS
================================================================================
Every package in the DSH ecosystem follows a consistent pattern:
  1. A main module (``index.ts``) with the package's core logic
  2. An invariant companion (``invariant.ts``) that declares:
     - ``name``: the companion's identity (for logging/debugging)
     - ``inject``: services this companion depends on
     - ``install``: a function that runs at startup to validate invariants
     - ``apply``: a function that registers the companion with the DI framework

For ``anonymous-user-id``, the companion is essentially a no-op because:
  - The package has no runtime invariants to validate (it's just a UUID generator)
  - The "invariant" is really just "the file can be created/read" — but that's
    tested at runtime in ``getOrCreateAnonymousUserId``, not at startup

So this file exists primarily to follow the DSH package convention and ensure
the package is properly integrated into the DI framework's startup sequence.

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- In TypeScript, ``Context`` and ``InvariantInstaller`` are imported from Cordis.
  In Python, we define minimal ``Protocol`` interfaces that match the surface
  we actually use (structural typing, like TypeScript).
- The companion registration is just ``ctx.invariants.register(name, installer)``.
  We don't model the full Cordis lifecycle — just the registration contract.
- ``inject`` is a tuple of service names (not a list like in TS). This is a
  Python idiom — tuples are immutable, which matches the "this is a constant"
  semantic.

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/identity/anonymous_user_id/test_invariant.py`` exercise:
  - Constants (name, inject, PACKAGE_NAME)
  - ``apply`` function (registers with mock invariant service)
  - ``_install`` function (verifies it's a no-op)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
# - ``Any``: for the opaque ``installer`` parameter (we don't model its full type)
# - ``Protocol``: for structural typing of ``InvariantRegistry`` and ``InvariantContext``
#   (Python's answer to TypeScript interfaces)
from typing import Any, Protocol

# ---------------------------------------------------------------------------
# Internal constant: PACKAGE_NAME
# ---------------------------------------------------------------------------
# The full npm-style package name. In the DSH ecosystem, packages are identified
# by their full scoped name (e.g., ``@deepseek-ai/dsh-anonymous-user-id``). This
# is used for logging, debugging, and invariant registration.
PACKAGE_NAME = "@deepseek-ai/dsh-anonymous-user-id"

# ---------------------------------------------------------------------------
# Public constant: name
# ---------------------------------------------------------------------------
# The companion's identity within the invariant system. This is distinct from
# ``PACKAGE_NAME`` — it's the name of the *companion plugin*, not the package
# itself. Used for logging and diagnostic output.
name = "anonymous-user-id-invariant"

# ---------------------------------------------------------------------------
# Public constant: inject
# ---------------------------------------------------------------------------
# Services this companion depends on. In Cordis (the DSH DI framework), ``inject``
# declares which services must be available before this companion's ``install``
# function runs. For this companion, we depend on the ``invariants`` service
# (which is... the service that manages invariants — it's a bit circular, but
# it's the root of the invariant system).
#
# WHY A TUPLE?
# TypeScript uses ``['invariants']`` (array literal). Python tuples are the
# idiomatic "immutable sequence of strings" type. This matches the semantic:
# the inject list is a constant, not something that changes at runtime.
inject = ("invariants",)


# ---------------------------------------------------------------------------
# Internal Protocol: InvariantRegistry
# ---------------------------------------------------------------------------
# Minimal structural interface for the invariant registry service. We only model
# the ``register`` method because that's all this companion uses.
#
# WHY A PROTOCOL?
# TypeScript uses ``ctx.invariants: InvariantRegistry`` (interface). Python
# Protocols give us the same "duck typing with documentation" pattern without
# requiring the actual Cordis library.
class InvariantRegistry(Protocol):
    """Minimal surface of the invariants service consumed by this companion."""

    def register(self, package_name: str, installer: Any) -> callable:
        """Register an invariant companion.

        Args:
            package_name: The full package name (for logging).
            installer: A callable that runs at startup to validate invariants.

        Returns:
            A disposer function that unregisters the companion (if needed).
        """
        ...


# ---------------------------------------------------------------------------
# Internal Protocol: InvariantContext
# ---------------------------------------------------------------------------
# Minimal structural interface for the Cordis context object. We only model the
# ``invariants`` property because that's all this companion uses.
class InvariantContext(Protocol):
    """Minimal surface of the Cordis context consumed by this companion."""

    @property
    def invariants(self) -> InvariantRegistry:
        """The invariant registry service."""
        ...


# ---------------------------------------------------------------------------
# Internal function: _install
# ---------------------------------------------------------------------------
# The actual invariant validation function. For this package, it's a no-op
# because there are no runtime invariants to validate (the package is just a
# UUID generator with best-effort file persistence).
#
# WHY IS THIS A NO-OP?
# In other packages, ``install`` might check things like:
#   - "Is the database connection established?"
#   - "Is the config file valid?"
#   - "Are required environment variables set?"
# But ``anonymous-user-id`` has no such invariants. The "invariant" is really
# just "can we create/read the file" — but that's tested at runtime in
# ``getOrCreateAnonymousUserId``, not at startup.
#
# Args:
#   _ctx: The child context (unused, hence the underscore prefix).
#   _fail: A reporter function for invariant violations (unused).
#
# Returns:
#   Nothing (implicit ``None``). This is a pure side-effect function (or rather,
#   a pure no-op function).
def _install(_ctx: Any, _fail: callable) -> None:
    """No runtime invariant — the API owns one private memo and one best-effort
    file, with no independent event stream or public mutable relation."""
    pass


# ---------------------------------------------------------------------------
# Public function: apply
# ---------------------------------------------------------------------------
# The main entry point for the companion. Registers the package's invariant
# companion with the DI framework. This is called during the Cordis plugin
# setup phase.
#
# WHY RETURN THE DISPOSER?
# The ``register`` method returns a disposer function that can be used to
# unregister the companion (e.g., during shutdown or hot-reload). We return it
# to the caller so they can manage the companion's lifecycle if needed.
def apply(ctx: InvariantContext) -> callable:
    """Register this package's invariant companion.

    Args:
        ctx: Cordis context carrying the invariant service.

    Returns:
        The installed registration's disposer after setup succeeds.
    """
    # Register the companion with the invariant service.
    # ``PACKAGE_NAME`` identifies the package (for logging).
    # ``_install`` is the no-op validation function.
    return ctx.invariants.register(PACKAGE_NAME, _install)


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------
# Explicitly declare the public API. This mirrors upstream's ``export`` statements
# and makes it clear which symbols are part of the package's contract.
__all__ = [
    "PACKAGE_NAME",
    "apply",
    "inject",
    "name",
]
