"""Types for the todo domain.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``todo/tool-todo/src/types.ts`` from deepseek-harness.

This module defines the core types for the todo system:
- TodoItem: A single todo item with content and status
- TodoStatus: The valid status values for a todo item

================================================================================
KEY BEHAVIORS
================================================================================
1. TODO ITEM: A todo item has:
   - ``content``: A non-empty, trimmed string describing the task
   - ``status``: One of 'pending', 'in_progress', or 'completed'

2. STATUS VALUES: The valid statuses are:
   - ``pending``: Task not started
   - ``in_progress``: Task currently being worked on
   - ``completed``: Task finished

3. PROJECTION: The todo list is stored as a session projection with key 'todos'
   - Whole-value replacement (not incremental updates)
   - Last-write-wins semantics
   - None before first write

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- Uses dataclass for TodoItem (equivalent to TypeScript interface)
- Uses Literal type for TodoStatus (equivalent to TypeScript union of literals)
- Uses Protocol for type-only imports (equivalent to TypeScript import type)

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/todo/tool_todo/test_types.py`` exercise:
  - TodoItem creation and validation
  - TodoStatus values
  - Type compatibility
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ---------------------------------------------------------------------------
# Public: TodoStatus
# ---------------------------------------------------------------------------
# The valid status values for a todo item.
TodoStatus = Literal["pending", "in_progress", "completed"]


# ---------------------------------------------------------------------------
# Public: TodoItem
# ---------------------------------------------------------------------------
# A single todo item with content and status.
@dataclass(frozen=True)
class TodoItem:
    """A single todo item.

    Attributes:
        content: A non-empty, trimmed string describing the task.
        status: One of 'pending', 'in_progress', or 'completed'.
    """

    content: str
    status: TodoStatus


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# The valid status values as a set for runtime validation.
TODO_STATUSES: set[str] = {"pending", "in_progress", "completed"}


__all__ = [
    "TODO_STATUSES",
    "TodoItem",
    "TodoStatus",
]
