"""Per-harness-home anonymous user id shared by telemetry and feedback.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``identity/anonymous-user-id/src/index.ts`` from deepseek-harness.

In upstream, the anonymous user id is a persistent UUID stored in the harness
home directory (typically ``~/.dsh`` or ``$DSH_HOME``). This id is used by:
  - Telemetry: to identify the installation for usage metrics
  - Feedback: to correlate user feedback with their session history

The id is NEVER derived from hostname, IP, MAC address, git remote, or any
other identifying source — it's purely a random UUID that persists across
process restarts but is scoped to the harness home directory.

================================================================================
KEY BEHAVIORS
================================================================================
1. FIRST USE: On first access, a random UUID v4 is minted and persisted to
   ``$DSH_HOME/.anonymous-user-id`` as a bare line (no JSON wrapper).

2. SUBSEQUENT USES: The file is read once and memoized for the process lifetime.
   This means:
   - The process touches disk at most once per launch
   - If the file is deleted mid-run, the process keeps using its cached id
   - Next launch after deletion mints a fresh id

3. CONCURRENT LAUNCHES: Multiple processes launching simultaneously may race
   to create the file. We use exclusive-create (``open(..., 'x')``) to detect
   the race:
   - Winner: successfully creates the file with its UUID
   - Loser: catches ``FileExistsError``, rereads the file, and adopts the
     winner's id (if valid) or overwrites it (if corrupt)

4. READ-ONLY HOME: If the harness home is unwritable (e.g., read-only mount,
   permission denied), we still return a usable id for the current run so
   telemetry/feedback aren't blocked. The id just isn't persisted.

5. CORRUPT FILE: If the persisted file contains invalid data (not a UUID),
   we mint a fresh id and overwrite the corrupt file.

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- In TypeScript, ``AnonymousUserId`` is a branded type (``Branded<'AnonymousUserId'>``).
  Python has no runtime-branded types, so we use a plain ``str`` alias.
- Upstream uses ``node:crypto.randomUUID()``. We use ``uuid.uuid4()`` from stdlib.
- Upstream uses ``node:fs.writeFileSync`` with ``flag: 'wx'`` for exclusive-create.
  We use Python's ``open(..., 'x')`` mode.
- Upstream uses ``node:path.join`` and ``dirname``. We use ``os.path.join``.
- Upstream's ``resolveDshHome`` is imported from ``@deepseek-ai/dsh-home-paths``.
  We inline a minimal version here to keep this package self-contained.

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/identity/anonymous_user_id/test_index.py`` exercise:
  - UUID validation (valid/invalid patterns)
  - File persistence (create, read, corrupt, missing)
  - Memoization (second call returns cached value)
  - Concurrent creation (FileExistsError handling)
  - Read-only home (best-effort fallback)
  - Custom options (env, random_uuid hooks)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
# - ``os``: for ``os.environ`` access and ``os.path.join``
# - ``re``: for UUID pattern matching
# - ``uuid``: stdlib UUID generation (replaces ``node:crypto.randomUUID``)
# - ``dataclass``: for ``AnonymousUserIdOptions`` (structured options bag)
# - ``Path``: modern file I/O (replaces ``node:fs``)
# - ``TypeAlias``: marks ``AnonymousUserId`` as a type alias (not a runtime value)
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

# ---------------------------------------------------------------------------
# Public type: AnonymousUserId
# ---------------------------------------------------------------------------
# In TypeScript this is ``Branded<'AnonymousUserId'>`` — a nominal type that
# prevents accidental mixing with other UUID strings at compile time. Python
# has no runtime-branded types, so we use a plain ``str`` alias. The semantic
# intent (this is a UUID v4 used as an anonymous user identifier) is preserved
# in the type name and documentation.
AnonymousUserId: TypeAlias = str

# ---------------------------------------------------------------------------
# Public constant: ANONYMOUS_USER_ID_FILE_NAME
# ---------------------------------------------------------------------------
# The filename inside the harness home where the id is persisted. This is a
# bare dotfile (starts with ``.``) with no extension. The content is a single
# line containing just the UUID — no JSON wrapper, no metadata. This keeps the
# file format trivially parseable and human-inspectable.
ANONYMOUS_USER_ID_FILE_NAME: str = ".anonymous-user-id"

# ---------------------------------------------------------------------------
# Internal: UUID validation pattern
# ---------------------------------------------------------------------------
# Matches RFC 4122 UUID format: 8-4-4-4-12 hex digits, case-insensitive.
# Used to validate persisted ids and reject corrupt files.
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public: AnonymousUserIdOptions
# ---------------------------------------------------------------------------
# A structured bag of "seams" (injection points) for testing and customization.
# Every field has a sensible default so callers can pass ``None`` or an empty
# options object and get standard behavior.
#
# WHY A DATACLASS?
# TypeScript uses an ``interface`` with optional fields. Python dataclasses
# give us the same ergonomic "named optional fields with defaults" pattern
# without requiring a full Protocol definition (since this is a concrete
# value object, not an interface).
@dataclass
class AnonymousUserIdOptions:
    """Ambient hooks for locating and generating the id.

    All fields are optional and have sensible defaults for production use.
    Tests can override them to control behavior without mocking globals.
    """

    #: Environment consulted for ``DSH_HOME``. If ``None``, uses ``os.environ``.
    #: Override in tests to point to a temporary directory.
    env: dict[str, str] | None = None

    #: UUID generator function. Defaults to ``uuid.uuid4`` (stdlib).
    #: Override in tests to return a deterministic value.
    random_uuid: callable = field(default_factory=lambda: lambda: str(uuid.uuid4()))


# ---------------------------------------------------------------------------
# Internal: Process-lifetime memo
# ---------------------------------------------------------------------------
# Maps resolved file path → cached id. This ensures the process touches disk
# at most once per launch, even if ``getOrCreateAnonymousUserId`` is called
# multiple times.
#
# WHY A MODULE-LEVEL DICT?
# TypeScript uses ``const memo = new Map<string, AnonymousUserId>()``. Python
# module-level dicts have the same lifetime semantics (one per process). This
# is simpler than a singleton class or global variable.
_memo: dict[str, AnonymousUserId] = {}


# ---------------------------------------------------------------------------
# Internal: _resolve_dsh_home
# ---------------------------------------------------------------------------
# Resolves the harness home directory using the same precedence as upstream:
#   1. ``$DSH_HOME`` environment variable (if set)
#   2. ``~/.dsh`` (default fallback)
#
# WHY INLINE THIS?
# In the full LCA integration, this logic lives in ``lca.layer0_infra``. But
# this package is meant to be self-contained (mirrors upstream structure), so
# we keep a minimal copy here. The full resolver can be wired in later if
# needed.
def _resolve_dsh_home(
    _unused: object = None,
    env: dict[str, str] | None = None,
) -> str:
    """Resolve the harness home directory.

    Args:
        _unused: Placeholder for API compatibility with upstream's
            ``resolveDshHome(undefined, env)`` signature. Ignored.
        env: Environment dict to consult. If ``None``, uses ``os.environ``.

    Returns:
        Absolute path to the harness home directory.
    """
    # Use the provided env dict, or fall back to the process environment.
    effective_env = env if env is not None else os.environ

    # Check for explicit DSH_HOME override first.
    value = effective_env.get("DSH_HOME")
    if value:
        return value

    # Fallback: ``~/.dsh`` (expanded via os.path.expanduser for portability).
    return os.path.join(os.path.expanduser("~"), ".dsh")


# ---------------------------------------------------------------------------
# Internal: _read_persisted_id
# ---------------------------------------------------------------------------
# Reads a UUID from the persisted file and validates it against the UUID pattern.
# Returns ``None`` if the file is missing, unreadable, or contains invalid data.
#
# ERROR HANDLING STRATEGY:
# We catch broad exceptions (OSError, UnicodeDecodeError) because:
#   - Missing file: ``FileNotFoundError`` (subclass of OSError)
#   - Permission denied: ``PermissionError`` (subclass of OSError)
#   - Corrupt encoding: ``UnicodeDecodeError``
# In all cases, we treat it as "no valid persisted id" and let the caller mint
# a fresh one. This aligns with upstream's best-effort semantics.
def _read_persisted_id(file: str) -> AnonymousUserId | None:
    """Read a valid persisted id from the file, or ``None`` when absent/corrupt.

    Args:
        file: Absolute path to the persistence file.

    Returns:
        The persisted UUID if valid, otherwise ``None``.
    """
    try:
        # Read the entire file as UTF-8 text.
        text = Path(file).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        # File missing, unreadable, or corrupt encoding — treat as "no id".
        return None

    # Strip whitespace (trailing newline, leading spaces) and validate.
    value = text.strip()
    return value if _UUID_PATTERN.match(value) else None


# ---------------------------------------------------------------------------
# Public: getOrCreateAnonymousUserId
# ---------------------------------------------------------------------------
# The main entry point. Returns the anonymous user id for the current process,
# creating and persisting one on first use.
#
# ALGORITHM:
#   1. Resolve the file path: ``$DSH_HOME/.anonymous-user-id``
#   2. Check the memo: if we've already loaded an id for this file, return it
#   3. Try to read the persisted file:
#      - If valid UUID exists: return it (and memoize)
#      - If missing/corrupt: mint a fresh UUID
#   4. Persist the fresh UUID using exclusive-create (``open(..., 'x')``):
#      - Success: use the fresh UUID
#      - FileExistsError: a concurrent process won the race
#        - Reread the file: if the winner's id is valid, adopt it
#        - Otherwise: overwrite with our fresh id (best-effort)
#      - Other OSError (read-only home): use the fresh id without persisting
#   5. Memoize the id for future calls
#
# WHY THIS COMPLEXITY?
# Concurrent launches are a real scenario (e.g., multiple CLI invocations,
# daemon + CLI, IDE + terminal). The exclusive-create pattern ensures:
#   - Exactly one id per harness home (eventual consistency)
#   - No silent data loss (winner's id is preserved)
#   - Graceful degradation (read-only homes still get a usable id)
def getOrCreateAnonymousUserId(
    options: AnonymousUserIdOptions | None = None,
) -> AnonymousUserId:
    """Return the harness home's anonymous user id, creating one on first use.

    The id is persistent across process restarts (stored in ``$DSH_HOME``) but
    scoped to the harness home directory. Different homes get different ids.

    Args:
        options: Optional seams for home location and UUID generation. If
            ``None``, uses standard production defaults.

    Returns:
        A valid UUID v4 string that uniquely identifies this harness home.
    """
    # Normalize options: use defaults if not provided.
    if options is None:
        options = AnonymousUserIdOptions()

    # Resolve the persistence file path.
    home = _resolve_dsh_home(None, options.env)
    file = os.path.join(home, ANONYMOUS_USER_ID_FILE_NAME)

    # Fast path: check if we've already loaded an id for this file.
    # This avoids redundant disk I/O on repeated calls.
    cached = _memo.get(file)
    if cached is not None:
        return cached

    # Slow path: read from disk or mint a fresh id.
    id_value = _read_persisted_id(file)
    if id_value is None:
        # No valid persisted id — mint a fresh UUID.
        generate = options.random_uuid
        created: AnonymousUserId = generate()

        try:
            # Ensure the parent directory exists (recursive mkdir).
            Path(file).parent.mkdir(parents=True, exist_ok=True)

            # Exclusive-create: write the new id atomically.
            # ``open(..., 'x')`` raises ``FileExistsError`` if the file exists.
            with open(file, "x", encoding="utf-8") as fh:
                fh.write(f"{created}\n")
            id_value = created

        except FileExistsError:
            # A concurrent process created the file first.
            # Strategy: reread and adopt the winner's id (if valid).
            id_value = _read_persisted_id(file)
            if id_value is None:
                # Winner's file is corrupt — overwrite with our fresh id.
                try:
                    Path(file).write_text(f"{created}\n", encoding="utf-8")
                except OSError:
                    # Best-effort: if we can't overwrite, just use the fresh id.
                    # It won't be persisted, but the current run still works.
                    pass
                id_value = created

        except OSError:
            # Read-only home, permission denied, or other IO failure.
            # Best-effort: use the fresh id without persisting.
            # This ensures telemetry/feedback aren't blocked by filesystem issues.
            id_value = created

    # Memoize for future calls within this process.
    _memo[file] = id_value
    return id_value


# ---------------------------------------------------------------------------
# Internal: _reset_memo (test-only helper)
# ---------------------------------------------------------------------------
# Clears the process-lifetime memo. Used by tests to reset state between
# test cases without restarting the Python interpreter.
#
# WARNING: This is NOT part of the public API. Do not call from production code.
def _reset_memo() -> None:
    """Clear the process-lifetime memo. For test isolation only."""
    _memo.clear()


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------
# Explicitly declare the public API. This mirrors upstream's ``export`` statements
# and makes it clear which symbols are part of the package's contract.
__all__ = [
    "ANONYMOUS_USER_ID_FILE_NAME",
    "AnonymousUserId",
    "AnonymousUserIdOptions",
    "getOrCreateAnonymousUserId",
]
