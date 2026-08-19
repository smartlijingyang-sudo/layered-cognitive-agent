"""Configurable registry for package-owned runtime invariant contributions.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``runtime-diagnostics/invariants/src/index.ts`` from deepseek-harness.

This module provides a registry system for runtime invariants - checks that
validate package contracts and raise errors when violated. Every workspace
package can register checks from a ``./invariant`` companion module.

================================================================================
KEY BEHAVIORS
================================================================================
1. REGISTRATION: Packages register invariant checkers via ``InvariantRegistry.register()``.
   Each registration is tracked by package name and can be filtered by allowlist/blocklist.

2. FILTERING: The registry supports regex-based filtering:
   - ``package_allowlist``: Only packages matching these patterns are checked
   - ``package_blocklist``: Packages matching these patterns are excluded
   - Filters are compiled at construction time and validated for correctness

3. INSTALLATION: When a package is registered, its installer function is called
   with a child context and a failure reporter. The installer can perform
   async operations and should raise ``InvariantError`` on violations.

4. LIFECYCLE: Registrations are tracked and can be disposed. Disposal removes
   the package from the registry and cleans up any resources.

5. ERROR HANDLING: Invalid package names, duplicate registrations, and
   installer failures all raise appropriate errors with clear messages.

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- TypeScript's ``Context`` and ``Service`` from Cordis are replaced with
  Protocol-based interfaces for structural typing
- Async operations use Python's ``asyncio`` instead of JavaScript Promises
- Regex patterns use Python's ``re`` module instead of JavaScript RegExp
- Type validation uses ``dataclasses`` instead of schemastery

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/runtime-diagnostics/invariants/test_index.py`` exercise:
  - Config validation (allowlist/blocklist patterns)
  - Package registration and filtering
  - Installer invocation and error handling
  - Disposal and cleanup
  - Error messages and exception types
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
# - ``re``: for regex pattern compilation and validation
# - ``dataclass``: for structured configuration
# - ``Protocol``: for structural typing of interfaces
# - ``Callable``: for function type hints
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# Public: Config
# ---------------------------------------------------------------------------
# Configuration for the invariant registry. Controls which packages are checked
# and whether the registry is globally enabled.
#
# WHY A DATACLASS?
# TypeScript uses an interface with optional fields. Python dataclasses give us
# the same "named optional fields with defaults" pattern with runtime validation.
@dataclass
class Config:
    """Runtime invariant selection configured on the service plugin.

    Attributes:
        enabled: Global switch to enable/disable all invariant checks.
        package_allowlist: Regex patterns for packages to check (empty = all).
        package_blocklist: Regex patterns for packages to exclude.
    """

    enabled: bool = True
    package_allowlist: list[str] = field(default_factory=list)
    package_blocklist: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public: InvariantFailure
# ---------------------------------------------------------------------------
# Type alias for the failure reporter function. When an invariant check fails,
# the installer calls this function with an error message, which raises
# ``InvariantError``.
InvariantFailure = Callable[[str], None]


# ---------------------------------------------------------------------------
# Public: InvariantInstaller
# ---------------------------------------------------------------------------
# Protocol for installer functions. Each package provides an installer that
# performs invariant checks when called. The installer receives a context
# and a failure reporter.
#
# WHY A PROTOCOL?
# TypeScript uses a callable interface. Python Protocols give us the same
# "duck typing with documentation" pattern for callable objects.
class InvariantInstaller(Protocol):
    """Install one package's checks into the registration's child context.

    Args:
        ctx: Child context owned by this invariant registration.
        fail: Reporter bound to the registering package name.

    Returns:
        Nothing, or a promise settling after asynchronous checks finish.
    """

    def __call__(self, ctx: Any, fail: InvariantFailure) -> Any: ...


# ---------------------------------------------------------------------------
# Public: InvariantError
# ---------------------------------------------------------------------------
# Custom exception class for invariant violations. Includes the package name
# that owns the violated invariant for clear error attribution.
class InvariantError(Exception):
    """Thrown when a package-owned runtime invariant is violated.

    Attributes:
        code: Stable machine-readable invariant failure code ('INVARIANT').
        package_name: Full package name that owned the violated invariant.
    """

    code: str = "INVARIANT"
    package_name: str

    def __init__(self, package_name: str, message: str) -> None:
        """Construct a package-attributed invariant failure.

        Args:
            package_name: Full package name that registered the check.
            message: Violated contract, without the standard error prefix.
        """
        super().__init__(f'invariant violated by "{package_name}": {message}')
        self.name = "InvariantError"
        self.package_name = package_name


# ---------------------------------------------------------------------------
# Internal: compile_patterns
# ---------------------------------------------------------------------------
# Compiles and validates a list of regex patterns. Ensures patterns are
# non-blank, have no surrounding whitespace, and are not duplicates.
#
# ERROR HANDLING:
# - Empty or whitespace-only patterns raise ValueError
# - Duplicate patterns raise ValueError
# - Invalid regex syntax raises ValueError with the original error
def _compile_patterns(field_name: str, values: list[str]) -> list[re.Pattern[str]]:
    """Compile and validate one package-filter list.

    Args:
        field_name: Name of the field being compiled (for error messages).
        values: List of regex pattern strings.

    Returns:
        List of compiled regex patterns.

    Raises:
        ValueError: If patterns are invalid, blank, or duplicated.
    """
    seen: set[str] = set()
    patterns: list[re.Pattern[str]] = []

    for value in values:
        # Validate non-blank and no surrounding whitespace
        if len(value) == 0 or value.strip() != value:
            raise ValueError(
                f"invariants: {field_name} entries must be non-blank and have no surrounding whitespace"
            )

        # Check for duplicates
        if value in seen:
            raise ValueError(f"invariants: {field_name} contains duplicate regex {value!r}")

        seen.add(value)

        # Compile the regex pattern
        try:
            patterns.append(re.compile(value))
        except re.error as e:
            raise ValueError(f"invariants: {field_name} contains invalid regex {value!r}") from e

    return patterns


# ---------------------------------------------------------------------------
# Public: InvariantRegistry
# ---------------------------------------------------------------------------
# Main registry class for managing package-owned runtime invariants. Tracks
# registrations, applies filtering, and manages the lifecycle of invariant
# checkers.
#
# KEY DESIGN DECISIONS:
# - Registrations are tracked by package name (not installer object)
# - Filtering is applied at registration time, not check time
# - Disposal is explicit and removes the package from tracking
# - Error messages include package names for clear attribution
class InvariantRegistry:
    """Package-owned invariant registry with global and regex-based selection.

    Attributes:
        config: Configuration for the registry.
        enabled: Whether the registry is globally enabled.
        package_allowlist: Compiled regex patterns for packages to check.
        package_blocklist: Compiled regex patterns for packages to exclude.
        registrations: Set of currently registered package names.
    """

    def __init__(self, ctx: Any = None, config: Config | None = None) -> None:
        """Create and install the invariant registry.

        Args:
            ctx: Context that owns the service (unused in Python port).
            config: Global enablement and package-name regex filters.
        """
        if config is None:
            config = Config()

        self._ctx = ctx
        self.enabled = config.enabled
        self.package_allowlist = _compile_patterns("package_allowlist", config.package_allowlist)
        self.package_blocklist = _compile_patterns("package_blocklist", config.package_blocklist)
        self.registrations: set[str] = set()

    def _selected(self, package_name: str) -> bool:
        """Return whether one full package name passes the configured filters.

        Args:
            package_name: Full package name to check.

        Returns:
            True if the package should be checked, False otherwise.
        """
        # If globally disabled, nothing is selected
        if not self.enabled:
            return False

        # If allowlist is non-empty, package must match at least one pattern
        if len(self.package_allowlist) > 0:
            if not any(pattern.search(package_name) for pattern in self.package_allowlist):
                return False

        # If package matches any blocklist pattern, it's excluded
        if any(pattern.search(package_name) for pattern in self.package_blocklist):
            return False

        return True

    def register(self, package_name: str, installer: InvariantInstaller) -> Callable[[], None]:
        """Register one package's invariant installer.

        The package name is reserved even when filtering disables its checks.
        Enabled installers run immediately; failure disposes the registration.

        Args:
            package_name: Full package name that owns the contribution.
            installer: Listener or startup-check installer for the child context.

        Returns:
            A disposer function that removes the registration.

        Raises:
            ValueError: If package name is invalid or already registered.
        """
        # Validate package name
        if (
            len(package_name) == 0
            or package_name.strip() != package_name
            or re.search(r"\s", package_name)
        ):
            raise ValueError("invariants: packageName must be non-blank and contain no whitespace")

        # Check for duplicate registration
        if package_name in self.registrations:
            raise ValueError(f'invariants: package "{package_name}" is already registered')

        # Reserve the package name
        self.registrations.add(package_name)

        # Create failure reporter bound to this package
        def fail(message: str) -> None:
            raise InvariantError(package_name, message)

        # Run the installer if the package is selected
        if self._selected(package_name):
            try:
                installer(self._ctx, fail)
            except Exception:
                # Installer failed - remove registration and re-raise
                self.registrations.discard(package_name)
                raise

        # Return disposer function
        def dispose() -> None:
            self.registrations.discard(package_name)

        return dispose


__all__ = [
    "Config",
    "InvariantError",
    "InvariantFailure",
    "InvariantInstaller",
    "InvariantRegistry",
]
