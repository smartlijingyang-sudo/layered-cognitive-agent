"""Compat layer for the loop_cursor module — sunset window.

This subpackage is the single discoverable location for everything
that still exists only because PR-21~24 (the cycle that migrates
business code off ``coord.*`` and onto ``cursor.advance(...)`` /
``cursor.record_*(...)``) has not landed yet.

Re-exports kept alive here
---------------------------

- ``CoordinatorAdapter`` — adapter over ``StepCoordinator`` plus the
  new ``LoopCursor``; lets the un-migrated body / brain / agent code
  keep using ``coord.begin_step``, ``coord.record_*``,
  ``coord.emit_phase``, ``coord.emit`` while the migration sweeps
  through.  Delete when ``rg ``coord.begin_step|coord.record_thinking
  |coord.emit_phase`` lca/cognition lca/body lca/runtime lca/agent``
  is 0 (tracked in the COMPAT block at the top of
  ``coordinator_adapter.py``).

Sunset tracking
----------------

Each item below corresponds to one of the four ADR-mandated deletion
conditions. When a grep drops to zero, the file is deleted and this
manifest shrinks. See ``README.md`` adjacent.

ADR-0185 PR-4:旧 capture / LLM 装饰器 / capture ContextVar 全部删除,
本 compat 不再 re-export。ReasonerPrompt ContextVar 真值已迁至
``lca.plugins.events.hooks.model_visible.reasoner_prompt``。
"""

from __future__ import annotations

# Re-export the historic alias pairs so callers using
# ``from lca.infrastructure.observability.loop_cursor.compat import
# install_run_cursor`` resolve to the canonical implementation.
from lca.infrastructure.observability.loop_cursor.bind import (
    install_run_cursor,
    reset_run_cursor,
)
from lca.infrastructure.observability.loop_cursor.coordinator_adapter import (
    CoordinatorAdapter,
    bind_current_cursor,
    current_cursor,
    get_current_cursor,
    reset_current_cursor,
)

__all__ = [
    "CoordinatorAdapter",
    "bind_current_cursor",
    "current_cursor",
    "get_current_cursor",
    "install_run_cursor",
    "reset_current_cursor",
    "reset_run_cursor",
]
