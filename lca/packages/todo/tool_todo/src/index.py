"""Model-facing whole-list replacement todo tool.

================================================================================
UPSTREAM ORIGIN
================================================================================
1:1 port of ``todo/tool-todo/src/index.ts`` from deepseek-harness.

Each call appends a ``todo/write`` snapshot to the calling agent's session;
replay is last-write-wins, and UIs render from session events. A non-agent
caller has no owning list and is rejected.

================================================================================
KEY BEHAVIORS
================================================================================
1. TOOL REGISTRATION: The ``todo_write`` tool is registered on the tools service.
   - Takes a complete todo list (not incremental updates)
   - Replaces the previous list entirely
   - Validates the input before accepting

2. VALIDATION: Input validation includes:
   - Content must be non-empty and trimmed
   - No duplicate content
   - Status must be one of the valid values
   - At most one ``in_progress`` item unless parallel is allowed

3. CONFIGURATION: The tool can be configured with:
   - ``allowParallelInProgress``: Whether multiple items can be in_progress

4. PROJECTION: The todo list is stored as a session projection:
   - Key: ``todos``
   - Whole-value replacement (last-write-wins)
   - None before first write

5. OUTPUT: The tool returns:
   - The validated todo list
   - Counts of items by status

================================================================================
PYTHON-SPECIFIC NOTES
================================================================================
- Uses Protocol for Context (structural typing)
- Uses dataclass for configuration
- Uses Protocol for tool registration interface

================================================================================
TESTING
================================================================================
Tests at ``tests/packages/todo/tool_todo/test_index.py`` exercise:
  - Tool registration
  - Input validation
  - Configuration options
  - Projection updates
  - Error handling
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import TODO_STATUSES, TodoItem


# ---------------------------------------------------------------------------
# Public: Config
# ---------------------------------------------------------------------------
# Configuration for the todo tool.
@dataclass(frozen=True)
class Config:
    """Configuration for the todo tool.

    Attributes:
        allowParallelInProgress: Whether multiple items can be in_progress.
    """

    allowParallelInProgress: bool


# ---------------------------------------------------------------------------
# Internal: Constants
# ---------------------------------------------------------------------------
DESCRIPTION_HEAD = (
    "Record and update a structured task list for the current work. Send the ENTIRE "
    "list every call — it REPLACES the previous list (there are no partial updates, "
    "no per-item edits). Use it to plan multi-step work and show progress: add one "
    "todo per concrete step before you start. "
)

DESCRIPTION_PARALLEL = (
    "Mark every todo being actively worked "
    "on `in_progress` — several at once when work genuinely runs in parallel (e.g. "
    "concurrent subagents or background commands), one for sequential work; while "
    "work remains, at least one task should be `in_progress`. "
)

DESCRIPTION_SINGLE = (
    "Keep AT MOST ONE todo `in_progress` at a "
    "time; while work remains, exactly one active task should be `in_progress`. "
)

DESCRIPTION_TAIL = (
    "Mark a todo "
    "`completed` the moment it is done (do not batch completions), and allow no "
    "`in_progress` item only once all work is complete. Skip the list for trivial "
    "single-step tasks. Statuses: `pending` (not started), `in_progress` (being "
    "worked on now), `completed` (finished)."
)


# ---------------------------------------------------------------------------
# Internal: Helper functions
# ---------------------------------------------------------------------------
def _describe(allow_parallel: bool) -> str:
    """Generate the tool description based on configuration.

    Args:
        allow_parallel: Whether multiple items can be in_progress.

    Returns:
        The composed tool description.
    """
    return (
        DESCRIPTION_HEAD
        + (DESCRIPTION_PARALLEL if allow_parallel else DESCRIPTION_SINGLE)
        + DESCRIPTION_TAIL
    )


def _to_todo_list(
    raw: list[dict[str, Any]],
    allow_parallel: bool,
) -> list[TodoItem]:
    """Validate and convert raw todo items to TodoItem instances.

    Args:
        raw: The model-supplied list of todo items.
        allow_parallel: Whether multiple items can be in_progress.

    Returns:
        The validated list of TodoItem instances.

    Raises:
        ValueError: If validation fails.
    """
    todos: list[TodoItem] = []
    seen: set[str] = set()
    active = 0

    for item in raw:
        content = item["content"].strip()
        if len(content) == 0:
            raise ValueError("invalid todo: `content` must be a non-empty string")

        if content in seen:
            raise ValueError(f"invalid todos: duplicate content {content!r}")

        seen.add(content)

        status = item["status"]
        if status == "in_progress":
            active += 1

        todos.append(TodoItem(content=content, status=status))

    if not allow_parallel and active > 1:
        raise ValueError(f"invalid todos: at most one task may be in_progress (got {active})")

    return todos


# ---------------------------------------------------------------------------
# Public: name, inject
# ---------------------------------------------------------------------------
# Companion metadata for plugin registration.
name = "tool-todo"
inject = ["tools"]


# ---------------------------------------------------------------------------
# Public: apply
# ---------------------------------------------------------------------------
def apply(ctx: Any, config: Config) -> None:
    """Register the todo_write tool and projection.

    Args:
        ctx: Context carrying the tool registry.
        config: Configuration for the tool.
    """
    allow_parallel = config.allowParallelInProgress

    # Register the projection (if sessionProjections is available)
    if hasattr(ctx, "sessionProjections"):
        ctx.sessionProjections.register(
            key="todos",
            init=lambda: None,
            apply=lambda state, event: (
                event.data["todos"]
                if event.type == "todo/write"
                else None
                if event.type == "turn/start"
                else state
            ),
            view=lambda state: state,
            state_version=2,
        )

    # Register the tool
    ctx.tools.register(
        {
            "name": "todo_write",
            "description": _describe(allow_parallel),
            "parameters": {
                "todos": {
                    "type": "array",
                    "required": True,
                    "description": "The COMPLETE task list, replacing any previous list.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "content": {
                                "type": "string",
                                "required": True,
                                "description": "What the task is — a short imperative line.",
                            },
                            "status": {
                                "type": "string",
                                "required": True,
                                "enum": list(TODO_STATUSES),
                                "description": "pending (not started) | in_progress (now) | completed (done).",
                            },
                        },
                    },
                },
            },
            "execute": lambda args, exec_ctx: _execute(args, exec_ctx, allow_parallel),
        }
    )


def _execute(
    args: dict[str, Any],
    exec_ctx: Any,
    allow_parallel: bool,
) -> dict[str, Any]:
    """Execute the todo_write tool.

    Args:
        args: The tool arguments.
        exec_ctx: The execution context.
        allow_parallel: Whether multiple items can be in_progress.

    Returns:
        The tool result with todos and counts.

    Raises:
        ValueError: If validation fails or no agent session.
    """
    todos = _to_todo_list(args["todos"], allow_parallel)

    if not hasattr(exec_ctx, "agent") or exec_ctx.agent is None:
        raise ValueError("todo_write requires an owning agent session")

    # Append the event to the session
    exec_ctx.agent.session.append("todo/write", {"todos": todos})

    # Count items by status
    counts = {
        "pending": sum(1 for t in todos if t.status == "pending"),
        "inProgress": sum(1 for t in todos if t.status == "in_progress"),
        "completed": sum(1 for t in todos if t.status == "completed"),
    }

    return {
        "todos": [{"content": t.content, "status": t.status} for t in todos],
        "counts": counts,
    }


__all__ = [
    "Config",
    "apply",
    "inject",
    "name",
]
