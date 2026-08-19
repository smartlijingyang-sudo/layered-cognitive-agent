"""Client-namespace projection of the todo domain.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``todo/tool-todo/src/client.ts`` from deepseek-harness.

This module provides a pure re-export of the package's types outlet.
Client code imports ONLY the client namespace (repo discipline), so
``./client`` projects the same single-source content ``./types`` serves
to host consumers — zero duplication.

================================================================================
KEY BEHAVIORS
================================================================================
1. RE-EXPORT: This module re-exports all types from the types module.
   - TodoItem
   - TodoStatus
   - TODO_STATUSES

2. NAMESPACE: Client code should import from this module, not directly from types.

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- Simple re-export module (equivalent to TypeScript export *)
- No additional logic or validation

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/todo/tool_todo/test_client.py`` exercise:
  - Re-exports are available
  - Types are correctly exported
"""

from __future__ import annotations

from .types import TODO_STATUSES, TodoItem, TodoStatus

__all__ = [
    "TODO_STATUSES",
    "TodoItem",
    "TodoStatus",
]
