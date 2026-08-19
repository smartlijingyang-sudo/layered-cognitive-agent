"""Package-owned durable todo-snapshot invariants.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``todo/tool-todo/src/invariant.ts`` from deepseek-harness.

This module provides validation for todo snapshots before they reach the
durable log.

================================================================================
KEY BEHAVIORS
================================================================================
1. VALIDATION: Validates todo/write events before they are persisted:
   - Todos must be an array
   - Each item must be an object with content and status
   - Content must be non-empty and trimmed
   - No duplicate content
   - Status must be one of the valid values

2. SCOPE: Deliberately silent on how many items are ``in_progress``.
   That is the tool's per-deployment policy, not a durable-shape rule.

3. REPLAY: Validates both loaded and newly appended todo snapshots.

4. DISPATCH: Listens for session/event dispatches and validates todo/write events.

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- Uses Protocol for Context (structural typing)
- Uses Protocol for InvariantFailure and InvariantInstaller
- Uses set for TODO_STATUSES (equivalent to TypeScript Set)

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/todo/tool_todo/test_invariant.py`` exercise:
  - Todo validation
  - Event validation
  - Installation and dispatch
  - Error handling
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .types import TODO_STATUSES

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PACKAGE_NAME = "@deepseek-ai/dsh-tool-todo"


# ---------------------------------------------------------------------------
# Internal: Validation functions
# ---------------------------------------------------------------------------
def _validate_todos(value: Any, fail: Callable[[str], None]) -> None:
    """Validate a whole-list todo snapshot.

    Args:
        value: The todo list to validate.
        fail: Failure reporter function.
    """
    if not isinstance(value, list):
        fail("todo/write todos must be an array")
        return

    seen: set[str] = set()

    for item in value:
        if not isinstance(item, dict):
            fail("todo/write entries must be objects")
            continue

        content = item.get("content")
        status = item.get("status")

        # Validate content
        if not isinstance(content, str) or len(content) == 0 or content.strip() != content:
            fail("todo/write content must be non-empty and already trimmed")
            continue

        # Check for duplicates
        if content in seen:
            fail(f"todo/write repeats content {content!r}")
            continue

        seen.add(content)

        # Validate status
        if not isinstance(status, str) or status not in TODO_STATUSES:
            fail(f"todo/write carries unknown status {status!r}")


def _validate_event(event: dict[str, Any], fail: Callable[[str], None]) -> None:
    """Validate a session event if it's a todo/write event.

    Args:
        event: The session event to validate.
        fail: Failure reporter function.
    """
    if event.get("type") == "todo/write":
        _validate_todos(event.get("data", {}).get("todos"), fail)


# ---------------------------------------------------------------------------
# Public: name, inject
# ---------------------------------------------------------------------------
# Companion metadata for plugin registration.
name = "tool-todo-invariant"
inject = ["invariants"]


# ---------------------------------------------------------------------------
# Internal: Install function
# ---------------------------------------------------------------------------
def _install(ctx: Any, fail: Callable[[str], None]) -> None:
    """Install validation for loaded and newly appended todo snapshots.

    Args:
        ctx: Context carrying the sessions service.
        fail: Failure reporter function.
    """
    # Validate all existing sessions
    if hasattr(ctx, "sessions"):
        for session in ctx.sessions.list():
            for event in session.events:
                _validate_event(event, fail)

    # Listen for new events
    if hasattr(ctx, "on"):

        def on_dispatch(mode: str, event_name: str, args: tuple[Any, ...]) -> None:
            if event_name != "session/event":
                return

            event = args[1]
            _validate_event(event, fail)

        ctx.on("internal/dispatch", on_dispatch, {"global": True})


# Attach inject metadata to the install function
_install.inject = ["sessions"]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Public: apply
# ---------------------------------------------------------------------------
def apply(ctx: Any) -> Callable[[], None]:
    """Register the todo invariant companion.

    Args:
        ctx: Context carrying the invariant service.

    Returns:
        The disposer function.
    """
    return ctx.invariants.register(PACKAGE_NAME, _install)


__all__ = [
    "apply",
    "inject",
    "name",
]
