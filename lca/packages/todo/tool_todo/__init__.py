"""Todo tool package for managing task lists.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``todo/tool-todo/`` from deepseek-harness.

This package provides a model-facing todo tool that allows agents to maintain
a structured task list. The tool uses whole-list replacement semantics.

================================================================================
PUBLIC API
================================================================================
The package exports:
  - ``Config``: Configuration for the todo tool
  - ``TodoItem``: A single todo item
  - ``TodoStatus``: Valid status values
  - ``TODO_STATUSES``: Set of valid status values
  - ``name``: Tool name ('tool-todo')
  - ``inject``: Required services (['tools'])
  - ``apply``: Registration function

For the companion module:
  - ``name``: Companion name ('tool-todo-invariant')
  - ``inject``: Required services (['invariants'])
  - ``apply``: Companion registration function

================================================================================
USAGE EXAMPLE
================================================================================
```python
from lca.packages.todo.tool_todo import Config, apply

# Create configuration
config = Config(allowParallelInProgress=True)

# Register the tool
apply(ctx, config)
```

================================================================================
UPSTREAM ALIGNMENT
================================================================================
This package maintains 1:1 behavioral parity with upstream TypeScript:
  - Same validation rules
  - Same configuration options
  - Same projection semantics
  - Same invariant checks
"""

from __future__ import annotations

from .index import Config, apply, inject, name
from .types import TODO_STATUSES, TodoItem, TodoStatus

__all__ = [
    # Main API
    "Config",
    "TodoItem",
    "TodoStatus",
    "TODO_STATUSES",
    "name",
    "inject",
    "apply",
]
